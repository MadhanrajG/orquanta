"""
OrQuanta — Job Database Service
================================
Synchronous (psycopg2/sqlite) job persistence layer used by Celery workers.
Celery workers are synchronous processes — they cannot use asyncio/asyncpg.
This module provides the same operations as JobRepo but over a sync connection.

The FastAPI layer continues to use the async JobRepo (repositories.py).
Both read/write the same PostgreSQL table — PostgreSQL is the single source of truth.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("orquanta.execution.job_db")

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_PG = DATABASE_URL.startswith(("postgresql://", "postgres://"))
_DB_FILE = "./orquanta_local.db"


def _get_conn():
    if USE_PG:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=10,
        )
        conn.autocommit = False
        return conn
    import sqlite3
    conn = sqlite3.connect(_DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


PH = "%s" if USE_PG else "?"


# ---------------------------------------------------------------------------
# Job state transitions (strict machine)
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, set[str]] = {
    "queued":       {"provisioning", "cancelled", "failed"},
    "provisioning": {"booting", "running", "failed", "cancelled"},
    "booting":      {"running", "failed", "cancelled"},
    "running":      {"completing", "completed", "failed", "cancelled"},
    "completing":   {"completed", "failed"},
    "completed":    set(),   # Terminal — no further transitions
    "failed":       set(),   # Terminal — no further transitions
    "cancelled":    set(),   # Terminal — no further transitions
}


def validate_transition(current: str, next_status: str) -> bool:
    allowed = VALID_TRANSITIONS.get(current, set())
    return next_status in allowed


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def get_job(job_id: str) -> dict | None:
    """Fetch a job row by ID. Returns None if not found."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM jobs WHERE id = {PH}", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_job(
    intent: str,
    gpu_type: str,
    gpu_count: int,
    user_id: str,
    organization_id: str,
    script: str = "",
    provider: str | None = None,
    max_cost_usd: float = 50.0,
    max_runtime_minutes: int = 120,
    idempotency_key: str | None = None,
    metadata: dict | None = None,
    goal_id: str | None = None,
) -> dict:
    """
    Insert a new job row with QUEUED status.
    Uses idempotency_key to prevent duplicate creation on retry.
    Returns the job dict (existing or newly created).
    """
    idem_key = idempotency_key or str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_conn()
    try:
        cur = conn.cursor()

        # Check idempotency — return existing job if key already used
        cur.execute(f"SELECT * FROM jobs WHERE idempotency_key = {PH}", (idem_key,))
        existing = cur.fetchone()
        if existing:
            logger.info(f"[JobDB] Idempotent create: job {dict(existing).get('id')} already exists for key {idem_key}")
            return dict(existing)

        meta_json = json.dumps(metadata or {})
        if USE_PG:
            cur.execute(
                """INSERT INTO jobs
                   (id, organization_id, user_id, goal_id, intent, gpu_type, gpu_count,
                    provider, max_cost_usd, max_runtime_minutes, status, script,
                    idempotency_key, job_metadata, created_at, retry_count)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued',%s,%s,%s::jsonb,%s,0)
                   RETURNING *""",
                (job_id, organization_id, user_id, goal_id, intent, gpu_type, gpu_count,
                 provider, max_cost_usd, max_runtime_minutes, script,
                 idem_key, meta_json, now),
            )
            row = cur.fetchone()
        else:
            cur.execute(
                """INSERT INTO jobs
                   (id, organization_id, user_id, goal_id, intent, gpu_type, gpu_count,
                    provider, max_cost_usd, max_runtime_minutes, status, script,
                    idempotency_key, job_metadata, created_at, retry_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?,'queued',?,?,?,?,0)""",
                (job_id, organization_id, user_id, goal_id, intent, gpu_type, gpu_count,
                 provider, max_cost_usd, max_runtime_minutes, script,
                 idem_key, meta_json, now),
            )
            cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()

        conn.commit()
        job = dict(row)
        logger.info(f"[JobDB] Created job {job_id} status=queued")
        return job
    except Exception as exc:
        conn.rollback()
        logger.error(f"[JobDB] create_job failed: {exc}")
        raise
    finally:
        conn.close()


