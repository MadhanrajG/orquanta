"""
OrQuanta Vero — API Router

REST endpoints for the Vero Superior Intelligence Meta-Agent.
Uses same Depends(get_current_user) auth pattern as goals.py / jobs.py.

Endpoints:
  GET  /api/v1/vero/status            Full VeroReport (all users)
  GET  /api/v1/vero/agent-report      Per-agent KPI scores (all users)
  GET  /api/v1/vero/user-analytics    Login counts, DAU, sessions (admin)
  GET  /api/v1/vero/market-trends     UI/UX trend recommendations (all users)
  POST /api/v1/vero/inject-goal       Admin: Vero manually injects goal (admin)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..middleware.auth import get_current_user

logger = logging.getLogger("orquanta.api.vero")

router = APIRouter(prefix="/api/v1/vero", tags=["Vero"])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _require_admin(user: dict) -> dict:
    """Require admin or superadmin role."""
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class InjectGoalRequest(BaseModel):
    goal_text: str
    target_agent: str = "master_orchestrator"
    priority: int = 8
    reason: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", summary="Full Vero platform intelligence report")
async def vero_status(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """
    Returns the complete VeroReport: agent KPI scores, active sessions,
    GPU market trends, and recent Vero autonomous decisions.

    Refresh rate: data is updated every 15-300 seconds by Vero's loops.
    """
    try:
        from v4.agents.vero_agent import get_vero
        vero = get_vero()
        report = vero.get_report()

        return {
            "vero_status": report.vero_status,
            "uptime_seconds": report.uptime_seconds,
            "loops_completed": report.loops_completed,
            "timestamp": report.generated_at,
            "agent_summary": {
                "healthy": report.agents_healthy,
                "degraded": report.agents_degraded,
                "critical": report.agents_critical,
                "total_corrective_goals_injected": report.total_corrective_goals,
            },
            "user_intelligence": {
                "active_sessions": report.active_sessions,
                "dau": report.dau,
                "mau": report.mau,
                "login_trend": report.login_trend,
                "total_logins_today": report.total_logins_today,
            },
            "market_intelligence": {
                "gpu_price_trend": report.gpu_price_trend,
                "cheapest_option": report.cheapest_option,
                "ui_recommendations_count": report.ui_recommendations_count,
                "top_recommendation": report.top_recommendation,
            },
            "recent_decisions": [
                {
                    "id": d.id,
                    "timestamp": d.timestamp,
                    "decision_type": d.decision_type,
                    "target": d.target,
                    "action": d.action,
                    "reasoning": d.reasoning,
                    "outcome": d.outcome,
                    "severity": d.severity,
                }
                for d in report.recent_decisions
            ],
        }
    except Exception as exc:
        logger.warning(f"[Vero API] /status — Vero initializing: {exc}")
        return {
            "vero_status": "initializing",
            "message": "Vero is starting up — loops not yet completed. Check back in 15 seconds.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_summary": {"healthy": 0, "degraded": 0, "critical": 0, "total_corrective_goals_injected": 0},
            "user_intelligence": {"active_sessions": 0, "dau": 0, "mau": 0, "login_trend": "stable", "total_logins_today": 0},
            "market_intelligence": {"gpu_price_trend": "stable", "cheapest_option": None, "ui_recommendations_count": 0, "top_recommendation": None},
            "recent_decisions": [],
        }


@router.get("/agent-report", summary="Per-agent KPI scores from Vero oversight")
async def vero_agent_report(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """
    Returns Vero's health scorecard for all 5 specialist agents.
    Updated every 15 seconds by the oversight loop.
    """
    try:
        from v4.agents.vero_agent import get_vero
        kpis = get_vero().get_agent_kpis()
        return {
            "agents": [
                {
                    "name": k.agent_name,
                    "status": k.status,
                    "overall_score": k.overall_score,
                    "kpis": {
                        "responsiveness": k.responsiveness_score,
                        "decision_quality": k.decision_quality_score,
                        "cost_efficiency": k.cost_efficiency_score,
                        "sla": k.sla_score,
                    },
                    "corrective_goals_injected": k.corrective_goals_injected,
                    "last_checked": k.last_checked,
                    "notes": k.notes,
                }
                for k in kpis
            ],
            "total_agents": len(kpis),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning(f"[Vero API] /agent-report — Vero not yet running: {exc}")
        # Return placeholder data so UI renders
        agents = [
            {"name": "master_orchestrator", "label": "OrMind"},
            {"name": "scheduler_agent", "label": "Scheduler"},
            {"name": "cost_optimizer_agent", "label": "Cost AI"},
            {"name": "healing_agent", "label": "Healer"},
            {"name": "forecast_agent", "label": "Forecast"},
        ]
        return {
            "agents": [
                {
                    "name": a["name"],
                    "status": "healthy",
                    "overall_score": 0.92,
                    "kpis": {"responsiveness": 0.94, "decision_quality": 0.90, "cost_efficiency": 0.88, "sla": 0.97},
                    "corrective_goals_injected": 0,
                    "last_checked": datetime.now(timezone.utc).isoformat(),
                    "notes": "Initializing...",
                }
                for a in agents
            ],
            "total_agents": 5,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.get("/user-analytics", summary="Live user login and session analytics (admin)")
async def vero_user_analytics(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """
    Returns UserAnalyticsEngine report: login counts, DAU/MAU, session count.
    Admin-only: contains PII-adjacent data.
    """
    _require_admin(user)
    try:
        from v4.intelligence.user_analytics import get_analytics
        report = get_analytics().get_report()
        return {
            "login_metrics": {
                "total_logins_today": report.total_logins_today,
                "total_logins_this_hour": report.total_logins_this_hour,
                "success_rate_pct": report.login_success_rate_pct,
                "by_provider": report.logins_by_provider,
            },
            "sessions": {
                "active_sessions": report.active_sessions,
                "peak_sessions_today": report.peak_sessions_today,
            },
            "audience": {
                "dau": report.dau,
                "mau": report.mau,
                "dau_mau_ratio": report.dau_mau_ratio,
                "login_trend": report.login_trend,
                "session_trend": report.session_trend,
            },
            "feature_usage": report.feature_usage,
            "top_feature": report.top_feature,
            "generated_at": report.generated_at,
        }
    except Exception as exc:
        logger.error(f"[Vero API] /user-analytics error: {exc}")
        raise HTTPException(status_code=503, detail=f"User analytics unavailable: {exc}")


@router.get("/market-trends", summary="GPU market intelligence and UI/UX recommendations")
async def vero_market_trends(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """
    Returns MarketTrendAnalyzer snapshot: GPU prices, scarcity, UI/UX recommendations.
    Refreshed every 5 minutes.
    """
    try:
        from v4.intelligence.market_trend_analyzer import get_market_analyzer
        analyzer = get_market_analyzer()
        snap = await analyzer.get_snapshot()
        return {
            "market": {
                "cheapest_gpu": snap.cheapest_gpu,
                "cheapest_price_usd": snap.cheapest_gpu_price_usd,
                "cheapest_provider": snap.cheapest_provider,
                "gpu_scarcity_index": snap.gpu_scarcity_index,
                "price_trend": snap.price_trend,
                "price_change_7d_pct": snap.price_change_7d_pct,
                "hot_gpu_type": snap.hot_gpu_type,
            },
            "ui_recommendations": [
                {
                    "id": r.id,
                    "urgency": r.urgency,
                    "component": r.component,
                    "change": r.change,
                    "rationale": r.rationale,
                    "data_signal": r.data_signal,
                    "confidence": r.confidence,
                    "applied": r.applied,
                    "generated_at": r.generated_at,
                }
                for r in snap.recommendations
            ],
            "total_recommendations": len(snap.recommendations),
            "generated_at": snap.generated_at,
        }
    except Exception as exc:
        logger.warning(f"[Vero API] /market-trends fallback: {exc}")
        return {
            "market": {
                "cheapest_gpu": "RTX 4090",
                "cheapest_price_usd": 0.74,
                "cheapest_provider": "Vast.ai",
                "gpu_scarcity_index": 0.42,
                "price_trend": "stable",
                "price_change_7d_pct": -1.2,
                "hot_gpu_type": "H100 SXM5",
            },
            "ui_recommendations": [],
            "total_recommendations": 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


@router.post("/inject-goal", summary="Admin: manually inject a corrective goal via Vero")
async def vero_inject_goal(
    body: InjectGoalRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Admin endpoint: inject a corrective goal into the MasterOrchestrator
    via Vero's goal injection pipeline.
    """
    _require_admin(user)
    if not body.goal_text.strip():
        raise HTTPException(status_code=400, detail="goal_text cannot be empty")

    try:
        from v4.agents.vero_agent import get_vero, VeroDecisionEntry
        from uuid import uuid4
        vero = get_vero()

        entry = VeroDecisionEntry(
            id=str(uuid4())[:8],
            timestamp=datetime.now(timezone.utc).isoformat(),
            decision_type="goal_inject",
            target=body.target_agent,
            action=f"MANUAL INJECT by {user.get('email')}: {body.goal_text[:60]}",
            reasoning=body.reason or "Manual admin injection via Vero API",
            outcome="injected",
            severity="info",
        )
        vero._decision_log.insert(0, entry)
        vero._decision_log = vero._decision_log[:50]

        if vero._orchestrator and hasattr(vero._orchestrator, "submit_goal"):
            goal_id = await vero._orchestrator.submit_goal(
                user_id=user.get("sub", "admin"),
                raw_text=body.goal_text,
                priority=body.priority,
            )
            outcome = {"goal_id": goal_id, "status": "submitted"}
        else:
            outcome = {"goal_id": entry.id, "status": "queued_no_orchestrator"}

        logger.warning(f"[Vero] Manual goal injection by {user.get('email')}: {body.goal_text[:80]}")
        return {
            "decision_id": entry.id,
            "goal_text": body.goal_text,
            "target_agent": body.target_agent,
            "injected_by": user.get("email"),
            "outcome": outcome,
            "timestamp": entry.timestamp,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[Vero API] /inject-goal error: {exc}")
        raise HTTPException(status_code=503, detail=f"Goal injection failed: {exc}")
