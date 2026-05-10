"""
OrQuanta Agentic v1.0 — Goal and Job Persistence Layer

Durable storage for Goals (MasterOrchestrator) and Jobs (JobPipeline).
Uses the same psycopg2/SQLite pattern as auth.py — no new dependencies.
Survives Render restarts: state is restored on startup from this store.

All writes are fire-and-forget (errors logged, never raised) so a DB
outage can never bring down the in-memory orchestrator.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("orquanta.persistence")

_DATABASE_URL = os.getenv("DATABASE_URL", "")
_USE_PG = _DATABASE_URL.startswith(("postgresql://", "postgres://"))

if _USE_PG:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        _USE_PG = False

_DB_FILE = "./orquanta.db"


def _ph() -> str:
    return "%s" if _USE_PG else "?"


def _get_db():
    if _USE_PG:
        conn = psycopg2.connect(
            _DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=10,
        )
        conn.autocommit = False
        return conn
    import sqlite3
    conn = sqlite3.connect(_DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


_GOALS_DDL = """
    CREATE TABLE IF NOT EXISTS goals (
        goal_id           TEXT PRIMARY KEY,
        user_id           TEXT NOT NULL DEFAULT '',
        raw_text          TEXT NOT NULL DEFAULT '',
        status            TEXT NOT NULL DEFAULT 'decomposing',
        plan              TEXT NOT NULL DEFAULT '{}',
        tasks             TEXT NOT NULL DEFAULT '[]',
        completed_tasks   TEXT NOT NULL DEFAULT '[]',
        failed_tasks      TEXT NOT NULL DEFAULT '[]',
        result            TEXT NOT NULL DEFAULT '{}',
        cost_incurred_usd REAL NOT NULL DEFAULT 0.0,
        reasoning_steps   INTEGER NOT NULL DEFAULT 0,
        created_at        TEXT NOT NULL DEFAULT '',
        updated_at        TEXT NOT NULL DEFAULT ''
    )
"""

_JOBS_DDL = """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id           TEXT PRIMARY KEY,
        user_id          TEXT NOT NULL DEFAULT '',
        intent           TEXT NOT NULL DEFAULT '',
        gpu_type         TEXT NOT NULL DEFAULT 'H100',
        gpu_count        INTEGER NOT NULL DEFAULT 1,
        provider         TEXT NOT NULL DEFAULT 'runpod',
        region           TEXT NOT NULL DEFAULT '',
        instance_id      TEXT NOT NULL DEFAULT '',
        status           TEXT NOT NULL DEFAULT 'queued',
        script           TEXT NOT NULL DEFAULT '',
        exit_code        INTEGER,
        cost_usd         REAL NOT NULL DEFAULT 0.0,
        hourly_rate      REAL NOT NULL DEFAULT 0.0,
        error            TEXT,
        metadata         TEXT NOT NULL DEFAULT '{}',
        log_lines        TEXT NOT NULL DEFAULT '[]',
        created_at       TEXT NOT NULL DEFAULT '',
        started_at       TEXT,
        completed_at     TEXT,
        duration_seconds REAL NOT NULL DEFAULT 0.0
    )
"""


def ensure_tables() -> None:
    """Create goals and jobs tables if they don't exist. Safe to call every startup."""
    try:
        conn = _get_db()
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(_GOALS_DDL)
            cur.execute(_JOBS_DDL)
            conn.commit()
            cur.close()
        else:
            conn.execute(_GOALS_DDL)
            conn.execute(_JOBS_DDL)
            conn.commit()
        conn.close()
        logger.info("[Persistence] goals + jobs tables ready.")
    except Exception as exc:
        logger.warning(f"[Persistence] ensure_tables failed (non-fatal): {exc}")


