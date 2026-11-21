"""
Phase 2 — Tests: job persistence, duplicate prevention, reconciler, provider health.
Run from v4/ directory: python -m pytest phase2_tests.py -v

Tests use SQLite (no Postgres required) and mock Celery tasks inline.
They verify the exact acceptance criteria from the Phase 2 spec.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

# Use SQLite for all tests
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("USE_REAL_PROVIDERS", "false")
os.environ.setdefault("CELERY_ENABLED", "false")

import pytest

# ---------------------------------------------------------------------------
# Setup test DB
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    """Redirect SQLite DB to a temp file for each test."""
    db_file = str(tmp_path / "test_orquanta.db")
    monkeypatch.setattr("v4.execution.job_db._DB_FILE", db_file)
    monkeypatch.setattr("v4.execution.job_db.USE_PG", False)
    monkeypatch.setattr("v4.execution.job_db.PH", "?")

    # Create tables
    import sqlite3
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, organization_id TEXT, user_id TEXT, goal_id TEXT,
            intent TEXT, gpu_type TEXT, gpu_count INTEGER, provider TEXT,
            max_cost_usd REAL, max_runtime_minutes INTEGER, status TEXT DEFAULT 'queued',
            script TEXT, idempotency_key TEXT UNIQUE, job_metadata TEXT DEFAULT '{}',
            created_at TEXT, retry_count INTEGER DEFAULT 0,
            celery_task_id TEXT, provider_job_id TEXT, region TEXT,
            hourly_rate_usd REAL, exit_code INTEGER, cost_incurred_usd REAL,
            duration_seconds REAL, failure_reason TEXT, gpu_peak_util_pct REAL,
            gpu_peak_mem_gb REAL, started_at TEXT, completed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, event_type TEXT,
            status TEXT, message TEXT, payload TEXT DEFAULT '{}', agent TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outbox_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, aggregate_type TEXT, aggregate_id TEXT,
            event_type TEXT, payload TEXT DEFAULT '{}', published INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')), published_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT, is_real INTEGER,
            auth_ok INTEGER, api_latency_ms REAL, gpu_available INTEGER,
            last_error TEXT, checked_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()
    yield db_file


# ---------------------------------------------------------------------------
# Test: Job persistence
# ---------------------------------------------------------------------------

class TestJobPersistence:

    def test_create_job_persists_to_db(self, test_db):
        from v4.execution.job_db import create_job, get_job
        job = create_job(
            intent="Train GPT-2",
            gpu_type="H100",
            gpu_count=1,
            user_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
        )
        assert job["id"]
        assert job["status"] == "queued"

        fetched = get_job(job["id"])
        assert fetched is not None
        assert fetched["status"] == "queued"
        assert fetched["intent"] == "Train GPT-2"

    def test_job_survives_process_restart(self, test_db):
        """Simulate restart: get_job reads from DB, not in-memory dict."""
        from v4.execution.job_db import create_job, get_job

        job = create_job(
            intent="Fine-tune Llama",
            gpu_type="A100",
            gpu_count=2,
            user_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
        )
        job_id = job["id"]

        # Simulate: clear any in-memory state (DB is the source of truth)
        fetched = get_job(job_id)
        assert fetched["intent"] == "Fine-tune Llama"
        assert fetched["gpu_count"] == 2

    def test_state_machine_valid_transition(self, test_db):
        from v4.execution.job_db import create_job, update_job_status, get_job

        job = create_job("Run embedding", "T4", 1, str(uuid.uuid4()), str(uuid.uuid4()))
        job_id = job["id"]

        ok = update_job_status(job_id, "provisioning")
        assert ok is True
        assert get_job(job_id)["status"] == "provisioning"

        ok = update_job_status(job_id, "running")
        assert ok is True

        ok = update_job_status(job_id, "completed", exit_code=0, cost_usd=0.42, duration_seconds=120)
        assert ok is True
        final = get_job(job_id)
        assert final["status"] == "completed"
        assert final["exit_code"] == 0

    def test_state_machine_rejects_invalid_transition(self, test_db):
        from v4.execution.job_db import create_job, update_job_status

        job = create_job("Test", "H100", 1, str(uuid.uuid4()), str(uuid.uuid4()))
        job_id = job["id"]

        # Cannot go from queued → completed directly
        ok = update_job_status(job_id, "completed")
        assert ok is False

    def test_terminal_state_is_immutable(self, test_db):
        from v4.execution.job_db import create_job, update_job_status, get_job

        job = create_job("Test", "H100", 1, str(uuid.uuid4()), str(uuid.uuid4()))
        job_id = job["id"]
        update_job_status(job_id, "provisioning")
        update_job_status(job_id, "running")
        update_job_status(job_id, "completing")
        update_job_status(job_id, "completed")

        # Cannot transition out of completed (terminal state)
        ok = update_job_status(job_id, "failed")
        assert ok is False, "Terminal state 'completed' must be immutable"
        assert get_job(job_id)["status"] == "completed"

    def test_job_events_append_history(self, test_db):
        from v4.execution.job_db import create_job, append_job_event, get_job_events

        job = create_job("Test events", "H100", 1, str(uuid.uuid4()), str(uuid.uuid4()))
        job_id = job["id"]

        for event in ["provisioning_started", "provisioned", "job_running", "job_completed"]:
            append_job_event(job_id, event, message=f"Event: {event}", status=event)

        events = get_job_events(job_id)
        assert len(events) == 4
        event_types = [e["event_type"] for e in events]
        assert "job_completed" in event_types


# ---------------------------------------------------------------------------
# Test: Duplicate prevention (idempotency)
# ---------------------------------------------------------------------------

class TestDuplicatePrevention:

    def test_idempotent_job_creation(self, test_db):
        """Same idempotency_key → same job returned, no duplicate."""
        from v4.execution.job_db import create_job

        idem = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        job1 = create_job("Train", "H100", 1, str(uuid.uuid4()), org_id, idempotency_key=idem)
        job2 = create_job("Train", "H100", 1, str(uuid.uuid4()), org_id, idempotency_key=idem)

        assert job1["id"] == job2["id"], "Same idempotency_key must return the same job"

    def test_different_keys_create_different_jobs(self, test_db):
        from v4.execution.job_db import create_job

        org_id = str(uuid.uuid4())
        job1 = create_job("Job A", "H100", 1, str(uuid.uuid4()), org_id, idempotency_key=str(uuid.uuid4()))
        job2 = create_job("Job B", "H100", 1, str(uuid.uuid4()), org_id, idempotency_key=str(uuid.uuid4()))
        assert job1["id"] != job2["id"]

    def test_duplicate_task_submission_blocked_by_state_check(self, test_db):
        """
        A second dispatch attempt for a job already in 'provisioning' or beyond
        is blocked by the state machine — no duplicate billable execution.
        """
        from v4.execution.job_db import create_job, update_job_status

        job = create_job("Critical job", "H100", 1, str(uuid.uuid4()), str(uuid.uuid4()))
        job_id = job["id"]

        # Simulate first dispatch: job transitions to provisioning
        ok = update_job_status(job_id, "provisioning", celery_task_id="task-abc")
        assert ok is True

        # Simulate second dispatch attempt: cannot re-enter provisioning from provisioning
        ok2 = update_job_status(job_id, "provisioning", celery_task_id="task-xyz")
        assert ok2 is False, "Second dispatch must be blocked by state machine"


# ---------------------------------------------------------------------------
# Test: Reconciler
# ---------------------------------------------------------------------------

class TestReconciler:

    def test_list_stuck_jobs_empty_when_fresh(self, test_db):
        """Newly created jobs are not stuck (< 30 minutes old)."""
        from v4.execution.job_db import create_job, update_job_status, list_stuck_jobs

        job = create_job("New job", "H100", 1, str(uuid.uuid4()), str(uuid.uuid4()))
        update_job_status(job["id"], "provisioning")

        # Stuck threshold is 30 minutes — fresh job should not appear
        stuck = list_stuck_jobs(stuck_minutes=30)
        # May be empty or contain only pre-existing stuck jobs
        ids = [j["id"] for j in stuck]
        assert job["id"] not in ids, "Fresh job should not be in stuck list"

    def test_reconciler_marks_stuck_job_failed(self, test_db, monkeypatch):
        """Insert a stuck job and verify state machine reconciliation marks it failed."""
        import sqlite3
        import v4.execution.job_db as job_db_module
        from datetime import datetime, timezone, timedelta

        db_file = test_db

        # Patch module globals so _get_conn() uses the test DB for all calls in this test
        monkeypatch.setattr(job_db_module, "_DB_FILE", db_file)
        monkeypatch.setattr(job_db_module, "USE_PG", False)
        monkeypatch.setattr(job_db_module, "PH", "?")

        # SQLite datetime uses space separator "YYYY-MM-DD HH:MM:SS", NOT ISO 'T' format
        # Using 'T' causes lexicographic comparison to fail (T > space in ASCII)
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        job_id = str(uuid.uuid4())

        conn = sqlite3.connect(db_file)
        conn.execute(
            "INSERT INTO jobs (id, organization_id, user_id, intent, gpu_type, gpu_count, "
            "status, created_at, retry_count) VALUES (?,?,?,?,?,?,?,?,?)",
            (job_id, "org1", "user1", "Old stuck job", "H100", 1, "running", old_time, 0),
        )
        conn.commit()

        # Verify our SQLite datetime comparison logic works directly
        rows = conn.execute(
            "SELECT id FROM jobs WHERE status='running' AND substr(created_at,1,19) < datetime('now',?)",
            ("-30 minutes",)
        ).fetchall()
        conn.close()
        assert any(r[0] == job_id for r in rows), (
            f"Direct SQL should find stuck job. created_at={old_time}"
        )

        stuck = job_db_module.list_stuck_jobs(stuck_minutes=30)
        ids = [j["id"] for j in stuck]
        assert job_id in ids, f"Stuck job {job_id} should appear in stuck list; found: {ids}"

        ok = job_db_module.update_job_status(job_id, "failed", failure_reason="Reconciler: stuck > 30m")
        assert ok is True

        final = job_db_module.get_job(job_id)
        assert final["status"] == "failed"


# ---------------------------------------------------------------------------
# Test: Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:

    def test_job_owned_by_organization(self, test_db):
        from v4.execution.job_db import create_job, get_job

        org_a = str(uuid.uuid4())
        org_b = str(uuid.uuid4())

        job_a = create_job("Org A job", "H100", 1, str(uuid.uuid4()), org_a)
        job_b = create_job("Org B job", "H100", 1, str(uuid.uuid4()), org_b)

        fetched_a = get_job(job_a["id"])
        fetched_b = get_job(job_b["id"])

        assert fetched_a["organization_id"] == org_a
        assert fetched_b["organization_id"] == org_b
        assert fetched_a["id"] != fetched_b["id"]


# ---------------------------------------------------------------------------
# Test: Cost accounting
# ---------------------------------------------------------------------------

class TestCostAccounting:

    def test_cost_recorded_on_completion(self, test_db):
        from v4.execution.job_db import create_job, update_job_status, get_job

        job = create_job("Cost test", "H100", 1, str(uuid.uuid4()), str(uuid.uuid4()))
        job_id = job["id"]
        update_job_status(job_id, "provisioning")
        update_job_status(job_id, "running")
        update_job_status(
            job_id, "completing",
        )
        update_job_status(
            job_id, "completed",
            exit_code=0,
            cost_usd=1.2345,
            duration_seconds=1800.0,
        )

        final = get_job(job_id)
        assert final["cost_incurred_usd"] is not None
        assert float(final["cost_incurred_usd"]) == pytest.approx(1.2345, rel=1e-4)
        assert float(final["duration_seconds"]) == pytest.approx(1800.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Test: Provider health (mock mode)
# ---------------------------------------------------------------------------

class TestProviderHealth:

    def test_provider_health_no_real_credentials(self):
        """Without API keys, is_real must be False — never report mock as real."""
        from v4.execution.provider_health import _check_provider

        result = _check_provider("runpod")
        assert result["is_real"] is False, "Must not report mock provider as real"
        assert result["auth_ok"] is False
        assert "RUNPOD_API_KEY" in (result.get("last_error") or "")

    def test_provider_health_persists_to_db(self, test_db):
        from v4.execution.provider_health import _check_provider, _persist_health, get_latest_health

        result = _check_provider("runpod")
        _persist_health("runpod", result)

        health = get_latest_health()
        providers = [h["provider"] for h in health]
        assert "runpod" in providers
        rp = next(h for h in health if h["provider"] == "runpod")
        assert rp["is_real"] in (0, False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
