"""
OrQuanta Agentic v1.0 — Safety Governor Adversarial Tests
"""

import asyncio
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from v4.agents.safety_governor import SafetyGovernor, PolicyViolation, EmergencyStop


class TestSafetyGovernor:
    def setup_method(self):
        self.gov = SafetyGovernor()

    # ------------------------------------------------------------------
    # Emergency Stop
    # ------------------------------------------------------------------
    def test_emergency_stop_triggers(self):
        self.gov.trigger_emergency_stop("Test stop")
        assert self.gov.is_stopped is True
        assert self.gov._stop_reason == "Test stop"

    def test_emergency_stop_clear_wrong_token(self):
        self.gov.trigger_emergency_stop("Test")
        result = self.gov.clear_emergency_stop("wrong-token")
        assert result is False
        assert self.gov.is_stopped is True

    def test_emergency_stop_clear_correct_token(self):
        self.gov.trigger_emergency_stop("Test")
        os.environ["SAFETY_OVERRIDE_TOKEN"] = "test-override"
        result = self.gov.clear_emergency_stop("test-override")
        assert result is True
        assert self.gov.is_stopped is False

    # ------------------------------------------------------------------
    # Rate Limiting
    # ------------------------------------------------------------------
    def test_rate_limit_allows_within_limit(self):
        gov = SafetyGovernor()
        gov.rate_limit_per_minute = 5
        for _ in range(5):
            gov._check_rate_limit("test-agent")  # Should not raise

    def test_rate_limit_blocks_over_limit(self):
        gov = SafetyGovernor()
        gov.rate_limit_per_minute = 3
        for _ in range(3):
            gov._check_rate_limit("test-agent")
        with pytest.raises(PolicyViolation) as exc:
            gov._check_rate_limit("test-agent")
        assert "AgentRateLimit" in str(exc.value)

    def test_rate_limit_per_agent_independent(self):
        gov = SafetyGovernor()
        gov.rate_limit_per_minute = 2
        gov._check_rate_limit("agent-A")
        gov._check_rate_limit("agent-A")
        # agent-B should still work
        gov._check_rate_limit("agent-B")
        gov._check_rate_limit("agent-B")

    # ------------------------------------------------------------------
    # Daily Spend Cap
    # ------------------------------------------------------------------
    def test_daily_spend_cap_allows_under_limit(self):
        gov = SafetyGovernor()
        gov.max_daily_spend_usd = 1000.0
        gov._check_daily_spend(999.0)  # Should not raise

    def test_daily_spend_cap_blocks_over_limit(self):
        gov = SafetyGovernor()
        gov.max_daily_spend_usd = 100.0
        gov._daily_spend = 90.0
        with pytest.raises(PolicyViolation) as exc:
            gov._check_daily_spend(20.0)  # Would total 110 > 100
        assert "DailySpendCap" in str(exc.value)

    # ------------------------------------------------------------------
    # Authorize and Run
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_authorize_runs_function(self):
        gov = SafetyGovernor()
        executed = []

        async def my_fn():
            executed.append(True)
            return {"status": "done"}

        result = await gov.authorize_and_run(
            agent_name="test_agent",
            action="test_action",
            reasoning="Testing authorize_and_run",
            payload={},
            cost_estimate_usd=1.0,
            fn=my_fn,
        )
        assert result["approved"] is True
        assert result["result"]["status"] == "done"
        assert len(executed) == 1

    @pytest.mark.asyncio
    async def test_authorize_blocks_on_emergency_stop(self):
        gov = SafetyGovernor()
        gov.trigger_emergency_stop("ADVERSARIAL TEST")

        async def my_fn(): return {}

        with pytest.raises(EmergencyStop):
            await gov.authorize_and_run("agent", "action", "reason", {}, 0.0, my_fn)

    @pytest.mark.asyncio
    async def test_authorize_logs_to_audit(self):
        gov = SafetyGovernor()

        async def my_fn(): return {"ok": True}

        await gov.authorize_and_run("scheduler", "schedule", "reason", {"gpu": "H100"}, 5.0, my_fn)
        log = gov.get_audit_log()
        assert len(log) == 1
        assert log[0]["agent_name"] == "scheduler"
        assert log[0]["action"] == "schedule"
        assert log[0]["cost_impact"] == 5.0

    @pytest.mark.asyncio
    async def test_audit_log_records_failure(self):
        gov = SafetyGovernor()

        async def failing_fn():
            raise RuntimeError("Simulated failure")

        with pytest.raises(RuntimeError):
            await gov.authorize_and_run("healer", "restart", "test", {}, 0.0, failing_fn)

        log = gov.get_audit_log()
        assert len(log) == 1
        assert "error" in log[0]["outcome"]

    # ------------------------------------------------------------------
    # Stats and Summary
    # ------------------------------------------------------------------
    def test_get_stats_structure(self):
        stats = self.gov.get_stats()
        assert "emergency_stop_active" in stats
        assert "total_actions_logged" in stats
        assert "daily_spend_usd" in stats
        assert "daily_cap_usd" in stats

    def test_spend_summary_structure(self):
        summary = self.gov.get_spend_summary()
        assert "daily_spend_usd" in summary
        assert "daily_cap_usd" in summary
        assert "remaining_usd" in summary
        assert summary["remaining_usd"] <= summary["daily_cap_usd"]