def update_job_status(
    job_id: str,
    new_status: str,
    *,
    celery_task_id: str | None = None,
    provider_job_id: str | None = None,
    region: str | None = None,
    hourly_rate_usd: float | None = None,
    exit_code: int | None = None,
    cost_usd: float | None = None,
    duration_seconds: float | None = None,
    failure_reason: str | None = None,
    gpu_peak_util_pct: float | None = None,
    gpu_peak_mem_gb: float | None = None,
    increment_retry: bool = False,
) -> bool:
    """
    Atomic status update with state machine validation.
    Returns True if the update was applied, False if rejected (invalid transition or not found).
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()

        # Read current status under lock (FOR UPDATE on PG)
        if USE_PG:
            cur.execute("SELECT status, retry_count FROM jobs WHERE id = %s FOR UPDATE", (job_id,))
        else:
            cur.execute("SELECT status, retry_count FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        if not row:
            logger.warning(f"[JobDB] update_status: job {job_id} not found")
            return False

        current = dict(row)["status"]
        if not validate_transition(current, new_status):
            logger.warning(
                f"[JobDB] Invalid transition {current} → {new_status} for job {job_id}. Skipping."
            )
            return False

        now = datetime.now(timezone.utc).isoformat()
        updates: dict[str, Any] = {"status": new_status}

        if celery_task_id:
            updates["celery_task_id"] = celery_task_id
        if provider_job_id:
            updates["provider_job_id"] = provider_job_id
        if region:
            updates["region"] = region
        if hourly_rate_usd is not None:
            updates["hourly_rate_usd"] = hourly_rate_usd
        if exit_code is not None:
            updates["exit_code"] = exit_code
        if cost_usd is not None:
            updates["cost_incurred_usd"] = cost_usd
        if duration_seconds is not None:
            updates["duration_seconds"] = duration_seconds
        if failure_reason:
            updates["failure_reason"] = failure_reason
        if gpu_peak_util_pct is not None:
            updates["gpu_peak_util_pct"] = gpu_peak_util_pct
        if gpu_peak_mem_gb is not None:
            updates["gpu_peak_mem_gb"] = gpu_peak_mem_gb
        if increment_retry:
            updates["retry_count"] = (dict(row).get("retry_count") or 0) + 1
        if new_status in ("provisioning", "running") and "started_at" not in updates:
            updates["started_at"] = now
        if new_status in ("completed", "failed", "cancelled"):
            updates["completed_at"] = now

        set_clause = ", ".join(f"{k} = {PH}" for k in updates)
        values = list(updates.values()) + [job_id]

        if USE_PG:
            cur.execute(f"UPDATE jobs SET {set_clause} WHERE id = %s", values)
        else:
            cur.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)

        conn.commit()
        logger.info(f"[JobDB] Job {job_id}: {current} → {new_status}")
        return True
    except Exception as exc:
        conn.rollback()
        logger.error(f"[JobDB] update_status failed for {job_id}: {exc}")
        raise
    finally:
        conn.close()


def append_job_event(
    job_id: str,
    event_type: str,
    message: str = "",
    status: str | None = None,
    payload: dict | None = None,
    agent: str = "pipeline",
) -> None:
    """Append an immutable event to the job_events audit log."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        payload_json = json.dumps(payload or {})
        now = datetime.now(timezone.utc).isoformat()
        if USE_PG:
            cur.execute(
                """INSERT INTO job_events (job_id, event_type, status, message, payload, agent, created_at)
                   VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)""",
                (job_id, event_type, status, message, payload_json, agent, now),
            )
        else:
            cur.execute(
                """INSERT INTO job_events (job_id, event_type, status, message, payload, agent, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (job_id, event_type, status, message, payload_json, agent, now),
            )
        conn.commit()
    except Exception as exc:
        logger.warning(f"[JobDB] append_job_event failed (non-fatal): {exc}")
    finally:
        conn.close()


def insert_outbox_event(
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
) -> None:
    """
    Insert a transactional outbox event.
    Call this in the same DB transaction as the job state change to ensure
    the Celery task is eventually published even if the process crashes.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        payload_json = json.dumps(payload)
        now = datetime.now(timezone.utc).isoformat()
        if USE_PG:
            cur.execute(
                """INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload, created_at)
                   VALUES (%s, %s, %s, %s::jsonb, %s)""",
                (aggregate_type, aggregate_id, event_type, payload_json, now),
            )
        else:
            cur.execute(
                """INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (aggregate_type, aggregate_id, event_type, payload_json, now),
            )
        conn.commit()
    except Exception as exc:
        logger.warning(f"[JobDB] insert_outbox_event failed (non-fatal): {exc}")
    finally:
        conn.close()


def list_stuck_jobs(stuck_minutes: int = 30) -> list[dict]:
    """
    Return jobs that have been in a non-terminal, non-queued state longer than
    stuck_minutes without any update. Used by the reconciler.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if USE_PG:
            cur.execute(
                """SELECT id, status, provider_job_id, provider, celery_task_id, created_at
                   FROM jobs
                   WHERE status IN ('provisioning', 'booting', 'running', 'completing')
                     AND created_at < NOW() - INTERVAL %s
                   ORDER BY created_at ASC
                   LIMIT 100""",
                (f"{stuck_minutes} minutes",),
            )
        else:
            # SQLite: datetime('now') returns UTC without timezone suffix.
            # Python isoformat() may include '+00:00'. We use substr(created_at,1,19)
            # to strip the timezone suffix before comparing with datetime('now',...).
            cur.execute(
                """SELECT id, status, provider_job_id, provider, celery_task_id, created_at
                   FROM jobs
                   WHERE status IN ('provisioning', 'booting', 'running', 'completing')
                     AND substr(created_at, 1, 19) < datetime('now', ?)
                   ORDER BY created_at ASC
                   LIMIT 100""",
                (f"-{stuck_minutes} minutes",),
            )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning(f"[JobDB] list_stuck_jobs failed: {exc}")
        return []
    finally:
        conn.close()


def get_job_events(job_id: str, limit: int = 200) -> list[dict]:
    """Return the event history for a job, newest first."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM job_events WHERE job_id = {PH} ORDER BY id DESC LIMIT {PH}",
            (job_id, limit),
        )
        rows = cur.fetchall()
        events = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.get("payload") or "{}")
            except Exception:
                d["payload"] = {}
            events.append(d)
        return events
    except Exception as exc:
        logger.warning(f"[JobDB] get_job_events failed: {exc}")
        return []
    finally:
        conn.close()
