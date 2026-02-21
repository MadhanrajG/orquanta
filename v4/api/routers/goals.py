"""OrQuanta Agentic v1.0 — Goals Router (POST /api/v1/goals)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..middleware.auth import get_current_user
from ..middleware.rate_limit import rate_limit_dependency
from ..models.schemas import GoalListResponse, GoalResponse, GoalSubmitRequest
from ...agents.master_orchestrator import MasterOrchestrator

logger = logging.getLogger("orquanta.routers.goals")
router = APIRouter(prefix="/api/v1/goals", tags=["Goals"])

# Shared orchestrator instance (injected via app state in production)
_orchestrator: MasterOrchestrator | None = None


def get_orchestrator() -> MasterOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MasterOrchestrator()
    return _orchestrator


@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a natural-language goal",
    description=(
        "Submit a natural-language goal to the MasterOrchestrator. "
        "The orchestrator will decompose it into tasks and assign them to specialist agents. "
        "Returns a goal_id for polling status."
    ),
)
async def submit_goal(
    request: GoalSubmitRequest,
    user: dict = Depends(get_current_user),
    _: None = Depends(rate_limit_dependency),
) -> dict[str, Any]:
    """Submit a natural-language goal for autonomous agent execution."""
    orchestrator = get_orchestrator()
    
    goal_id = await orchestrator.submit_goal(
        raw_text=request.raw_text,
        user_id=user["sub"],
    )
    
    logger.info(f"Goal submitted: {goal_id} by user {user.get('email', '?')}")
    
    return {
        "goal_id": goal_id,
        "status": "accepted",
        "message": "Goal accepted. Agents are working on it.",
        "polling_url": f"/api/v1/goals/{goal_id}",
        "submitted_at": datetime.now().isoformat(),
    }


@router.get(
    "/{goal_id}",
    response_model=dict,
    summary="Get goal execution status",
)
async def get_goal(
    goal_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the current status and execution plan of a submitted goal."""
    orchestrator = get_orchestrator()
    goal = orchestrator.get_goal_status(goal_id)
    
    if not goal:
        raise HTTPException(status_code=404, detail=f"Goal '{goal_id}' not found.")
    
    return goal


@router.get(
    "",
    response_model=dict,
    summary="List all goals for current user",
)
async def list_goals(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """List all goals submitted by the current user."""
    orchestrator = get_orchestrator()
    goals = orchestrator.get_all_goals(user_id=user["sub"])
    return {
        "goals": goals,
        "total": len(goals),
    }


@router.get(
    "/{goal_id}/reasoning",
    response_model=dict,
    summary="Get full ReAct reasoning log for a goal",
)
async def get_reasoning_log(
    goal_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the full step-by-step ReAct reasoning log for a goal execution."""
    orchestrator = get_orchestrator()
    log = orchestrator.get_reasoning_log(goal_id)
    
    if not log and not orchestrator.get_goal_status(goal_id):
        raise HTTPException(status_code=404, detail=f"Goal '{goal_id}' not found.")
    
    return {
        "goal_id": goal_id,
        "reasoning_steps": len(log),
        "log": log,
    }
