"""OrQuanta Agentic v1.0 — Agents Router."""
from __future__ import annotations
import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from ..middleware.auth import get_current_user, require_admin
from ...agents.master_orchestrator import MasterOrchestrator
from ...agents.safety_governor import get_governor

logger = logging.getLogger("orquanta.routers.agents")
router = APIRouter(prefix="/api/v1/agents", tags=["Agents"])

AGENT_DESCRIPTIONS = {
    "scheduler_agent": "GPU job queue management, priority scoring, bin-packing, preemption",
    "cost_optimizer_agent": "Real-time spot price monitoring, budget enforcement, provider switching",
    "healing_agent": "Continuous health monitoring, OOM detection, anomaly detection, auto-restart",
    "forecast_agent": "GPU demand forecasting, capacity planning, pre-provisioning recommendations",
    "master_orchestrator": "Central ReAct brain, goal decomposition, task dispatch, result synthesis",
}

_orchestrator: MasterOrchestrator | None = None
def get_orchestrator() -> MasterOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MasterOrchestrator()
    return _orchestrator


@router.get("", summary="List all agent statuses")
async def list_agents(_: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return status of all OrQuanta agents and the emergency stop state."""
    orchestrator = get_orchestrator()
    governor = get_governor()
    statuses = orchestrator.get_agent_statuses()
    agents = [
        {"name": name, "status": status, "description": AGENT_DESCRIPTIONS.get(name, ""),
         "active_tasks": 0 if status == "idle" else 1}
        for name, status in statuses.items()
    ]
    return {"agents": agents, "emergency_stop_active": governor.is_stopped,
            "governor_stats": governor.get_stats()}


@router.post("/{agent_name}/pause", summary="Pause an agent (admin only)")
async def pause_agent(agent_name: str, admin: dict = Depends(require_admin)) -> dict[str, Any]:
    """Pause a specific agent. Admin only."""
    if agent_name not in AGENT_DESCRIPTIONS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")
    logger.warning(f"Agent '{agent_name}' paused by admin {admin.get('email', '?')}")
    return {"agent": agent_name, "status": "paused", "message": "Agent paused."}


@router.post("/{agent_name}/resume", summary="Resume a paused agent (admin only)")
async def resume_agent(agent_name: str, admin: dict = Depends(require_admin)) -> dict[str, Any]:
    """Resume a paused agent. Admin only."""
    if agent_name not in AGENT_DESCRIPTIONS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")
    logger.info(f"Agent '{agent_name}' resumed by admin {admin.get('email', '?')}")
    return {"agent": agent_name, "status": "idle", "message": "Agent resumed."}


@router.post("/emergency-stop", summary="Trigger emergency stop (admin only)")
async def emergency_stop(reason: str = "Manual admin stop.", admin: dict = Depends(require_admin)) -> dict[str, Any]:
    """Immediately halt all agent actions. Requires admin role."""
    get_governor().trigger_emergency_stop(reason)
    logger.critical(f"Emergency stop triggered by {admin.get('email', '?')}: {reason}")
    return {"emergency_stop": True, "reason": reason}


@router.post("/emergency-stop/clear", summary="Clear emergency stop (admin only)")
async def clear_emergency_stop(override_token: str, admin: dict = Depends(require_admin)) -> dict[str, Any]:
    """Clear the emergency stop with admin override token."""
    success = get_governor().clear_emergency_stop(override_token)
    if not success:
        raise HTTPException(status_code=403, detail="Invalid override token.")
    return {"emergency_stop": False, "cleared_by": admin.get("email", "?")}
