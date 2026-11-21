"""
OrQuanta — Celery GPU Job Tasks
================================
Async GPU job execution via Celery workers.

CRITICAL SAFETY RULE: Never execute a GPU workload twice.
- Idempotency is enforced at job_db.create_job via the idempotency_key column.
- Before provisioning, we check the job status is still 'queued'.
- Retries use exponential backoff with jitter and only retry on transient errors.
- Billable GPU provisioning is NOT retried on the same job_id once instance_id is set.
"""
from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from .celery_app import celery_app
from .job_db import (
    append_job_event,
    get_job,
    update_job_status,
)

logger = logging.getLogger("orquanta.execution.tasks")

PIPELINE_MOCK = os.getenv("USE_REAL_PROVIDERS", "false").lower() != "true"


# ---------------------------------------------------------------------------
# Base task class with structured logging
# ---------------------------------------------------------------------------

class JobTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = kwargs.get("job_id") or (args[0] if args else "unknown")
        logger.error(f"[Task] FAILED job={job_id} task={task_id} exc={exc}")
        try:
            update_job_status(
                job_id,
                "failed",
                failure_reason=f"Worker task failure: {exc}",
            )
            append_job_event(
                job_id,
                event_type="task_failed",
                status="failed",
                message=f"Celery task failed: {exc}",
                agent="celery_worker",
            )
        except Exception as inner:
            logger.error(f"[Task] Failed to persist failure for job {job_id}: {inner}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        job_id = kwargs.get("job_id") or (args[0] if args else "unknown")
        retry_num = self.request.retries
        logger.warning(f"[Task] RETRY {retry_num} job={job_id} task={task_id} exc={exc}")
        try:
            append_job_event(
                job_id,
                event_type="task_retry",
                message=f"Retry {retry_num}: {exc}",
                payload={"retry": retry_num},
                agent="celery_worker",
            )
            update_job_status(job_id, "queued", increment_retry=True)
        except Exception as inner:
            logger.error(f"[Task] Failed to record retry for {job_id}: {inner}")


# ---------------------------------------------------------------------------
# Main GPU job execution task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    base=JobTask,
    name="v4.execution.tasks.execute_gpu_job",
    queue="orquanta.jobs",
    max_retries=3,
    # No auto-retry — we handle retries explicitly to avoid duplicate billing
    autoretry_for=(),
    soft_time_limit=7200,
    time_limit=7500,
    acks_late=True,
    reject_on_worker_lost=True,
    track_started=True,
)
def execute_gpu_job(
    self: Task,
    job_id: str,
    intent: str,
    gpu_type: str,
    gpu_count: int,
    script: str = "",
    provider_preference: str | None = None,
    max_cost_usd: float = 50.0,
    max_runtime_minutes: float = 120.0,
    tags: dict | None = None,
) -> dict[str, Any]:
    """
    Execute a GPU job end-to-end.

    This task is idempotent at the job level:
    - If the job is not in 'queued' state, we abort without provisioning.
    - GPU provisioning is a one-shot operation guarded by state machine transition.
    - Retries only occur on transient infrastructure errors BEFORE billable provisioning.
    """
    task_id = self.request.id
    logger.info(f"[Task] Starting job={job_id} task={task_id}")

    # --- Step 1: Verify job is still queued (guard against duplicate dispatch) ---
    job = get_job(job_id)
    if not job:
        logger.error(f"[Task] Job {job_id} not found in DB — aborting.")
        return {"status": "aborted", "reason": "job_not_found"}

    if job["status"] != "queued":
        logger.warning(
            f"[Task] Job {job_id} is in status '{job['status']}', not 'queued'. "
            f"Skipping execution to prevent duplicate billing."
        )
        return {"status": "skipped", "reason": f"already_{job['status']}"}

    # --- Step 2: Mark as provisioning (atomic state transition) ---
    transitioned = update_job_status(
        job_id,
        "provisioning",
        celery_task_id=task_id,
    )
    if not transitioned:
        logger.warning(f"[Task] Job {job_id} could not transition to provisioning — another worker took it.")
        return {"status": "skipped", "reason": "race_condition"}

    append_job_event(
        job_id, "provisioning_started",
        message=f"Worker {task_id} began provisioning",
        status="provisioning",
        agent="celery_worker",
    )

    t0 = time.time()
    instance_id: str = ""
    provider_name: str = provider_preference or "runpod"
    hourly_rate: float = 0.0
    region: str = "US-TX-3"

    try:
        # --- Step 3: Provision GPU (non-retriable once billable resource exists) ---
        if PIPELINE_MOCK:
            instance_id, hourly_rate, region = _mock_provision(job_id, gpu_type, gpu_count, provider_preference)
        else:
            instance_id, provider_name, hourly_rate, region = _real_provision(
                job_id, gpu_type, gpu_count, provider_preference, max_cost_usd, max_runtime_minutes
            )

        update_job_status(
            job_id,
            "booting",
            provider_job_id=instance_id,
            region=region,
            hourly_rate_usd=hourly_rate,
        )
        append_job_event(
            job_id, "provisioned",
            message=f"Instance {instance_id} launched on {provider_name} @ ${hourly_rate:.3f}/hr",
            status="booting",
            payload={"instance_id": instance_id, "provider": provider_name, "hourly_rate": hourly_rate, "region": region},
            agent="celery_worker",
        )

        # --- Step 4: Wait for boot / execute job ---
        update_job_status(job_id, "running")
        append_job_event(job_id, "job_running", message="Job started on GPU", status="running", agent="celery_worker")

        if PIPELINE_MOCK:
            exit_code, stdout, peak_util, peak_mem = _mock_execute(job_id, intent, gpu_type, gpu_count)
        else:
            exit_code, stdout, peak_util, peak_mem = _real_execute(
                job_id, instance_id, provider_name, script, max_runtime_minutes
            )

        # --- Step 5: Calculate cost ---
        duration = time.time() - t0
        cost_usd = (duration / 3600.0) * hourly_rate * gpu_count

        # --- Step 6: Mark complete ---
        update_job_status(
            job_id,
            "completing",
        )
        final_status = "completed" if exit_code == 0 else "failed"
        update_job_status(
            job_id,
            final_status,
            exit_code=exit_code,
            cost_usd=cost_usd,
            duration_seconds=duration,
            gpu_peak_util_pct=peak_util,
            gpu_peak_mem_gb=peak_mem,
            failure_reason=None if exit_code == 0 else f"Job exited with code {exit_code}",
        )
        append_job_event(
            job_id,
            "job_completed" if exit_code == 0 else "job_failed",
            message=f"Exit={exit_code} duration={duration:.1f}s cost=${cost_usd:.4f}",
            status=final_status,
            payload={"exit_code": exit_code, "cost_usd": cost_usd, "duration_seconds": duration},
            agent="celery_worker",
        )
        logger.info(f"[Task] Job {job_id} {final_status} exit={exit_code} cost=${cost_usd:.4f}")
        return {"status": final_status, "exit_code": exit_code, "cost_usd": cost_usd}

    except SoftTimeLimitExceeded:
        duration = time.time() - t0
        logger.warning(f"[Task] Job {job_id} hit soft time limit after {duration:.0f}s")
        update_job_status(job_id, "failed", failure_reason="Exceeded maximum runtime limit")
        append_job_event(job_id, "timeout", status="failed", message="Soft time limit exceeded", agent="celery_worker")
        _safe_terminate(instance_id, provider_name)
        return {"status": "failed", "reason": "timeout"}

    except _TransientError as exc:
        # Transient error BEFORE provisioning — safe to retry
        if not instance_id:
            backoff = _jitter_backoff(self.request.retries)
            logger.warning(f"[Task] Transient error (pre-provision) job={job_id}: {exc}. Retrying in {backoff:.1f}s")
            update_job_status(job_id, "queued", increment_retry=True)
            raise self.retry(exc=exc, countdown=backoff, max_retries=3)
        else:
            # Billable resource already exists — do not retry, fail safely
            logger.error(f"[Task] Transient error AFTER provision for job={job_id}: {exc}. NOT retrying (billable resource exists).")
            duration = time.time() - t0
            cost_usd = (duration / 3600.0) * hourly_rate * gpu_count
            update_job_status(
                job_id, "failed",
                failure_reason=f"Infrastructure error after provisioning: {exc}",
                cost_usd=cost_usd,
                duration_seconds=duration,
            )
            _safe_terminate(instance_id, provider_name)
            return {"status": "failed", "reason": str(exc)}

    except Exception as exc:
        duration = time.time() - t0
        cost_usd = (duration / 3600.0) * hourly_rate * gpu_count if hourly_rate else 0.0
        logger.error(f"[Task] Unhandled error job={job_id}: {exc}", exc_info=True)
        update_job_status(
            job_id, "failed",
            failure_reason=str(exc),
            cost_usd=cost_usd if cost_usd else None,
            duration_seconds=duration,
        )
        append_job_event(job_id, "task_error", status="failed", message=str(exc), agent="celery_worker")
        _safe_terminate(instance_id, provider_name)
        return {"status": "failed", "reason": str(exc)}


