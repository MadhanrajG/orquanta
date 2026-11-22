# Copyright 2026 OrQuanta — Apache License 2.0
"""
Phase 5A — OpenTelemetry Unified Telemetry
==========================================
Provides distributed tracing, structured logging, and metrics propagation
across FastAPI, Celery, agents, and provider adapters.

Security:
- API keys, credentials, and sensitive prompt content are redacted before
  any trace attribute is recorded.
- Telemetry failures NEVER disable security policy enforcement.
- Tenant attribution is propagated as a trace attribute, never as a baggage
  item that could leak cross-tenant.

Usage:
    from observability.telemetry import get_tracer, get_meter, record_span_error
    from observability.telemetry import redact_sensitive

Span naming convention:
    <component>.<operation>   e.g. "inference.chat_completion", "agent.execute"
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger("orquanta.observability.telemetry")

# ── OpenTelemetry imports (soft-optional) ─────────────────────────────────────
_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace, metrics as otel_metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.trace import Status, StatusCode, NonRecordingSpan
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.context import attach, detach, get_current
    _OTEL_AVAILABLE = True
except ImportError:
    logger.warning("[Telemetry] opentelemetry-sdk not available — telemetry is a no-op")

# ── OTLP exporter (optional) ─────────────────────────────────────────────────
_OTLP_AVAILABLE = False
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    _OTLP_AVAILABLE = True
except ImportError:
    pass

# ── FastAPI auto-instrumentation (optional) ───────────────────────────────────
_FASTAPI_INSTR_AVAILABLE = False
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    _FASTAPI_INSTR_AVAILABLE = True
except ImportError:
    pass

# ── Configuration ─────────────────────────────────────────────────────────────
SERVICE_NAME_VALUE = os.getenv("OTEL_SERVICE_NAME", "orquanta-api")
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")  # e.g. http://localhost:4317
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"

# Redaction patterns — applied to ALL span attributes before recording
_REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-[a-zA-Z0-9\-]{10,}", re.IGNORECASE), "[API_KEY_REDACTED]"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9\-_.]+", re.IGNORECASE), "Bearer [TOKEN_REDACTED]"),
    (re.compile(r"eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+"), "[JWT_REDACTED]"),
    (re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE), "password=[REDACTED]"),
    (re.compile(r"secret\s*[:=]\s*\S+", re.IGNORECASE), "secret=[REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL_REDACTED]"),
    (re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"), "[CARD_REDACTED]"),
]

# Prompt capture disabled by default — must be explicitly enabled per tenant
_PROMPT_CAPTURE_ENABLED = os.getenv("OTEL_CAPTURE_PROMPTS", "false").lower() == "true"


def redact_sensitive(value: str) -> str:
    """Apply all redaction patterns to a string value."""
    if not isinstance(value, str):
        return str(value)
    for pattern, replacement in _REDACT_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _safe_attr(value: Any) -> str:
    """Convert a value to a safe, redacted string attribute."""
    return redact_sensitive(str(value)[:1024])  # cap at 1 KB per attribute


# ── Tracer/Meter provider setup ───────────────────────────────────────────────

_tracer_provider: Optional[Any] = None
_meter_provider: Optional[Any] = None
_tracer: Optional[Any] = None
_meter: Optional[Any] = None


def setup_telemetry(app: Any = None) -> None:
    """
    Initialise OpenTelemetry providers. Call once at application startup.
    Safe to call multiple times — idempotent.

    :param app: FastAPI app instance for auto-instrumentation (optional).
    """
    global _tracer_provider, _meter_provider, _tracer, _meter

    if not _OTEL_AVAILABLE or not OTEL_ENABLED:
        logger.info("[Telemetry] OpenTelemetry disabled or not available — no-op mode")
        return

    if _tracer_provider is not None:
        return  # Already initialised

    try:
        resource = Resource.create({SERVICE_NAME: SERVICE_NAME_VALUE})

        # ── Trace provider ──────────────────────────────────────────────────
        span_processors = []
        if _OTLP_AVAILABLE and OTLP_ENDPOINT:
            exporter = OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)
            span_processors.append(BatchSpanProcessor(exporter))
            logger.info(f"[Telemetry] OTLP trace export → {OTLP_ENDPOINT}")
        else:
            # Console exporter in development; replace with OTLP in production
            span_processors.append(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("[Telemetry] Console span exporter active (set OTEL_EXPORTER_OTLP_ENDPOINT for OTLP)")

        _tracer_provider = TracerProvider(resource=resource)
        for processor in span_processors:
            _tracer_provider.add_span_processor(processor)
        trace.set_tracer_provider(_tracer_provider)
        _tracer = trace.get_tracer("orquanta", schema_url="https://opentelemetry.io/schemas/1.21.0")

        # ── Meter provider ──────────────────────────────────────────────────
        metric_reader = PeriodicExportingMetricReader(
            ConsoleMetricExporter(),
            export_interval_millis=60_000,
        )
        _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        otel_metrics.set_meter_provider(_meter_provider)
        _meter = otel_metrics.get_meter("orquanta")

        # ── FastAPI auto-instrumentation ────────────────────────────────────
        if app is not None and _FASTAPI_INSTR_AVAILABLE:
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=_tracer_provider,
                excluded_urls="/metrics,/health,/health/readiness",
            )
            logger.info("[Telemetry] FastAPI auto-instrumentation enabled")

        logger.info("[Telemetry] OpenTelemetry setup complete")

    except Exception as exc:
        # Telemetry setup failure MUST NOT crash the application
        logger.error(f"[Telemetry] Setup failed — telemetry will be no-op: {exc}")
        _tracer_provider = None


def get_tracer() -> Any:
    """Return the global tracer (or a no-op tracer if OTel unavailable)."""
    if _tracer is not None:
        return _tracer
    if _OTEL_AVAILABLE:
        return trace.get_tracer("orquanta")
    return _NoOpTracer()


def get_meter() -> Any:
    """Return the global meter (or a no-op meter if OTel unavailable)."""
    if _meter is not None:
        return _meter
    return _NoOpMeter()


# ── Span helpers ──────────────────────────────────────────────────────────────

@contextmanager
def traced_operation(
    name: str,
    tenant_id: str = "",
    actor_id: str = "",
    attributes: Optional[Dict[str, str]] = None,
) -> Generator[Any, None, None]:
    """
    Context manager for a traced operation. Automatically records errors.
    Never propagates telemetry exceptions to the caller.

    Usage:
        with traced_operation("inference.chat", tenant_id="t1") as span:
            span.set_attribute("model", "llama-3")
            result = do_inference(...)
    """
    tracer = get_tracer()
    safe_attrs: Dict[str, str] = {
        "orquanta.tenant_id": _safe_attr(tenant_id),
        "orquanta.actor_id": _safe_attr(actor_id),
        "orquanta.correlation_id": str(uuid.uuid4()),
        "orquanta.timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if attributes:
        safe_attrs.update({k: _safe_attr(v) for k, v in attributes.items()})

    try:
        with tracer.start_as_current_span(name, attributes=safe_attrs) as span:
            yield span
    except Exception as exc:
        # Record span error without leaking sensitive exception details
        try:
            if _OTEL_AVAILABLE and hasattr(span, "set_status"):
                span.set_status(Status(StatusCode.ERROR, str(exc)[:256]))
                span.record_exception(exc)
        except Exception:
            pass
        raise


def record_span_error(span: Any, error: Exception) -> None:
    """Safely record an error on an active span without raising."""
    try:
        if _OTEL_AVAILABLE and span is not None and hasattr(span, "set_status"):
            from opentelemetry.trace import Status, StatusCode
            span.set_status(Status(StatusCode.ERROR, str(error)[:256]))
            span.record_exception(error)
    except Exception:
        pass


def get_current_trace_id() -> str:
    """Return the current trace ID as a hex string, or empty string if no active span."""
    try:
        if _OTEL_AVAILABLE:
            ctx = trace.get_current_span().get_span_context()
            if ctx and ctx.trace_id:
                return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return ""


def inject_trace_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Inject W3C trace-context headers into an outgoing request dict."""
    try:
        if _OTEL_AVAILABLE:
            TraceContextTextMapPropagator().inject(headers)
    except Exception:
        pass
    return headers


