"""OrQuanta Agentic v1.0 — Jobs Router (CRUD /api/v1/jobs)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..middleware.auth import get_current_user
from ..middleware.rate_limit import rate_limit_dependency
from ..models.schemas import JobCreateRequest, JobListResponse
from ...agents.scheduler_agent import SchedulerAgent

logger = logging.getLogger("orquanta.routers.jobs")
router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])

_scheduler: SchedulerAgent | None = None


def get_scheduler() -> SchedulerAgent:
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerAgent()
    return _scheduler


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create and schedule a GPU job",
)
async def create_job(
    request: JobCreateRequest,
    user: dict = Depends(get_current_user),
    _: None = Depends(rate_limit_dependency),
) -> dict[str, Any]:
    """Schedule a GPU job directly (without a high-level goal).
    
    The SchedulerAgent will score priority, bin-pack into existing GPUs,
    or provision new instances as needed.
    """
    scheduler = get_scheduler()
    result = await scheduler.schedule_job(
        intent=request.intent,
        required_vram_gb=request.required_vram_gb,
        gpu_type=request.gpu_type,
        provider=request.provider,
        gpu_count=request.gpu_count,
        user_id=user["sub"],
        max_cost_usd=request.max_cost_usd,
        max_runtime_minutes=request.max_runtime_minutes,
    )
    logger.info(f"Job created: {result['job_id']} for user {user.get('email', '?')}")
    return result


@router.get(
    "",
    summary="List GPU jobs",
)
async def list_jobs(
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """List GPU jobs for the current user with optional status filtering."""
    scheduler = get_scheduler()
    user_id = user["sub"] if user.get("role") != "admin" else None
    jobs = scheduler.list_jobs(user_id=user_id, status=status_filter)
    paginated = jobs[offset : offset + limit]
    return {
        "jobs": paginated,
        "total": len(jobs),
        "offset": offset,
        "limit": limit,
        "queue_status": scheduler.get_queue_status(),
    }


@router.get(
    "/{job_id}",
    summary="Get job details",
)
async def get_job(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get detailed status and metadata for a specific job."""
    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


@router.delete(
    "/{job_id}",
    summary="Cancel a GPU job",
)
async def cancel_job(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Cancel a queued or running job. Running jobs will be terminated."""
    scheduler = get_scheduler()
    result = await scheduler.cancel_job(job_id)
    if result.get("error") == "job_not_found":
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return result


@router.get(
    "/queue/status",
    summary="Get scheduler queue and bin status",
)
async def queue_status(
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the current scheduler queue depth, active bins, and GPU utilization."""
    return get_scheduler().get_queue_status()