# ---------------------------------------------------------------------------
# Sentinel task: cancel a running job
# ---------------------------------------------------------------------------

@celery_app.task(
    name="v4.execution.tasks.cancel_job",
    queue="orquanta.jobs",
    max_retries=1,
    soft_time_limit=30,
)
def cancel_job(job_id: str, requested_by: str = "user") -> dict:
    """Mark a job as cancelled and terminate its cloud instance."""
    job = get_job(job_id)
    if not job:
        return {"status": "not_found"}

    if job["status"] in ("completed", "failed", "cancelled"):
        return {"status": "already_terminal", "current_status": job["status"]}

    update_job_status(job_id, "cancelled", failure_reason=f"Cancelled by {requested_by}")
    append_job_event(
        job_id, "cancelled",
        message=f"Job cancelled by {requested_by}",
        status="cancelled",
        agent="celery_worker",
    )

    instance_id = job.get("provider_job_id", "")
    provider = job.get("provider", "runpod")
    _safe_terminate(instance_id, provider)

    return {"status": "cancelled"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _TransientError(Exception):
    """Signals a transient infrastructure error that is safe to retry."""


def _jitter_backoff(retry_num: int, base: float = 10.0, cap: float = 300.0) -> float:
    """Exponential backoff with full jitter: uniform(0, min(cap, base * 2^n))."""
    ceiling = min(cap, base * (2 ** retry_num))
    return random.uniform(0, ceiling)


def _safe_terminate(instance_id: str, provider: str) -> None:
    """Best-effort instance termination — never raises."""
    if not instance_id or PIPELINE_MOCK:
        return
    try:
        import asyncio
        from ..providers.provider_router import get_router
        loop = asyncio.new_event_loop()
        router = get_router()
        p = router._providers.get(provider)
        if p:
            loop.run_until_complete(p.terminate(instance_id))
            logger.info(f"[Task] Terminated {provider}/{instance_id}")
        loop.close()
    except Exception as exc:
        logger.error(f"[Task] Failed to terminate {provider}/{instance_id}: {exc}")


def _mock_provision(
    job_id: str, gpu_type: str, gpu_count: int, provider_preference: str | None
) -> tuple[str, float, str]:
    """Return a mock instance tuple (instance_id, hourly_rate, region)."""
    import uuid as _uuid
    rates = {"H100": 2.49, "A100": 1.44, "RTX 4090": 0.74, "T4": 0.26}
    rate = rates.get(gpu_type, 1.44)
    mock_id = f"mock-{_uuid.uuid4().hex[:10]}"
    logger.info(f"[Task] MOCK provision job={job_id} instance={mock_id} @ ${rate}/hr")
    return mock_id, rate, "US-TX-3"


def _mock_execute(
    job_id: str, intent: str, gpu_type: str, gpu_count: int
) -> tuple[int, str, float, float]:
    """Simulate job execution with realistic delay. Returns (exit_code, stdout, peak_util, peak_mem)."""
    log_lines = [
        f"[OrQuanta] Starting job {job_id}",
        f"[OrQuanta] GPU: {gpu_count}x {gpu_type} | MOCK mode",
        "[STDOUT] CUDA 12.1 initialized",
        "[STDOUT] Model loaded: 13.4B parameters",
        "[STDOUT] Training: Epoch 1/3 | Loss: 2.84 | GPU Util: 94%",
        "[STDOUT] Training: Epoch 2/3 | Loss: 1.98 | GPU Util: 97%",
        "[STDOUT] Training: Epoch 3/3 | Loss: 1.42 | GPU Util: 96%",
        "[STDOUT] Job completed successfully",
    ]
    for line in log_lines:
        time.sleep(1.5)
        append_job_event(job_id, "log_line", message=line, agent="celery_worker")

    return 0, "\n".join(log_lines), 95.0 + random.uniform(-5, 3), 72.5


def _real_provision(
    job_id: str,
    gpu_type: str,
    gpu_count: int,
    provider_preference: str | None,
    max_cost_usd: float,
    max_runtime_minutes: float,
) -> tuple[str, str, float, str]:
    """Real GPU provisioning via ProviderRouter. Returns (instance_id, provider, hourly_rate, region)."""
    import asyncio
    from ..providers.provider_router import get_router
    from ..providers.base_provider import InsufficientCapacityError

    budget_hr = max_cost_usd / max(max_runtime_minutes / 60.0, 0.5)
    loop = asyncio.new_event_loop()
    try:
        router = get_router()
        instance, _ = loop.run_until_complete(
            router.spin_up_cheapest(
                gpu_type=gpu_type,
                gpu_count=gpu_count,
                spot=True,
                tags={"orquanta_job": job_id},
                budget_usd_hr=budget_hr,
            )
        )
        return instance.instance_id, instance.provider, instance.hourly_cost_usd, instance.region
    except InsufficientCapacityError as exc:
        raise _TransientError(f"No GPU capacity: {exc}") from exc
    finally:
        loop.close()


def _real_execute(
    job_id: str,
    instance_id: str,
    provider: str,
    script: str,
    max_runtime_minutes: float,
) -> tuple[int, str, float, float]:
    """Execute job on a provisioned instance. Returns (exit_code, stdout, peak_util, peak_mem)."""
    import asyncio
    from ..execution.pipeline import get_pipeline

    loop = asyncio.new_event_loop()
    try:
        pipeline = get_pipeline()

        def _log_cb(j_id: str, stream: str, line: str):
            append_job_event(j_id, "log_line", message=f"[{stream}] {line}", agent="celery_worker")

        from ..execution.pipeline import PipelineJob, JobStatus
        fake_job = PipelineJob(
            job_id=job_id,
            user_id="system",
            intent="celery-task",
            gpu_type="H100",
            gpu_count=1,
            provider=provider,
            instance_id=instance_id,
            script=script,
        )
        result = loop.run_until_complete(
            pipeline._run_container_job(fake_job, _log_cb, max_runtime_minutes)
        )
        return result
    finally:
        loop.close()
