"""
OrQuanta — Prometheus Metrics Middleware
=========================================
Exposes /metrics endpoint for Grafana Cloud monitoring.

Tracks:
  - HTTP request rate, latency, error rate
  - Active GPU jobs count
  - Job submission rate
  - Provider latency by provider name
  - Cost accrued (gauge)

Usage in v4/api/main.py — already imported via this module.
Install: pip install prometheus-client
"""
from __future__ import annotations

import os
import time
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

logger = logging.getLogger("orquanta.metrics")

_prometheus_available = False
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, generate_latest,
        CONTENT_TYPE_LATEST, CollectorRegistry, REGISTRY,
    )
    _prometheus_available = True
except ImportError:
    logger.warning("prometheus-client not installed — /metrics endpoint disabled. Run: pip install prometheus-client")


if _prometheus_available:
    # ── Metric definitions ────────────────────────────────────────────────────
    HTTP_REQUESTS_TOTAL = Counter(
        "orquanta_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status_code"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "orquanta_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )
    ACTIVE_JOBS = Gauge(
        "orquanta_active_jobs",
        "Number of currently running GPU jobs",
    )
    JOBS_SUBMITTED_TOTAL = Counter(
        "orquanta_jobs_submitted_total",
        "Total GPU jobs submitted",
        ["gpu_type", "provider"],
    )
    JOBS_COMPLETED_TOTAL = Counter(
        "orquanta_jobs_completed_total",
        "Total GPU jobs completed",
        ["gpu_type", "provider", "status"],
    )
    COST_ACCRUED_USD = Gauge(
        "orquanta_cost_accrued_usd_total",
        "Total GPU cost accrued across all jobs in USD",
    )
    PROVIDER_LATENCY = Histogram(
        "orquanta_provider_api_latency_seconds",
        "Provider API call latency",
        ["provider", "operation"],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    )
    AGENT_ACTIONS_TOTAL = Counter(
        "orquanta_agent_actions_total",
        "Total actions taken by AI agents",
        ["agent_name", "action_type"],
    )
    WS_CONNECTIONS_ACTIVE = Gauge(
        "orquanta_ws_connections_active",
        "Number of active WebSocket connections",
    )


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that records HTTP metrics for every request.
    Skips /metrics, /health, and static file paths to avoid noise.
    """

    SKIP_PATHS = {"/metrics", "/health", "/health/readiness", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not _prometheus_available:
            return await call_next(request)

        path = request.url.path
        method = request.method

        # Skip noisy paths
        if path in self.SKIP_PATHS or path.startswith("/app/assets"):
            return await call_next(request)

        # Normalize path (replace UUIDs/IDs with placeholders)
        normalized_path = _normalize_path(path)

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            path=normalized_path,
            status_code=str(response.status_code),
        ).inc()

        HTTP_REQUEST_DURATION.labels(
            method=method,
            path=normalized_path,
        ).observe(duration)

        return response


def _normalize_path(path: str) -> str:
    """Replace UUID segments with {id} placeholder to reduce cardinality."""
    import re
    uuid_pattern = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        re.IGNORECASE,
    )
    path = uuid_pattern.sub("{id}", path)
    # Also replace long hex job IDs like job-abc123def456
    path = re.sub(r"job-[a-f0-9]{12,}", "job-{id}", path)
    return path


def get_metrics_response() -> Response:
    """Return Prometheus text format metrics for /metrics endpoint."""
    if not _prometheus_available:
        return Response(
            content="# prometheus-client not installed\n",
            media_type="text/plain",
        )
    # Update active jobs gauge from pipeline
    try:
        from v4.execution.pipeline import get_pipeline
        pipeline = get_pipeline()
        stats = pipeline.get_stats()
        ACTIVE_JOBS.set(stats["by_status"].get("running", 0))
        COST_ACCRUED_USD.set(stats["total_cost_usd"])
    except Exception:
        pass

    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


# ── Helper functions for other modules to record metrics ─────────────────────

def record_job_submitted(gpu_type: str, provider: str):
    if _prometheus_available:
        JOBS_SUBMITTED_TOTAL.labels(gpu_type=gpu_type, provider=provider).inc()


def record_job_completed(gpu_type: str, provider: str, status: str):
    if _prometheus_available:
        JOBS_COMPLETED_TOTAL.labels(gpu_type=gpu_type, provider=provider, status=status).inc()


def record_provider_latency(provider: str, operation: str, duration_s: float):
    if _prometheus_available:
        PROVIDER_LATENCY.labels(provider=provider, operation=operation).observe(duration_s)


def record_agent_action(agent_name: str, action_type: str):
    if _prometheus_available:
        AGENT_ACTIONS_TOTAL.labels(agent_name=agent_name, action_type=action_type).inc()


def track_ws_connection(connected: bool):
    if _prometheus_available:
        if connected:
            WS_CONNECTIONS_ACTIVE.inc()
        else:
            WS_CONNECTIONS_ACTIVE.dec()
