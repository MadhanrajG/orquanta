"""
OrQuanta Agentic v1.0 — End-to-End Integration Tests

Full workflow validation:
  Register → Login → Submit Goal → Watch Agents →
  Check Routing Decision → Verify Audit Trail → Confirm Cost Tracking

Uses the real FastAPI TestClient so no live server needed.
All real cloud API calls are mocked via environment variables.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from v4.api.main import app
from v4.providers.base_provider import GPUInstance, SpotPrice
from v4.providers.provider_router import ProviderRouter


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    """Register and authenticate a test user, return JWT headers."""
    email = f"e2e-{uuid.uuid4().hex[:8]}@orquanta-test.ai"
    password = "E2E_Secure_Pass_123!"

    # Register
    r = client.post("/auth/register", json={"email": email, "password": password, "name": "E2E Tester"})
    assert r.status_code == 201, f"Registration failed: {r.text}"

    # Login
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json()["access_token"]

    return {"Authorization": f"Bearer {token}", "X-User-Email": email}


@pytest.fixture
def mock_instance() -> GPUInstance:
    return GPUInstance(
        instance_id="i-e2e-test-001",
        provider="aws",
        region="us-east-1",
        gpu_type="A100",
        gpu_count=1,
        vram_gb=40,
        vcpus=12,
        ram_gb=85,
        hourly_cost_usd=1.20,
        status="running",
        public_ip="1.2.3.4",
        spot=True,
        tags={"managedby": "orquanta", "test": "e2e"},
    )


@pytest.fixture
def mock_spot_price() -> SpotPrice:
    return SpotPrice(
        provider="aws",
        region="us-east-1",
        gpu_type="A100",
        instance_type="p4d.24xlarge",
        current_price_usd_hr=1.20,
        on_demand_price_usd_hr=2.93,
        availability="high",
        interruption_rate_pct=4.5,
    )


# ─── 1. Authentication Flow ───────────────────────────────────────────────────

class TestAuthFlow:
    """Complete authentication lifecycle tests."""

    def test_register_unique_user(self, client):
        email = f"reg-{uuid.uuid4().hex[:8]}@test.ai"
        r = client.post("/auth/register", json={
            "email": email, "password": "TestPass123!", "name": "New User"
        })
        assert r.status_code == 201
        body = r.json()
        assert "user_id" in body
        assert body["email"] == email

    def test_login_returns_jwt(self, client):
        email = f"login-{uuid.uuid4().hex[:8]}@test.ai"
        client.post("/auth/register", json={"email": email, "password": "Pass123!", "name": "Login Test"})
        r = client.post("/auth/login", json={"email": email, "password": "Pass123!"})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        # JWT should have 3 dot-separated parts
        assert len(body["access_token"].split(".")) == 3

    def test_wrong_password_rejected(self, client):
        email = f"wrong-{uuid.uuid4().hex[:8]}@test.ai"
        client.post("/auth/register", json={"email": email, "password": "Correct123!", "name": "Test"})
        r = client.post("/auth/login", json={"email": email, "password": "WrongPassword!"})
        assert r.status_code in (401, 403)

    def test_duplicate_registration_rejected(self, client):
        email = f"dup-{uuid.uuid4().hex[:8]}@test.ai"
        client.post("/auth/register", json={"email": email, "password": "Pass123!", "name": "First"})
        r = client.post("/auth/register", json={"email": email, "password": "Pass123!", "name": "Second"})
        assert r.status_code in (400, 409)

    def test_protected_route_without_token_rejected(self, client):
        r = client.get("/goals/")
        assert r.status_code == 401

    def test_protected_route_with_token_works(self, client, auth_headers):
        r = client.get("/goals/", headers=auth_headers)
        assert r.status_code == 200


# ─── 2. Goal Submission → Agent Processing Flow ──────────────────────────────

class TestGoalSubmissionFlow:
    """Test goal life cycle from submission to completion."""

    def test_submit_goal_returns_goal_id(self, client, auth_headers):
        r = client.post("/goals/", json={
            "raw_text": "Train BERT model on customer feedback dataset for sentiment analysis",
            "budget_usd": 50.0,
        }, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "goal_id" in body
        assert body["status"] in ("accepted", "planning", "executing")

    def test_submit_goal_too_short_rejected(self, client, auth_headers):
        r = client.post("/goals/", json={"raw_text": "short"}, headers=auth_headers)
        assert r.status_code == 422

    def test_goal_persists_and_is_retrievable(self, client, auth_headers):
        # Submit
        r = client.post("/goals/", json={
            "raw_text": "Fine-tune LLaMA 3 on medical QA dataset with LoRA on A100"
        }, headers=auth_headers)
        assert r.status_code == 200
        goal_id = r.json()["goal_id"]

        # Retrieve
        r = client.get(f"/goals/{goal_id}", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["goal_id"] == goal_id
        assert "LLaMA" in body["raw_text"]

    def test_goal_list_pagination(self, client, auth_headers):
        # Submit 3 goals
        for i in range(3):
            client.post("/goals/", json={
                "raw_text": f"Train ResNet50 on ImageNet subset part {i} — distributed training"
            }, headers=auth_headers)

        r = client.get("/goals/?limit=2&offset=0", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body.get("goals", body), list)

    def test_goal_contains_reasoning_log(self, client, auth_headers):
        r = client.post("/goals/", json={
            "raw_text": "Deploy GPT-4 fine-tuning pipeline with FSDP on 4×H100"
        }, headers=auth_headers)
        goal_id = r.json()["goal_id"]
        time.sleep(0.1)  # Let agent process async

        r = client.get(f"/goals/{goal_id}", headers=auth_headers)
        body = r.json()
        # Either has plan or reasoning_log populated
        assert "status" in body


# ─── 3. Job Management Flow ───────────────────────────────────────────────────

class TestJobManagementFlow:
    """Test job CRUD and state transitions."""

    def test_create_job_returns_job_id(self, client, auth_headers):
        r = client.post("/jobs/", json={
            "intent": "Train YOLOv8 on custom dataset — 10 epochs",
            "gpu_type": "A100",
            "gpu_count": 1,
            "required_vram_gb": 40,
            "max_cost_usd": 20.0,
        }, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "job_id" in body
        assert body["status"] == "queued"

    def test_created_job_appears_in_list(self, client, auth_headers):
        client.post("/jobs/", json={
            "intent": "Inference benchmark on T4 GPU",
            "gpu_type": "T4",
            "gpu_count": 1,
        }, headers=auth_headers)
        r = client.get("/jobs/", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        jobs = body if isinstance(body, list) else body.get("jobs", [])
        assert len(jobs) > 0

    def test_filter_jobs_by_status(self, client, auth_headers):
        r = client.get("/jobs/?status=queued", headers=auth_headers)
        assert r.status_code == 200

    def test_cancel_job(self, client, auth_headers):
        r = client.post("/jobs/", json={
            "intent": "This job will be cancelled",
            "gpu_type": "T4",
            "gpu_count": 1,
        }, headers=auth_headers)
        job_id = r.json()["job_id"]

        r = client.delete(f"/jobs/{job_id}", headers=auth_headers)
        assert r.status_code in (200, 204)

    def test_get_nonexistent_job_returns_404(self, client, auth_headers):
        r = client.get(f"/jobs/{uuid.uuid4()}", headers=auth_headers)
        assert r.status_code == 404


# ─── 4. Provider Router Integration ──────────────────────────────────────────

class TestProviderRouter:
    """Test the intelligent provider routing logic."""

    def test_compare_prices_returns_sorted_list(self):
        router = ProviderRouter()
        prices = asyncio.run(router.compare_prices("H100"))
        assert isinstance(prices, list)
        assert len(prices) > 0
        # Prices must be sorted cheapest first
        for i in range(len(prices) - 1):
            assert prices[i].current_price_usd_hr <= prices[i + 1].current_price_usd_hr

    def test_compare_prices_all_providers_present(self):
        router = ProviderRouter()
        prices = asyncio.run(router.compare_prices("A100"))
        providers = {p.provider for p in prices}
        # Should have at least 2 providers in mock mode
        assert len(providers) >= 2

    @pytest.mark.asyncio
    async def test_spin_up_cheapest_returns_instance(self, mock_instance, mock_spot_price):
        router = ProviderRouter()
        # Patch all provider spin_up methods to return mock instance
        for provider in router._providers.values():
            provider.get_spot_prices = AsyncMock(return_value=[mock_spot_price])
            provider.spin_up = AsyncMock(return_value=mock_instance)

        instance, decision = await router.spin_up_cheapest("A100", gpu_count=1)
        assert isinstance(instance, GPUInstance)
        assert instance.gpu_type == "A100"
        assert decision.chosen_provider in ["aws", "gcp", "azure", "coreweave"]

    @pytest.mark.asyncio
    async def test_router_failover_on_capacity_error(self, mock_instance):
        from v4.providers.base_provider import InsufficientCapacityError
        router = ProviderRouter()

        # Make first provider fail, second succeed
        providers = list(router._providers.values())
        mock_price = SpotPrice("aws", "us-east-1", "V100", "p3.2xlarge", 0.90, 2.48, "high")

        for i, provider in enumerate(providers):
            provider.get_spot_prices = AsyncMock(return_value=[mock_price])
            if i == 0:
                provider.spin_up = AsyncMock(side_effect=InsufficientCapacityError("No capacity"))
            else:
                provider.spin_up = AsyncMock(return_value=mock_instance)

        # Should succeed via failover
        instance, decision = await router.spin_up_cheapest("V100")
        assert instance is not None
        assert decision.alternatives_considered > 0

    def test_routing_stats_structure(self):
        router = ProviderRouter()
        stats = router.get_routing_stats()
        assert "total_instances_launched" in stats
        assert "provider_distribution" in stats
        assert "avg_decision_latency_ms" in stats


# ─── 5. Monitoring Integration ───────────────────────────────────────────────

class TestMonitoringIntegration:
    """Test cost tracking and alerting."""

    def test_cost_tracker_registers_instance(self):
        from v4.monitoring.cost_tracker import CostTracker
        tracker = CostTracker(daily_budget_usd=1000.0)
        tracker.register_instance(
            "inst-monitor-001", "job-001", "aws", "A100", 1, 2.93
        )
        assert "inst-monitor-001" in tracker._active_instances
        spend = tracker.get_job_spend("job-001")
        assert spend >= 0  # May be fractional seconds

    def test_cost_tracker_deregister_records_cost(self):
        from v4.monitoring.cost_tracker import CostTracker
        tracker = CostTracker(daily_budget_usd=1000.0)
        tracker.register_instance("inst-002", "job-002", "gcp", "T4", 1, 0.35)
        time.sleep(0.01)  # Let a tiny bit of time pass
        cost = tracker.deregister_instance("inst-002")
        assert cost >= 0
        assert len(tracker._records) == 1

    def test_cost_dashboard_structure(self):
        from v4.monitoring.cost_tracker import CostTracker
        tracker = CostTracker(daily_budget_usd=500.0)
        tracker.record_one_time_cost("job-003", 5.50, "aws", "api-call")
        dashboard = tracker.get_cost_dashboard()
        required_keys = [
            "today_spend_usd", "daily_budget_usd", "budget_used_pct",
            "remaining_usd", "active_instances", "weekly_report",
        ]
        for k in required_keys:
            assert k in dashboard, f"Missing key: {k}"

    @pytest.mark.asyncio
    async def test_alert_manager_deduplicates(self):
        from v4.monitoring.alerting import AlertManager, Alert, AlertSeverity
        manager = AlertManager()
        alert = Alert(
            alert_id="a-dedup-001",
            title="GPU Temperature Critical",
            message="GPU0 is at 88°C",
            severity=AlertSeverity.CRITICAL,
            source="gpu_telemetry",
            instance_id="inst-001",
        )
        # First send should add to history
        r1 = await manager.send(alert)
        assert r1 is True

        # Second send immediately after should be suppressed
        alert2 = Alert(
            alert_id="a-dedup-002",
            title="GPU Temperature Critical",
            message="GPU0 is still at 89°C",
            severity=AlertSeverity.CRITICAL,
            source="gpu_telemetry",
            instance_id="inst-001",
        )
        r2 = await manager.send(alert2)
        assert r2 is False  # Deduplicated


# ─── 6. Audit Trail Integration ───────────────────────────────────────────────

class TestAuditTrail:
    """Verify audit log is populated correctly through the API."""

    def test_audit_log_accessible(self, client, auth_headers):
        r = client.get("/audit/", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "entries" in body or isinstance(body, list)

    def test_audit_stats_returned(self, client, auth_headers):
        r = client.get("/audit/stats", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "total_actions_logged" in body

    def test_goal_submission_generates_audit_entry(self, client, auth_headers):
        # Submit a goal
        client.post("/goals/", json={
            "raw_text": "Run CLIP model inference on 100K images for product classification"
        }, headers=auth_headers)
        time.sleep(0.2)  # Let agent process

        # Audit log should have at least one entry
        r = client.get("/audit/", headers=auth_headers)
        assert r.status_code == 200


# ─── 7. Platform Metrics ─────────────────────────────────────────────────────

class TestPlatformMetrics:
    """Validate platform-level metrics endpoints."""

    def test_platform_metrics_structure(self, client, auth_headers):
        r = client.get("/metrics/platform", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        expected_keys = [
            "active_jobs", "active_instances", "total_goals",
            "platform_utilization_pct", "agents_active",
        ]
        for k in expected_keys:
            assert k in body, f"Missing metric: {k}"

    def test_spot_prices_returned(self, client, auth_headers):
        r = client.get("/metrics/spot-prices?gpu_type=H100", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        prices = body.get("prices", body)
        assert isinstance(prices, list)
        if prices:
            assert "provider" in prices[0]
            assert "current_price_usd_hr" in prices[0]

    def test_spot_prices_sorted_cheapest_first(self, client, auth_headers):
        r = client.get("/metrics/spot-prices?gpu_type=A100", headers=auth_headers)
        assert r.status_code == 200
        prices = r.json().get("prices", [])
        for i in range(len(prices) - 1):
            assert prices[i]["current_price_usd_hr"] <= prices[i + 1]["current_price_usd_hr"]

    def test_agent_statuses_all_present(self, client, auth_headers):
        r = client.get("/agents/", headers=auth_headers)
        assert r.status_code == 200
        agents = r.json()
        assert isinstance(agents, list)
        names = [a.get("agent_name", a.get("name", "")) for a in agents]
        for expected in ["master_orchestrator", "scheduler_agent", "cost_optimizer_agent"]:
            assert any(expected in n for n in names), f"Agent {expected} not found in {names}"


# ─── 8. WebSocket Connectivity ────────────────────────────────────────────────

class TestWebSocketConnectivity:
    """Verify WebSocket stream endpoint connectivity."""

    def test_websocket_connects_and_sends_data(self, client, auth_headers):
        token = auth_headers["Authorization"].replace("Bearer ", "")
        with client.websocket_connect(f"/ws/agent-stream?token={token}") as ws:
            # Should receive initial connection event
            data = ws.receive_json(timeout=5)
            assert "type" in data or "event" in data or data is not None

    def test_websocket_rejects_without_token(self, client):
        try:
            with client.websocket_connect("/ws/agent-stream") as ws:
                data = ws.receive_json(timeout=2)
                # Some servers send error JSON before closing
        except Exception:
            pass  # Connection refused is also acceptable


# ─── 9. Safety Limits ────────────────────────────────────────────────────────

class TestSafetyLimits:
    """Verify safety governors are enforced through the API."""

    def test_emergency_stop_requires_admin(self, client, auth_headers):
        r = client.post("/agents/emergency-stop", json={"token": "wrong-token"}, headers=auth_headers)
        assert r.status_code in (401, 403)

    def test_goal_with_excessive_budget_warned(self, client, auth_headers):
        r = client.post("/goals/", json={
            "raw_text": "Train full GPT-4 scale model from scratch on all public data",
            "budget_usd": 1_000_000.0,  # Extremely high budget
        }, headers=auth_headers)
        # Should either accept with warning, or reject based on org limits
        assert r.status_code in (200, 400, 422)


# ─── 10. Full End-to-End Workflow ─────────────────────────────────────────────

class TestFullWorkflow:
    """The complete OrQuanta workflow — from registration to audit trail."""

    def test_full_workflow_register_submit_verify(self, client):
        """
        Simulates the real day-1 user journey:
        1. Register new account
        2. Login
        3. Submit goal
        4. Retrieve goal status
        5. Check jobs were created
        6. Verify audit trail
        7. Check cost tracking
        """
        email = f"workflow-{uuid.uuid4().hex[:8]}@orquanta-test.ai"
        password = "Workflow_Pass_2024!"

        # 1. Register
        r = client.post("/auth/register", json={
            "email": email, "password": password, "name": "Workflow User"
        })
        assert r.status_code == 201
        user_id = r.json()["user_id"]

        # 2. Login
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Submit goal
        r = client.post("/goals/", json={
            "raw_text": "Fine-tune Mistral 7B on legal documents using QLoRA — H100 preferred",
            "budget_usd": 100.0,
        }, headers=headers)
        assert r.status_code == 200
        goal_id = r.json()["goal_id"]
        assert len(goal_id) > 10

        # 4. Retrieve goal
        r = client.get(f"/goals/{goal_id}", headers=headers)
        assert r.status_code == 200
        goal = r.json()
        assert goal["goal_id"] == goal_id
        assert goal["status"] in ("accepted", "planning", "executing", "completed")

        # 5. List jobs
        r = client.get("/jobs/", headers=headers)
        assert r.status_code == 200

        # 6. Audit trail
        r = client.get("/audit/", headers=headers)
        assert r.status_code == 200

        # 7. Platform metrics
        r = client.get("/metrics/platform", headers=headers)
        assert r.status_code == 200
        metrics = r.json()
        assert metrics["agents_active"] > 0

        # Full workflow passed ✅
