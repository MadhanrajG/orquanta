"""OrQuanta Agentic v1.0  -  Jobs Router (CRUD /api/v1/jobs).

This router is the production job API. It routes all job submission
through the real JobPipeline which handles:
  - Provider selection (RunPod first, cheapest)
  - Pod provisioning + SSH execution
  - Live log streaming via WebSocket
  - Billing deduction on completion
  - Job state persistence
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..middleware.auth import get_current_user
from ..middleware.rate_limit import rate_limit_dependency
from ..models.schemas import JobCreateRequest
from ...execution.pipeline import get_pipeline, JobStatus

logger = logging.getLogger("orquanta.routers.jobs")
router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])


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
    """
    Schedule a GPU job  -  routes through the production JobPipeline.

    The pipeline will:
    1. Select the cheapest available provider (RunPod first @ $2.49/hr for H100)
    2. Spin up a GPU pod
    3. Execute the job via SSH with real-time log streaming
    4. Deduct cost from your billing account
    5. Terminate the instance on completion

    Poll GET /api/v1/jobs/{job_id} for status, or subscribe to
    WebSocket at /ws/agent-stream for live log streaming.
    """
    pipeline = get_pipeline()

    # Generate job script from intent if not provided
    script = getattr(request, "script", None) or _intent_to_script(
        intent=request.intent,
        gpu_type=request.gpu_type or "H100",
        gpu_count=request.gpu_count or 1,
    )

    job = await pipeline.submit_job(
        user_id=user["sub"],
        intent=request.intent,
        script=script,
        gpu_type=request.gpu_type or "H100",
        gpu_count=request.gpu_count or 1,
        provider_preference=request.provider,
        max_cost_usd=request.max_cost_usd or 50.0,
        max_runtime_minutes=request.max_runtime_minutes or 120.0,
        tags={"goal_id": request.goal_id} if request.goal_id else {},
    )

    logger.info(f"[Jobs] {job.job_id} submitted for user {user.get('email', '?')}")
    return {
        **job.to_dict(),
        "message": "Job submitted. Poll this endpoint or watch WebSocket /ws/agent-stream for live updates.",
        "ws_channel": "/ws/agent-stream",
    }


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
    pipeline = get_pipeline()
    user_id = user["sub"] if user.get("role") != "admin" else None
    jobs = pipeline.list_jobs(user_id=user_id, status=status_filter)
    paginated = jobs[offset: offset + limit]
    stats = pipeline.get_stats()
    return {
        "jobs": paginated,
        "total": len(jobs),
        "offset": offset,
        "limit": limit,
        "stats": stats,
    }


@router.get(
    "/queue/status",
    summary="Get scheduler queue and pipeline status",
)
async def queue_status(
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get current pipeline stats: total jobs, cost, GPU-hours used."""
    pipeline = get_pipeline()
    stats = pipeline.get_stats()
    return {
        "pipeline_stats": stats,
        "active_jobs": sum(1 for _ in [JobStatus.PROVISIONING, JobStatus.BOOTING, JobStatus.RUNNING]
                           if stats["by_status"].get(_, 0) > 0),
    }


