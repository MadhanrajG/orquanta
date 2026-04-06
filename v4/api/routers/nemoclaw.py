"""
OrQuanta NemoClaw API Router

Exposes all NemoClaw engine capabilities as REST endpoints.
Prefix: /api/v1/nemoclaw
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..middleware.auth import get_current_user

try:
    from ...agents.nemoclaw_engine import get_nemoclaw
except ImportError:
    # Fallback for different Python import contexts
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    from v4.agents.nemoclaw_engine import get_nemoclaw

router = APIRouter(prefix="/api/v1/nemoclaw", tags=["NemoClaw"])


# ── Request Models ─────────────────────────────────────────────────────────────

class RunGoalRequest(BaseModel):
    goal_text: str
    budget_usd: float = 200.0


class ContextQueryRequest(BaseModel):
    query: str
    node_type: str | None = None
    top_k: int = 5


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status", summary="NemoClaw engine status and full report")
async def nemoclaw_status(user: dict = Depends(get_current_user)):
    """Return full NemoClaw platform intelligence report."""
    nemo = get_nemoclaw()
    report = nemo.get_report()
    return {
        "engine_status": report.engine_status,
        "context_nodes": report.context_nodes,
        "active_traces": report.active_traces,
        "cost_brakes_fired": report.cost_brakes_fired,
        "total_goals_processed": report.total_goals_processed,
        "avg_confidence": report.avg_confidence,
        "top_context_insight": report.top_context_insight,
        "prefetch_recommendations": [
            {
                "rec_id": r.rec_id,
                "predicted_gpu": r.predicted_gpu,
                "predicted_provider": r.predicted_provider,
                "confidence": r.confidence,
                "reasoning": r.reasoning,
                "action": r.action,
                "estimated_save_minutes": r.estimated_save_minutes,
            }
            for r in report.prefetch_recommendations
        ],
        "generated_at": report.generated_at,
    }


@router.post("/run", summary="Run a goal through NemoClaw enhanced execution")
async def run_goal(
    req: RunGoalRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a goal through NemoClaw's AdaptiveReAct engine with context retrieval."""
    nemo = get_nemoclaw()
    result = await nemo.run_goal(
        goal_text=req.goal_text,
        user_id=user["sub"],
        budget_usd=req.budget_usd,
    )
    return result


@router.post("/context/query", summary="Query the NemoClaw ContextGraph")
async def query_context(
    req: ContextQueryRequest,
    user: dict = Depends(get_current_user),
):
    """Retrieve relevant past decisions and outcomes from the ContextGraph."""
    nemo = get_nemoclaw()
    nodes = nemo.context.query(req.query, node_type=req.node_type, top_k=req.top_k)
    return {
        "query": req.query,
        "results": [
            {
                "node_id": n.node_id,
                "node_type": n.node_type,
                "content": n.content,
                "tags": n.tags,
                "weight": n.weight,
                "access_count": n.access_count,
                "created_at": n.created_at,
            }
            for n in nodes
        ],
        "total_found": len(nodes),
    }


@router.get("/context/stats", summary="ContextGraph statistics")
async def context_stats(user: dict = Depends(get_current_user)):
    """Return ContextGraph node count and type distribution."""
    nemo = get_nemoclaw()
    return nemo.get_context_stats()


@router.get("/traces", summary="List recent AdaptiveReAct traces")
async def list_traces(
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    """Return the most recent NemoClaw reasoning traces."""
    nemo = get_nemoclaw()
    recent = list(nemo._traces.values())[:limit]
    return {
        "traces": [
            {
                "trace_id": t.trace_id,
                "goal_id": t.goal_id,
                "status": t.status,
                "final_confidence": t.final_confidence,
                "steps_count": len(t.steps),
                "replans": t.replans_triggered,
                "started_at": t.started_at,
                "completed_at": t.completed_at,
            }
            for t in recent
        ],
        "total": len(nemo._traces),
    }


@router.get("/traces/{trace_id}", summary="Get full AdaptiveReAct trace")
async def get_trace(
    trace_id: str,
    user: dict = Depends(get_current_user),
):
    """Return the full reasoning chain for a specific trace."""
    nemo = get_nemoclaw()
    trace = nemo.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found.")
    return {
        "trace_id": trace.trace_id,
        "goal_id": trace.goal_id,
        "user_id": trace.user_id,
        "status": trace.status,
        "final_confidence": trace.final_confidence,
        "total_tokens_used": trace.total_tokens_used,
        "replans_triggered": trace.replans_triggered,
        "self_eval_scores": trace.self_eval_scores,
        "steps": trace.steps,
        "started_at": trace.started_at,
        "completed_at": trace.completed_at,
    }


@router.get("/cost/brakes", summary="List CostWatcher brake events")
async def cost_brakes(
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    """Return recent budget enforcement events."""
    nemo = get_nemoclaw()
    brakes = nemo.cost_watcher.get_brakes(limit)
    return {
        "brakes": [
            {
                "brake_id": b.brake_id,
                "user_id": b.user_id,
                "budget_usd": b.budget_usd,
                "spent_usd": b.spent_usd,
                "pct_used": b.pct_used,
                "action_taken": b.action_taken,
                "alternative": b.alternative,
                "potential_save_usd": b.potential_save_usd,
                "fired_at": b.fired_at,
            }
            for b in brakes
        ],
        "total": len(brakes),
    }


@router.get("/prefetch", summary="Get PredictivePrefetch recommendations")
async def get_prefetch(user: dict = Depends(get_current_user)):
    """Return proactive GPU pre-warming recommendations."""
    nemo = get_nemoclaw()
    recs = nemo.prefetch.get_all_recommendations()
    return {
        "recommendations": [
            {
                "rec_id": r.rec_id,
                "predicted_gpu": r.predicted_gpu,
                "predicted_provider": r.predicted_provider,
                "confidence": r.confidence,
                "reasoning": r.reasoning,
                "action": r.action,
                "estimated_save_minutes": r.estimated_save_minutes,
                "predicted_at": r.predicted_at,
            }
            for r in recs
        ],
        "total": len(recs),
    }
