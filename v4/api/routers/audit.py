"""OrQuanta Agentic v1.0 — Audit Router."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, Query
from ..middleware.auth import get_current_user, require_admin
from ...agents.safety_governor import get_governor

router = APIRouter(prefix="/api/v1/audit", tags=["Audit"])


@router.get("", summary="Get audit log (paginated)")
async def get_audit_log(
    agent: str | None = Query(None, description="Filter by agent name"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the full audit trail of all agent decisions and actions.
    
    Every action taken by any agent — from provisioning instances to
    sending alerts — is logged here with its reasoning and outcome.
    """
    governor = get_governor()
    entries = governor.get_audit_log(agent_filter=agent, limit=limit, offset=offset)
    return {
        "entries": entries,
        "total": len(governor._audit_log),
        "offset": offset,
        "limit": limit,
        "filtered_by_agent": agent,
    }


@router.get("/spend", summary="Get spend summary (admin only)")
async def get_spend_summary(admin: dict = Depends(require_admin)) -> dict[str, Any]:
    """Return current platform spend summary against safety caps. Admin only."""
    return get_governor().get_spend_summary()


@router.get("/stats", summary="Get governor statistics")
async def get_governor_stats(_: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return Safety Governor statistics: total actions, spend, emergency stop status."""
    return get_governor().get_stats()
