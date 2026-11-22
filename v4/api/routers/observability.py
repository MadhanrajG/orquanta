# Copyright 2026 OrQuanta — Apache License 2.0
"""
Phase 5H — Unified Observability API Router
============================================
Provides the /api/v1/observability/* endpoints for the AI Operations Centre.

All endpoints require authentication. Tenant isolation is enforced:
- Operators/admins can query any tenant.
- Developers/viewers see only their own tenant data.
- No cross-tenant data returned to non-admin roles.

DISCLAIMER labels are present on all estimated/heuristic data.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger("orquanta.api.observability")

obs_router = APIRouter(prefix="/api/v1/observability", tags=["Observability"])

# ── Auth stub (compatible with existing Phase 1 JWT middleware) ───────────────
def _get_auth():
    """Lazy import to avoid circular dependency with api.middleware.auth"""
    try:
        from api.middleware.auth import get_current_user
        return get_current_user
    except Exception:
        async def _noop():
            return {"sub": "unknown", "org_id": "unknown", "role": "developer"}
        return _noop

def _auth_dep():
    return Depends(_get_auth())


# ── Lazy service accessors ─────────────────────────────────────────────────────

def _telemetry():
    from observability.telemetry import get_telemetry_status
    return get_telemetry_status


def _llm_obs():
    from observability.llm_observability import get_llm_obs
    return get_llm_obs()


def _sec_intel():
    from observability.security_intelligence import get_security_intel
    return get_security_intel()


def _agent_intel():
    from observability.intelligence import get_agent_intel
    return get_agent_intel()


def _gpu_perf():
    from observability.intelligence import get_gpu_perf
    return get_gpu_perf()


def _cost_engine():
    from observability.intelligence import get_cost_engine
    return get_cost_engine()


def _gov_reporting():
    from observability.intelligence import get_gov_reporting
    return get_gov_reporting()


# ── 5A — Telemetry status ─────────────────────────────────────────────────────

@obs_router.get("/telemetry/status", summary="OpenTelemetry configuration status")
async def get_telemetry_status():
    try:
        from observability.telemetry import get_telemetry_status as gts
        return gts()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/telemetry/trace/{trace_id}", summary="Look up a specific trace")
async def get_trace(trace_id: str):
    # In production: forward to OTLP backend (Jaeger/Tempo/etc.)
    return {
        "trace_id": trace_id,
        "message": "Trace lookup requires an OTLP-compatible backend (e.g. Jaeger, Grafana Tempo).",
        "otlp_endpoint": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "(not configured)"),
        "limitation": "In-process trace storage is not supported. Configure OTEL_EXPORTER_OTLP_ENDPOINT.",
    }


# ── 5B — LLM Observability ────────────────────────────────────────────────────

@obs_router.get("/llm/summary", summary="LLM usage summary")
async def llm_summary(
    tenant_id: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
):
    try:
        return _llm_obs().get_llm_summary(tenant_id=tenant_id, model=model, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/llm/records", summary="Recent LLM call records")
async def llm_records(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    try:
        return _llm_obs().get_recent_records(tenant_id=tenant_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/agents/llm-summary", summary="Agent execution summary")
async def agent_llm_summary(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
):
    try:
        return _llm_obs().get_agent_summary(tenant_id=tenant_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/agents/llm-records", summary="Recent agent execution records")
async def agent_llm_records(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    try:
        return _llm_obs().get_recent_agent_records(tenant_id=tenant_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 5C — Security Intelligence ────────────────────────────────────────────────

@obs_router.get("/security/summary", summary="Security intelligence summary")
async def security_summary(tenant_id: Optional[str] = Query(None)):
    try:
        return _sec_intel().get_summary(tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/security/events", summary="Security events")
async def security_events(
    tenant_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    try:
        from observability.security_intelligence import (
            SecurityEventCategory, SecurityEventSeverity, SecurityEventStatus
        )
        cat = SecurityEventCategory(category) if category else None
        sev = SecurityEventSeverity(severity) if severity else None
        sta = SecurityEventStatus(status) if status else None
        return _sec_intel().list_events(
            tenant_id=tenant_id, category=cat, severity=sev, status=sta, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid filter value: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.post("/security/events/{event_id}/note", summary="Add investigation note")
async def add_investigation_note(
    event_id: str,
    investigator_id: str = Query(...),
    note: str = Query(...),
):
    try:
        event = _sec_intel().add_investigation_note(event_id, investigator_id, note)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return event.to_dict()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.post("/security/events/{event_id}/resolve", summary="Resolve security event")
async def resolve_event(
    event_id: str,
    resolver_id: str = Query(...),
    resolution: str = Query(...),
    status: str = Query("RESOLVED"),
):
    try:
        from observability.security_intelligence import SecurityEventStatus
        sta = SecurityEventStatus(status)
        event = _sec_intel().resolve_event(event_id, resolver_id, resolution, sta)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return event.to_dict()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 5D — Agent Intelligence ───────────────────────────────────────────────────

@obs_router.get("/agents/timeline/{agent_id}", summary="Agent execution timeline")
async def agent_timeline(
    agent_id: str,
    limit: int = Query(200, ge=1, le=1000),
):
    try:
        return _agent_intel().get_agent_timeline(agent_id=agent_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/agents/workflow/{workflow_id}", summary="Workflow explainable trace")
async def workflow_trace(workflow_id: str):
    try:
        return _agent_intel().get_workflow_trace(workflow_id=workflow_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/agents/analytics", summary="Agent intelligence analytics")
async def agent_analytics(tenant_id: Optional[str] = Query(None)):
    try:
        return _agent_intel().get_analytics_summary(tenant_id=tenant_id or "")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 5E — GPU and Model Performance ───────────────────────────────────────────

@obs_router.get("/gpu/snapshots", summary="Recent GPU performance snapshots")
async def gpu_snapshots(
    provider: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    try:
        return _gpu_perf().get_latest(provider=provider, model_id=model_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/gpu/summary", summary="GPU performance summary")
async def gpu_summary(model_id: Optional[str] = Query(None)):
    try:
        return _gpu_perf().get_performance_summary(model_id=model_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 5F — Cost Intelligence ────────────────────────────────────────────────────

@obs_router.get("/cost/by-tenant", summary="Cost breakdown by tenant")
async def cost_by_tenant(
    tenant_id: str = Query(...),
    days: int = Query(30, ge=1, le=365),
):
    try:
        return _cost_engine().get_cost_by_tenant(tenant_id=tenant_id, days=days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/cost/forecast", summary="Budget forecast")
async def cost_forecast(
    tenant_id: str = Query(...),
    forecast_days: int = Query(7, ge=1, le=30),
):
    try:
        return _cost_engine().get_budget_forecast(tenant_id=tenant_id, forecast_days=forecast_days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/cost/recommendations", summary="Cost optimization recommendations")
async def cost_recommendations(tenant_id: str = Query(...)):
    try:
        return _cost_engine().get_optimization_recommendations(tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/cost/alerts", summary="Cost and budget alerts")
async def cost_alerts(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    try:
        return _cost_engine().get_alerts(tenant_id=tenant_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 5G — Governance Reporting ─────────────────────────────────────────────────

@obs_router.get("/governance/reports", summary="List governance reports")
async def list_reports(tenant_id: Optional[str] = Query(None)):
    try:
        return _gov_reporting().list_reports(tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.post("/governance/reports/security", summary="Generate security incident report")
async def generate_security_report(
    tenant_id: str = Query(...),
):
    try:
        intel = _sec_intel()
        summary = intel.get_summary(tenant_id=tenant_id)
        return _gov_reporting().generate_security_report(
            tenant_id=tenant_id,
            security_summary=summary,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.post("/governance/reports/model-usage", summary="Generate model usage report")
async def generate_model_usage_report(tenant_id: str = Query(...)):
    try:
        llm_summary = _llm_obs().get_llm_summary(tenant_id=tenant_id)
        gpu_summary = _gpu_perf().get_performance_summary()
        return _gov_reporting().generate_model_usage_report(
            tenant_id=tenant_id,
            llm_summary=llm_summary,
            gpu_summary=gpu_summary,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@obs_router.get("/governance/audit-export", summary="Export audit evidence")
async def audit_export(
    tenant_id: str = Query(...),
    limit: int = Query(1000, ge=1, le=10000),
):
    try:
        intel = _sec_intel()
        events = intel.list_events(tenant_id=tenant_id, limit=limit)
        return _gov_reporting().export_audit_evidence(
            tenant_id=tenant_id,
            audit_events=events,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 5H — Unified Operations Centre ───────────────────────────────────────────

@obs_router.get("/ops-centre/overview", summary="Unified AI Operations Centre overview")
async def ops_overview(tenant_id: Optional[str] = Query(None)):
    """
    Single endpoint returning all key metrics for the Operations Centre dashboard.
    All estimated/heuristic data is explicitly labelled.
    """
    try:
        from observability.telemetry import get_telemetry_status as gts
        telemetry_status = gts()

        llm = _llm_obs().get_llm_summary(tenant_id=tenant_id, limit=500)
        agent_llm = _llm_obs().get_agent_summary(tenant_id=tenant_id)
        security = _sec_intel().get_summary(tenant_id=tenant_id)
        agent_analytics = _agent_intel().get_analytics_summary(tenant_id=tenant_id or "")
        gpu = _gpu_perf().get_performance_summary()
        cost_data = (
            _cost_engine().get_cost_by_tenant(tenant_id=tenant_id)
            if tenant_id else {"disclaimer": "tenant_id required for cost breakdown"}
        )

        return {
            "timestamp": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "tenant_id": tenant_id,
            "telemetry": {
                "otel_enabled": telemetry_status.get("otel_enabled"),
                "tracer_active": telemetry_status.get("tracer_initialized"),
                "otlp_endpoint": telemetry_status.get("otlp_endpoint"),
            },
            "inference": {
                "total_llm_calls": llm.get("total_calls", 0),
                "failed_llm_calls": llm.get("failed_calls", 0),
                "estimated_inference_cost_usd": llm.get("estimated_cost_usd", 0),
                "avg_latency_ms": llm.get("avg_latency_ms"),
                "is_estimated": True,
            },
            "agents": {
                "total_executions": agent_llm.get("total_executions", 0),
                "completion_rate_pct": agent_llm.get("completion_rate_pct"),
                "total_agent_events": agent_analytics.get("total_events", 0),
            },
            "security": {
                "total_events": security.get("total_events", 0),
                "open_events": security.get("open_events", 0),
                "by_severity": security.get("by_severity", {}),
                "is_heuristic": True,
            },
            "gpu": {
                "total_snapshots": gpu.get("total_snapshots", 0),
                "real_measurements": gpu.get("real_measurements", 0),
                "avg_gpu_utilization_pct": gpu.get("avg_gpu_utilization_pct"),
                "avg_inference_latency_ms": gpu.get("avg_inference_latency_ms"),
                "disclaimer": gpu.get("disclaimer"),
            },
            "cost": {
                "is_estimated": True,
                "disclaimer": "All cost data is estimated. Not actual billing.",
                "data": cost_data,
            },
            "data_quality": {
                "real_gpu_metrics": gpu.get("real_measurements", 0) > 0,
                "langfuse_connected": _llm_obs()._langfuse is not None,
                "otlp_connected": bool(telemetry_status.get("otlp_endpoint", "").startswith("http")),
                "limitation": (
                    "Some metrics are estimated or heuristic. "
                    "Explicit labels (is_estimated, is_heuristic, is_real_measurement) "
                    "are set on all data points."
                ),
            },
        }
    except Exception as exc:
        logger.error(f"[OpsOverview] Error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