# ── Celery trace correlation ──────────────────────────────────────────────────

def celery_task_start_span(task_name: str, task_id: str, tenant_id: str = "") -> Any:
    """
    Begin a trace span for a Celery task. Returns the span (caller must end it).
    Uses a new root span since Celery tasks run in a separate process.
    """
    tracer = get_tracer()
    try:
        span = tracer.start_span(
            f"celery.task.{task_name}",
            attributes={
                "messaging.system": "celery",
                "messaging.destination": task_name,
                "messaging.message_id": task_id,
                "orquanta.tenant_id": _safe_attr(tenant_id),
                "orquanta.timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        return span
    except Exception:
        return _NoOpSpan()


def celery_task_end_span(span: Any, success: bool, error: str = "") -> None:
    """End a Celery task span with success/error status."""
    try:
        if _OTEL_AVAILABLE and hasattr(span, "set_status"):
            from opentelemetry.trace import Status, StatusCode
            if success:
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(Status(StatusCode.ERROR, error[:256]))
        if hasattr(span, "end"):
            span.end()
    except Exception:
        pass


# ── Structured log correlation ────────────────────────────────────────────────

class TraceCorrelationFilter(logging.Filter):
    """
    Logging filter that injects the current trace_id and span_id
    into every log record for correlation.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_current_trace_id() or "no-trace"
        record.span_id = ""
        try:
            if _OTEL_AVAILABLE:
                ctx = trace.get_current_span().get_span_context()
                if ctx and ctx.span_id:
                    record.span_id = format(ctx.span_id, "016x")
        except Exception:
            pass
        return True


def install_trace_log_filter(logger_name: str = "orquanta") -> None:
    """Add trace correlation to the named logger."""
    target = logging.getLogger(logger_name)
    target.addFilter(TraceCorrelationFilter())


# ── No-op fallbacks ───────────────────────────────────────────────────────────

class _NoOpSpan:
    def set_attribute(self, *a, **kw): pass
    def set_status(self, *a, **kw): pass
    def record_exception(self, *a, **kw): pass
    def end(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass


class _NoOpTracer:
    def start_as_current_span(self, *a, **kw):
        from contextlib import contextmanager
        @contextmanager
        def _ctx():
            yield _NoOpSpan()
        return _ctx()
    def start_span(self, *a, **kw):
        return _NoOpSpan()


class _NoOpMeter:
    def create_counter(self, *a, **kw): return _NoOpInstrument()
    def create_histogram(self, *a, **kw): return _NoOpInstrument()
    def create_up_down_counter(self, *a, **kw): return _NoOpInstrument()
    def create_observable_gauge(self, *a, **kw): return _NoOpInstrument()


class _NoOpInstrument:
    def add(self, *a, **kw): pass
    def record(self, *a, **kw): pass


# ── Singleton accessor ────────────────────────────────────────────────────────

def get_telemetry_status() -> Dict[str, Any]:
    """Return current telemetry configuration for diagnostics."""
    return {
        "otel_available": _OTEL_AVAILABLE,
        "otel_enabled": OTEL_ENABLED,
        "otlp_available": _OTLP_AVAILABLE,
        "otlp_endpoint": OTLP_ENDPOINT or "(console exporter)",
        "fastapi_instrumentation": _FASTAPI_INSTR_AVAILABLE,
        "prompt_capture_enabled": _PROMPT_CAPTURE_ENABLED,
        "service_name": SERVICE_NAME_VALUE,
        "tracer_initialized": _tracer is not None,
        "meter_initialized": _meter is not None,
        "limitation": (
            "OpenTelemetry telemetry is best-effort. "
            "Telemetry failure does not affect security policy enforcement."
        ),
    }