def upsert_goal(goal: dict[str, Any]) -> None:
    """Insert or update a goal record. Never raises — DB errors are logged only."""
    ph = _ph()
    sql = f"""
        INSERT INTO goals
            (goal_id, user_id, raw_text, status, plan, tasks,
             completed_tasks, failed_tasks, result,
             cost_incurred_usd, reasoning_steps, created_at, updated_at)
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        ON CONFLICT (goal_id) DO UPDATE SET
            status            = excluded.status,
            plan              = excluded.plan,
            tasks             = excluded.tasks,
            completed_tasks   = excluded.completed_tasks,
            failed_tasks      = excluded.failed_tasks,
            result            = excluded.result,
            cost_incurred_usd = excluded.cost_incurred_usd,
            reasoning_steps   = excluded.reasoning_steps,
            updated_at        = excluded.updated_at
    """
    params = (
        goal.get("goal_id", ""),
        goal.get("user_id", ""),
        goal.get("raw_text", ""),
        goal.get("status", "decomposing"),
        json.dumps(goal.get("plan", {})),
        json.dumps(goal.get("tasks", [])),
        json.dumps(goal.get("completed_tasks", [])),
        json.dumps(goal.get("failed_tasks", [])),
        json.dumps(goal.get("result", {})),
        goal.get("cost_incurred_usd", 0.0),
        goal.get("reasoning_steps", 0),
        goal.get("created_at", ""),
        goal.get("updated_at", ""),
    )
    try:
        conn = _get_db()
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            cur.close()
        else:
            conn.execute(sql, params)
            conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning(f"[Persistence] upsert_goal({goal.get('goal_id')}) failed: {exc}")


def upsert_job(job: dict[str, Any]) -> None:
    """Insert or update a job record. Never raises — DB errors are logged only."""
    ph = _ph()
    sql = f"""
        INSERT INTO jobs
            (job_id, user_id, intent, gpu_type, gpu_count, provider, region,
             instance_id, status, script, exit_code, cost_usd, hourly_rate,
             error, metadata, log_lines, created_at, started_at,
             completed_at, duration_seconds)
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        ON CONFLICT (job_id) DO UPDATE SET
            status           = excluded.status,
            instance_id      = excluded.instance_id,
            exit_code        = excluded.exit_code,
            cost_usd         = excluded.cost_usd,
            hourly_rate      = excluded.hourly_rate,
            error            = excluded.error,
            log_lines        = excluded.log_lines,
            started_at       = excluded.started_at,
            completed_at     = excluded.completed_at,
            duration_seconds = excluded.duration_seconds
    """
    params = (
        job.get("job_id", ""),
        job.get("user_id", ""),
        job.get("intent", ""),
        job.get("gpu_type", "H100"),
        job.get("gpu_count", 1),
        job.get("provider", "runpod"),
        job.get("region", ""),
        job.get("instance_id", ""),
        job.get("status", "queued"),
        job.get("script", ""),
        job.get("exit_code"),
        job.get("cost_usd", 0.0),
        job.get("hourly_rate", 0.0),
        job.get("error"),
        json.dumps(job.get("metadata", {})),
        json.dumps(job.get("log_lines", [])[-100:]),
        job.get("created_at", ""),
        job.get("started_at"),
        job.get("completed_at"),
        job.get("duration_seconds", 0.0),
    )
    try:
        conn = _get_db()
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            cur.close()
        else:
            conn.execute(sql, params)
            conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning(f"[Persistence] upsert_job({job.get('job_id')}) failed: {exc}")


def load_all_goals() -> list[dict[str, Any]]:
    """Load all goal records. Returns [] on any error."""
    try:
        conn = _get_db()
        if _USE_PG:
            cur = conn.cursor()
            cur.execute("SELECT * FROM goals ORDER BY created_at")
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
        else:
            rows = [dict(r) for r in conn.execute("SELECT * FROM goals ORDER BY created_at").fetchall()]
        conn.close()
        for row in rows:
            for col in ("plan", "result"):
                try:
                    row[col] = json.loads(row.get(col) or "{}")
                except Exception:
                    row[col] = {}
            for col in ("tasks", "completed_tasks", "failed_tasks"):
                try:
                    row[col] = json.loads(row.get(col) or "[]")
                except Exception:
                    row[col] = []
        logger.info(f"[Persistence] Loaded {len(rows)} goals from DB.")
        return rows
    except Exception as exc:
        logger.warning(f"[Persistence] load_all_goals failed: {exc}")
        return []


def load_all_jobs() -> list[dict[str, Any]]:
    """Load all job records. Returns [] on any error."""
    try:
        conn = _get_db()
        if _USE_PG:
            cur = conn.cursor()
            cur.execute("SELECT * FROM jobs ORDER BY created_at")
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
        else:
            rows = [dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY created_at").fetchall()]
        conn.close()
        for row in rows:
            try:
                row["metadata"] = json.loads(row.get("metadata") or "{}")
            except Exception:
                row["metadata"] = {}
            try:
                row["log_lines"] = json.loads(row.get("log_lines") or "[]")
            except Exception:
                row["log_lines"] = []
        logger.info(f"[Persistence] Loaded {len(rows)} jobs from DB.")
        return rows
    except Exception as exc:
        logger.warning(f"[Persistence] load_all_jobs failed: {exc}")
        return []
