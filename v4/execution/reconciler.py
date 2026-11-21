"""
OrQuanta — Job Reconciler (Celery Beat Tasks)
==============================================
Periodic tasks that ensure consistency between DB state and actual provider state.

Runs every 60s via celery beat. Safe to run on multiple beat instances
(uses DB-level locking / idempotent updates to avoid duplicate actions).
"""
from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger("orquanta.execution.reconciler")

PIPELINE_MOCK = os.getenv("USE_REAL_PROVIDERS", "false").lower() != "true"

try:
    from .celery_app import celery_app
    from .job_db import (
        list_stuck_jobs,
        update_job_status,
        append_job_event,
        _get_conn,
        PH,
        USE_PG,
    )
    _CELERY_AVAILABLE = True
except Exception as _e:
    logger.warning(f"[Reconciler] Celery not available: {_e}")
    _CELERY_AVAILABLE = False


if _CELERY_AVAILABLE:

    @celery_app.task(
        name="v4.execution.reconciler.reconcile_stuck_jobs",
        queue="orquanta.ops",
        max_retries=1,
        soft_time_limit=55,
    )
    def reconcile_stuck_jobs() -> dict:
        """
        Find jobs stuck in non-terminal states for > 30 minutes and reconcile them.

        Actions taken:
        - If the provider instance is still running: update DB to match.
        - If the provider instance is gone: mark job as failed with failure_reason.
        - If MOCK mode: auto-recover mock stuck jobs.

        Returns a summary dict for Celery result storage.
        """
        stuck = list_stuck_jobs(stuck_minutes=30)
        if not stuck:
            return {"checked": 0, "recovered": 0, "failed": 0}

        logger.warning(f"[Reconciler] Found {len(stuck)} stuck jobs")
        recovered = 0
        failed_count = 0

        for job in stuck:
            job_id = job["id"]
            status = job["status"]
            instance_id = job.get("provider_job_id", "")
            provider = job.get("provider", "runpod")

            try:
                if PIPELINE_MOCK or not instance_id:
                    # In mock mode, stuck jobs are auto-failed after reconcile window
                    ok = update_job_status(
                        job_id, "failed",
                        failure_reason=f"Reconciler: job stuck in '{status}' for >30m (mock mode)",
                    )
                    if ok:
                        append_job_event(
                            job_id, "reconciled_failed",
                            message=f"Reconciler marked stuck job as failed (mock mode)",
                            status="failed",
                            agent="reconciler",
                        )
                        failed_count += 1
                else:
                    # Real mode: query provider for actual instance state
                    provider_status = _query_provider_instance(provider, instance_id)

                    if provider_status == "running":
                        # Instance is still alive — job may still be running
                        # Extend visibility timeout by updating a heartbeat field
                        append_job_event(
                            job_id, "reconciler_checked",
                            message=f"Reconciler: instance {instance_id} still running on {provider}",
                            status=status,
                            payload={"provider_status": "running"},
                            agent="reconciler",
                        )
                        logger.info(f"[Reconciler] Job {job_id} instance still running — no action")

                    elif provider_status in ("terminated", "not_found", "error"):
                        # Instance gone — mark job as failed
                        ok = update_job_status(
                            job_id, "failed",
                            failure_reason=f"Reconciler: instance {instance_id} not found on {provider} (status={provider_status})",
                        )
                        if ok:
                            append_job_event(
                                job_id, "reconciled_failed",
                                message=f"Reconciler: instance gone on {provider}",
                                status="failed",
                                payload={"instance_id": instance_id, "provider_status": provider_status},
                                agent="reconciler",
                            )
                            failed_count += 1
                            logger.warning(f"[Reconciler] Job {job_id} marked failed — instance gone")

            except Exception as exc:
                logger.error(f"[Reconciler] Error reconciling job {job_id}: {exc}")

        logger.info(f"[Reconciler] Done: {len(stuck)} checked, {recovered} recovered, {failed_count} failed")
        return {"checked": len(stuck), "recovered": recovered, "failed": failed_count}


    @celery_app.task(
        name="v4.execution.reconciler.flush_outbox",
        queue="orquanta.ops",
        max_retries=1,
        soft_time_limit=9,
    )
    def flush_outbox() -> dict:
        """
        Transactional outbox relay: publish unpublished outbox events to Celery.
        Runs every 10s. Guarantees that DB-committed job state changes are
        eventually dispatched to Celery even if the initial dispatch failed.
        """
        from .tasks import execute_gpu_job

        conn = _get_conn()
        dispatched = 0
        errors = 0
        try:
            cur = conn.cursor()
            if USE_PG:
                cur.execute(
                    """SELECT id, aggregate_id, event_type, payload
                       FROM outbox_events
                       WHERE NOT published
                       ORDER BY id ASC
                       LIMIT 50
                       FOR UPDATE SKIP LOCKED"""
                )
            else:
                cur.execute(
                    """SELECT id, aggregate_id, event_type, payload
                       FROM outbox_events
                       WHERE published = 0
                       ORDER BY id ASC
                       LIMIT 50"""
                )

            rows = cur.fetchall()
            if not rows:
                conn.close()
                return {"dispatched": 0, "errors": 0}

            for row in rows:
                d = dict(row)
                try:
                    payload = json.loads(d.get("payload") or "{}")
                    event_type = d["event_type"]

                    if event_type == "submit_job":
                        execute_gpu_job.apply_async(
                            kwargs=payload,
                            task_id=payload.get("task_id"),
                            queue="orquanta.jobs",
                        )
                    # Mark as published
                    now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    if USE_PG:
                        cur.execute(
                            "UPDATE outbox_events SET published = TRUE, published_at = %s WHERE id = %s",
                            (now_str, d["id"]),
                        )
                    else:
                        cur.execute(
                            "UPDATE outbox_events SET published = 1, published_at = ? WHERE id = ?",
                            (now_str, d["id"]),
                        )
                    dispatched += 1
                except Exception as exc:
                    logger.error(f"[Outbox] Failed to dispatch event {d.get('id')}: {exc}")
                    errors += 1

            conn.commit()
        except Exception as exc:
            logger.error(f"[Outbox] flush_outbox failed: {exc}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            conn.close()

        return {"dispatched": dispatched, "errors": errors}


def _query_provider_instance(provider: str, instance_id: str) -> str:
    """
    Query a provider for the real-time status of an instance.
    Returns: 'running', 'terminated', 'not_found', 'error'
    """
    try:
        import asyncio
        from ..providers.provider_router import get_router
        loop = asyncio.new_event_loop()
        router = get_router()
        p = router._providers.get(provider)
        if not p:
            return "not_found"
        # Try to get instance status — provider-specific
        status = loop.run_until_complete(_async_get_instance_status(p, instance_id))
        loop.close()
        return status
    except Exception as exc:
        logger.error(f"[Reconciler] Provider query error for {provider}/{instance_id}: {exc}")
        return "error"


async def _async_get_instance_status(provider, instance_id: str) -> str:
    """Call provider-specific status check."""
    try:
        # RunPod: check pod status
        if hasattr(provider, "get_pod_status"):
            status = await provider.get_pod_status(instance_id)
            if status in ("RUNNING", "running"):
                return "running"
            if status in ("EXITED", "TERMINATED", "DEAD", None, ""):
                return "terminated"
            return "terminated"
        # Generic: try terminate (idempotent) and treat as not_found
        return "not_found"
    except Exception:
        return "error"
