"""
OrQuanta Agentic v1.0 — FastAPI Integration Tests
Tests the full API layer against a real in-process FastAPI app (TestClient)
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi.testclient import TestClient
from v4.api.main import app
from v4.api.middleware.auth import register_user, authenticate_user, create_access_token


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token():
    """Register a test user (idempotent) and return an admin JWT for testing."""
    try:
        register_user("test@orquanta.com", "testpass123", "Test User")
    except ValueError:
        pass  # Already registered — fine
    # Promote to admin directly in SQLite for testing
    from v4.api.middleware.auth import _get_db
    conn = _get_db()
    conn.execute("UPDATE users SET role = 'admin' WHERE email = ?", ("test@orquanta.com",))
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE email = ?", ("test@orquanta.com",)).fetchone()
    conn.close()
    if user:
        return create_access_token(user["id"], user["email"], "admin")
    return "no-user"


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ─── Health ────────────────────────────────────────────────────────────────

def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
    assert "components" in data


def test_root(client):
    # Root redirects to /app (302). Follow redirect to get the API info.
    res = client.get("/api")
    assert res.status_code == 200
    data = res.json()
    assert "OrQuanta" in data["name"]


# ─── Auth ──────────────────────────────────────────────────────────────────

def test_register_new_user(client):
    import uuid
    res = client.post("/auth/register", json={
        "email": f"newuser-{uuid.uuid4().hex[:8]}@test.com", "password": "password123", "name": "New User"
    })
    assert res.status_code == 201  # register returns 201 Created
    data = res.json()
    assert "access_token" in data

def test_register_duplicate_fails(client):
    client.post("/auth/register", json={"email": "dup@test.com", "password": "pass1234"})
    res = client.post("/auth/register", json={"email": "dup@test.com", "password": "pass1234"})
    assert res.status_code == 400

def test_login_success(client):
    client.post("/auth/register", json={"email": "login@test.com", "password": "goodpass1"})
    res = client.post("/auth/login", json={"email": "login@test.com", "password": "goodpass1"})
    assert res.status_code == 200
    assert "access_token" in res.json()

def test_login_wrong_password(client):
    res = client.post("/auth/login", json={"email": "login@test.com", "password": "wrong"})
    assert res.status_code == 401

def test_protected_route_requires_auth(client):
    res = client.get("/api/v1/jobs")
    assert res.status_code == 401


# ─── Goals ─────────────────────────────────────────────────────────────────

def test_submit_goal(client, auth_headers):
    res = client.post("/api/v1/goals", json={"raw_text": "Train a LLaMA 7B model on my data"}, headers=auth_headers)
    assert res.status_code == 202
    data = res.json()
    assert "goal_id" in data
    assert data["status"] == "accepted"

def test_submit_goal_too_short(client, auth_headers):
    res = client.post("/api/v1/goals", json={"raw_text": "hi"}, headers=auth_headers)
    assert res.status_code == 422  # Pydantic validation error

def test_get_goal(client, auth_headers):
    sub = client.post("/api/v1/goals", json={"raw_text": "Run inference on my images"}, headers=auth_headers)
    goal_id = sub.json()["goal_id"]
    res = client.get(f"/api/v1/goals/{goal_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["goal_id"] == goal_id

def test_get_nonexistent_goal(client, auth_headers):
    res = client.get("/api/v1/goals/fake-goal-99", headers=auth_headers)
    assert res.status_code == 404

def test_list_goals(client, auth_headers):
    res = client.get("/api/v1/goals", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "goals" in data
    assert isinstance(data["goals"], list)


# ─── Jobs ──────────────────────────────────────────────────────────────────

def test_create_job(client, auth_headers):
    res = client.post("/api/v1/jobs", json={
        "intent": "Run stable diffusion inference",
        "gpu_type": "H100", "gpu_count": 1, "provider": "aws",
        "required_vram_gb": 80, "max_cost_usd": 200.0, "max_runtime_minutes": 60,
    }, headers=auth_headers)
    assert res.status_code == 201
    assert "job_id" in res.json()

def test_list_jobs(client, auth_headers):
    res = client.get("/api/v1/jobs", headers=auth_headers)
    assert res.status_code == 200
    assert "jobs" in res.json()

def test_list_jobs_status_filter(client, auth_headers):
    res = client.get("/api/v1/jobs?status=queued", headers=auth_headers)
    assert res.status_code == 200

def test_get_job_not_found(client, auth_headers):
    res = client.get("/api/v1/jobs/fake-job-000", headers=auth_headers)
    assert res.status_code == 404

def test_cancel_job(client, auth_headers):
    create = client.post("/api/v1/jobs", json={
        "intent": "Job to cancel", "gpu_type": "T4", "gpu_count": 1,
        "provider": "gcp", "required_vram_gb": 16, "max_cost_usd": 50.0, "max_runtime_minutes": 30,
    }, headers=auth_headers)
    job_id = create.json()["job_id"]
    res = client.delete(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"


# ─── Agents ────────────────────────────────────────────────────────────────

def test_list_agents(client, auth_headers):
    res = client.get("/api/v1/agents", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "agents" in data
    assert "emergency_stop_active" in data

def test_emergency_stop_requires_admin(client, auth_headers):
    res = client.post("/api/v1/agents/emergency-stop?reason=Test", headers=auth_headers)
    assert res.status_code == 200 or res.status_code == 403


# ─── Metrics ───────────────────────────────────────────────────────────────

def test_platform_metrics(client, auth_headers):
    res = client.get("/api/v1/metrics", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "total_active_jobs" in data
    assert "daily_spend_usd" in data

def test_spot_prices(client, auth_headers):
    res = client.get("/api/v1/metrics/spot-prices/H100", headers=auth_headers)
    assert res.status_code == 200
    assert "gpu_type" in res.json()


# ─── Audit ─────────────────────────────────────────────────────────────────

def test_audit_log(client, auth_headers):
    res = client.get("/api/v1/audit", headers=auth_headers)
    assert res.status_code == 200
    assert "entries" in res.json()

def test_audit_stats(client, auth_headers):
    res = client.get("/api/v1/audit/stats", headers=auth_headers)
    assert res.status_code == 200
    assert "emergency_stop_active" in res.json()


# ─── API Keys ──────────────────────────────────────────────────────────────

def test_create_api_key(client, auth_headers):
    res = client.post("/api/v1/api-keys", json={"name": "ci-test-key"}, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["key"].startswith("sk-orq-")
    assert "key_id" in data
    assert data["name"] == "ci-test-key"


def test_list_api_keys(client, auth_headers):
    res = client.get("/api/v1/api-keys", headers=auth_headers)
    assert res.status_code == 200
    keys = res.json()
    assert isinstance(keys, list)
    assert any(k["name"] == "ci-test-key" for k in keys)


def test_api_key_auth_works(client, auth_headers):
    """A created sk-orq-* key should authenticate protected routes."""
    create = client.post("/api/v1/api-keys", json={"name": "auth-test-key"}, headers=auth_headers)
    raw_key = create.json()["key"]
    res = client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {raw_key}"})
    assert res.status_code == 200


def test_revoke_api_key(client, auth_headers):
    create = client.post("/api/v1/api-keys", json={"name": "to-revoke"}, headers=auth_headers)
    key_id = create.json()["key_id"]
    res = client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)
    assert res.status_code == 204


def test_revoked_key_rejected(client, auth_headers):
    create = client.post("/api/v1/api-keys", json={"name": "revoke-then-use"}, headers=auth_headers)
    data = create.json()
    raw_key, key_id = data["key"], data["key_id"]
    client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)
    res = client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {raw_key}"})
    assert res.status_code == 401


def test_api_key_limit_enforced(client, auth_headers):
    """Cannot exceed 10 active keys — returns 429."""
    existing = client.get("/api/v1/api-keys", headers=auth_headers).json()
    needed = max(0, 10 - len(existing))
    for i in range(needed):
        client.post("/api/v1/api-keys", json={"name": f"fill-{i}"}, headers=auth_headers)
    res = client.post("/api/v1/api-keys", json={"name": "over-limit"}, headers=auth_headers)
    assert res.status_code == 429


def test_api_keys_unauthenticated(client):
    res = client.get("/api/v1/api-keys")
    assert res.status_code == 401


# ─── Webhooks ──────────────────────────────────────────────────────────────

def test_create_webhook(client, auth_headers):
    res = client.post("/api/v1/webhooks", json={
        "url": "https://example.com/hook",
        "events": ["job_completed", "job_failed"],
        "description": "CI test hook",
    }, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["id"].startswith("wh-")
    assert "inbound_url" in data


def test_list_webhooks(client, auth_headers):
    res = client.get("/api/v1/webhooks", headers=auth_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_webhook_deliveries(client, auth_headers):
    create = client.post("/api/v1/webhooks", json={
        "url": "https://example.com/hook2",
        "events": ["job_completed"],
    }, headers=auth_headers)
    wid = create.json()["id"]
    res = client.get(f"/api/v1/webhooks/{wid}/deliveries", headers=auth_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_delete_webhook(client, auth_headers):
    create = client.post("/api/v1/webhooks", json={
        "url": "https://example.com/hook-del",
        "events": ["job_completed"],
    }, headers=auth_headers)
    wid = create.json()["id"]
    res = client.delete(f"/api/v1/webhooks/{wid}", headers=auth_headers)
    assert res.status_code == 204


def test_webhook_not_found(client, auth_headers):
    res = client.get("/api/v1/webhooks/wh-nonexistent/deliveries", headers=auth_headers)
    assert res.status_code == 404


def test_webhooks_unauthenticated(client):
    res = client.get("/api/v1/webhooks")
    assert res.status_code == 401


# ─── OAuth redirects ───────────────────────────────────────────────────────

def test_google_login_redirects(client):
    """OAuth login redirects — to Google when configured, error page when not."""
    res = client.get("/auth/google/login", follow_redirects=False)
    assert res.status_code in (302, 307)
    location = res.headers.get("location", "")
    assert "accounts.google.com" in location or "error=google_not_configured" in location


def test_github_login_redirects(client):
    """OAuth login redirects — to GitHub when configured, error page when not."""
    res = client.get("/auth/github/login", follow_redirects=False)
    assert res.status_code in (302, 307)
    location = res.headers.get("location", "")
    assert "github.com" in location or "error=github_not_configured" in location