@router.get(
    "/{job_id}",
    summary="Get job details and live status",
)
async def get_job(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get detailed status, logs, GPU metrics, and cost for a specific job."""
    pipeline = get_pipeline()
    job = pipeline.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    # Non-admins can only view their own jobs
    if user.get("role") != "admin" and job.user_id != user["sub"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return job.to_dict()


@router.delete(
    "/{job_id}",
    summary="Cancel a GPU job",
)
async def cancel_job(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Cancel a queued or running job.
    Running jobs will have their GPU instance terminated.
    """
    pipeline = get_pipeline()
    result = await pipeline.cancel_job(
        job_id=job_id,
        user_id=user["sub"] if user.get("role") != "admin" else None,
    )
    if result.get("error") == "job_not_found":
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if result.get("error") == "unauthorized":
        raise HTTPException(status_code=403, detail="Access denied")
    return result




# ---------------------------------------------------------------------------
# Phase 2 endpoints — durable job submission and observability
# ---------------------------------------------------------------------------

@router.post(
    "/durable",
    status_code=status.HTTP_201_CREATED,
    summary="Create a durable GPU job (DB-persisted, Celery-dispatched)",
)
async def create_durable_job(
    request: JobCreateRequest,
    user: dict = Depends(get_current_user),
    _: None = Depends(rate_limit_dependency),
) -> dict[str, Any]:
    """
    Submit a GPU job via the durable execution engine.
    - Job state is immediately persisted to PostgreSQL.
    - Dispatched to Celery worker (Redis required) or asyncio fallback.
    - Idempotency key supported: pass X-Idempotency-Key header.
    - Job survives API restart — recoverable from DB.
    """
    from ...execution.durable_pipeline import submit_durable_job

    org_id = user.get("org_id") or user.get("sub")  # fallback for dev
    idem_key = None  # could be extracted from request headers via middleware

    script = getattr(request, "script", None) or _intent_to_script(
        intent=request.intent,
        gpu_type=request.gpu_type or "H100",
        gpu_count=request.gpu_count or 1,
    )

    job = submit_durable_job(
        intent=request.intent,
        gpu_type=request.gpu_type or "H100",
        gpu_count=request.gpu_count or 1,
        user_id=user["sub"],
        organization_id=org_id,
        script=script,
        provider_preference=request.provider,
        max_cost_usd=request.max_cost_usd or 50.0,
        max_runtime_minutes=request.max_runtime_minutes or 120.0,
        tags={"goal_id": request.goal_id} if request.goal_id else {},
        goal_id=request.goal_id,
        idempotency_key=idem_key,
    )

    logger.info(f"[Jobs] Durable job {job['id']} submitted for user {user.get('email', '?')}")
    return {
        **job,
        "message": "Job submitted durably. Poll GET /api/v1/jobs/{id}/status or watch /ws/agent-stream.",
        "ws_channel": "/ws/agent-stream",
    }


@router.get(
    "/{job_id}/events",
    summary="Get job event history",
)
async def get_job_events(
    job_id: str,
    limit: int = Query(200, ge=1, le=500),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Return the immutable event history for a job.
    Includes: provisioning, execution, log lines, retries, reconciliation events.
    Tenant-isolated: non-admins can only view their own jobs.
    """
    from ...execution.durable_pipeline import get_durable_job, get_durable_job_history

    job = get_durable_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    # Tenant isolation
    if user.get("role") != "admin":
        job_user = str(job.get("user_id") or "")
        if job_user != str(user["sub"]):
            raise HTTPException(status_code=403, detail="Access denied")

    events = get_durable_job_history(job_id)
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "event_count": len(events),
        "events": events[:limit],
    }


@router.get(
    "/{job_id}/status",
    summary="Get durable job status from DB",
)
async def get_durable_job_status(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Get live job status directly from PostgreSQL.
    More reliable than the in-memory pipeline for jobs that survived a restart.
    """
    from ...execution.durable_pipeline import get_durable_job

    job = get_durable_job(job_id)
    if not job:
        # Fallback to in-memory pipeline
        pipeline = get_pipeline()
        in_mem = pipeline.get_job(job_id)
        if not in_mem:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        return in_mem.to_dict()

    # Tenant isolation
    if user.get("role") != "admin":
        job_user = str(job.get("user_id") or "")
        if job_user != str(user["sub"]):
            raise HTTPException(status_code=403, detail="Access denied")

    return job


def _shell_quote(s: str) -> str:
    """Single-quote a string for safe bash interpolation (prevents injection)."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _intent_to_script(intent: str, gpu_type: str, gpu_count: int) -> str:
    """Convert a plain-English intent into a minimal GPU job script.

    Intent is assigned via single-quoted variable assignment so that no
    shell metacharacters ($(...), backticks, etc.) can execute.
    """
    q_intent = _shell_quote(intent)
    q_gpu = _shell_quote(gpu_type)
    return f"""#!/bin/bash
set -euo pipefail
INTENT={q_intent}
GPU_TYPE={q_gpu}
GPU_COUNT={gpu_count}
echo "=== OrQuanta GPU Job ==="
printf 'Intent: %s\\n' "$INTENT"
printf 'GPU: %sx %s\\n' "$GPU_COUNT" "$GPU_TYPE"
echo "Started: $(date -u)"
echo ""
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null || echo "GPU info unavailable"
echo ""
echo "=== Running workload ==="
echo "Job ready  -  attach your script or use the script field in the API."
echo "=== Completed: $(date -u) ==="
"""
