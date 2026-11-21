"""
OrQuanta — Durable Job Submission Bridge
=========================================
This module wraps the existing JobPipeline.submit_job() with:
1. Persistent job creation in PostgreSQL (via job_db.create_job)
2. Outbox event insertion (transactional guarantee for Celery dispatch)
3. Fallback to asyncio background task (when Celery/Redis unavailable)

Existing pipeline in-memory dict is kept for backward compatibility with
routes that call pipeline.get_job() during development/mock mode.
PostgreSQL is the authoritative state once a job is persisted.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from .job_db import (
    append_job_event,
    create_job,
    get_job,
    get_job_events,
    insert_outbox_event,
    update_job_status,
    list_stuck_jobs,
)

logger = logging.getLogger("orquanta.execution.durable_pipeline")

REDIS_URL = os.getenv("REDIS_URL", "")
CELERY_ENABLED = bool(REDIS_URL) and os.getenv("CELERY_ENABLED", "true").lower() != "false"


def submit_durable_job(
    *,
    intent: str,
    gpu_type: str,
    gpu_count: int,
    user_id: str,
    organization_id: str,
    script: str = "",
    provider_preference: str | None = None,
    max_cost_usd: float = 50.0,
    max_runtime_minutes: float = 120.0,
    tags: dict | None = None,
    goal_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """
    Create a durable job record and dispatch for execution.

    Guarantees:
    - Job is persisted to PostgreSQL before dispatch.
    - Idempotency: same idempotency_key returns existing job, never creates duplicate.
    - Dispatch: via Celery (if Redis available) or asyncio background task.
    - Transactional outbox: Celery dispatch failure leaves outbox event for retry.

    Returns the job dict (status=queued).
    """
    idem_key = idempotency_key or str(uuid.uuid4())

    # 1. Persist to DB (idempotent)
    job = create_job(
        intent=intent,
        gpu_type=gpu_type,
        gpu_count=gpu_count,
        user_id=user_id,
        organization_id=organization_id,
        script=script,
        provider=provider_preference,
        max_cost_usd=max_cost_usd,
        max_runtime_minutes=int(max_runtime_minutes),
        idempotency_key=idem_key,
        metadata={"tags": tags or {}},
        goal_id=goal_id,
    )
    job_id = job["id"]

    # If job already existed (idempotent), return it without re-dispatching
    if job.get("status") != "queued":
        logger.info(f"[DurablePipeline] Job {job_id} already in status '{job['status']}' — returning existing.")
        return job

    # 2. Append creation event
    append_job_event(
        job_id,
        "job_created",
        message=f"Job created: {intent[:80]}",
        status="queued",
        payload={"gpu_type": gpu_type, "gpu_count": gpu_count, "provider": provider_preference},
        agent="api",
    )

    # 3. Dispatch via Celery + outbox, or asyncio fallback
    task_kwargs = {
        "job_id": job_id,
        "intent": intent,
        "gpu_type": gpu_type,
        "gpu_count": gpu_count,
        "script": script,
        "provider_preference": provider_preference,
        "max_cost_usd": max_cost_usd,
        "max_runtime_minutes": max_runtime_minutes,
        "tags": tags or {},
    }

    dispatched_via = "none"
    if CELERY_ENABLED:
        try:
            from .tasks import execute_gpu_job
            result = execute_gpu_job.apply_async(
                kwargs=task_kwargs,
                queue="orquanta.jobs",
            )
            dispatched_via = f"celery:{result.id}"
            logger.info(f"[DurablePipeline] Job {job_id} dispatched via Celery task {result.id}")
        except Exception as exc:
            # Celery dispatch failed — write to outbox for retry
            logger.warning(f"[DurablePipeline] Celery dispatch failed for {job_id}: {exc}. Writing to outbox.")
            insert_outbox_event(
                aggregate_type="job",
                aggregate_id=job_id,
                event_type="submit_job",
                payload=task_kwargs,
            )
            dispatched_via = "outbox"
    else:
        # No Redis/Celery — fall back to asyncio background task (dev mode)
        _dispatch_asyncio_fallback(task_kwargs)
        dispatched_via = "asyncio"

    logger.info(f"[DurablePipeline] Job {job_id} queued, dispatch={dispatched_via}")
    job["dispatch_via"] = dispatched_via
    return job


def _dispatch_asyncio_fallback(task_kwargs: dict) -> None:
    """
    Fallback: dispatch via asyncio.create_task when Celery/Redis unavailable.
    Uses the existing pipeline execution engine.
    """
    import asyncio

    async def _run():
        try:
            from .pipeline import get_pipeline
            pipeline = get_pipeline()
            job_id = task_kwargs["job_id"]
            await pipeline._execute_durable(task_kwargs)
        except Exception as exc:
            logger.error(f"[DurablePipeline] Asyncio fallback failed: {exc}", exc_info=True)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_run())
        else:
            loop.run_until_complete(_run())
    except Exception as exc:
        logger.error(f"[DurablePipeline] Could not dispatch asyncio fallback: {exc}")


def get_durable_job(job_id: str) -> dict | None:
    """
    Retrieve job state from PostgreSQL.
    Falls back to in-memory pipeline state if DB unavailable.
    """
    try:
        job = get_job(job_id)
        if job:
            # Enrich with event history count
            events = get_job_events(job_id, limit=5)
            job["recent_events"] = events
            return job
    except Exception as exc:
        logger.warning(f"[DurablePipeline] DB lookup failed for {job_id}: {exc}")

    # Fallback to in-memory pipeline
    try:
        from .pipeline import get_pipeline
        pipeline_job = get_pipeline().get_job(job_id)
        if pipeline_job:
            return pipeline_job.to_dict()
    except Exception:
        pass

    return None


def get_durable_job_history(job_id: str) -> list[dict]:
    """Return the full event history for a job from the DB."""
    try:
        return get_job_events(job_id, limit=500)
    except Exception as exc:
        logger.warning(f"[DurablePipeline] get_job_history failed: {exc}")
        return []
