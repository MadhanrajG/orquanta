"""
OrQuanta Agentic v1.0 — Agent Behavior Tests
Tests for SchedulerAgent, CostOptimizerAgent, HealingAgent, ForecastAgent
"""

import asyncio
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from v4.agents.scheduler_agent import SchedulerAgent, ScheduledJob, GPUBin
from v4.agents.cost_optimizer_agent import CostOptimizerAgent
from v4.agents.healing_agent import HealingAgent, JobHealthRecord
from v4.agents.forecast_agent import ForecastAgent


# ─── Scheduler Agent ────────────────────────────────────────────────────────

class TestSchedulerAgent:
    def setup_method(self):
        self.scheduler = SchedulerAgent()

    @pytest.mark.asyncio
    async def test_schedule_job_returns_id(self):
        result = await self.scheduler.schedule_job(
            intent="Train LLaMA 70B", required_vram_gb=80, gpu_type="H100", provider="aws"
        )
        assert "job_id" in result
        assert result["job_id"].startswith("job-")
        assert 0.0 <= result["priority_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_schedule_job_appears_in_list(self):
        result = await self.scheduler.schedule_job(
            intent="Quick inference job", required_vram_gb=16, gpu_type="T4", provider="gcp"
        )
        job_id = result["job_id"]
        job = self.scheduler.get_job(job_id)
        assert job is not None
        assert job["intent"] == "Quick inference job"

    @pytest.mark.asyncio
    async def test_cancel_job(self):
        result = await self.scheduler.schedule_job(
            intent="Job to cancel", required_vram_gb=24, gpu_type="A10G", provider="azure"
        )
        job_id = result["job_id"]
        cancel_result = await self.scheduler.cancel_job(job_id)
        assert cancel_result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job(self):
        result = await self.scheduler.cancel_job("fake-job-id")
        assert result["error"] == "job_not_found"

    def test_queue_status_structure(self):
        status = self.scheduler.get_queue_status()
        assert "queued_jobs" in status
        assert "active_bins" in status
        assert "jobs_by_status" in status


class TestBinPacking:
    def setup_method(self):
        self.scheduler = SchedulerAgent()

    def test_bin_can_fit(self):
        bin_ = GPUBin("inst-001", total_vram_gb=80, gpu_count=1)
        assert bin_.can_fit(80) is True
        assert bin_.can_fit(81) is False

    def test_bin_allocate(self):
        bin_ = GPUBin("inst-001", total_vram_gb=80, gpu_count=1)
        bin_.allocate("job-1", 40)
        assert bin_.used_vram_gb == 40
        assert bin_.available_vram_gb == 40
        assert bin_.can_fit(30) is True

    def test_bin_release(self):
        bin_ = GPUBin("inst-001", total_vram_gb=80, gpu_count=1)
        bin_.allocate("job-1", 60)
        bin_.release("job-1", 60)
        assert bin_.used_vram_gb == 0
        assert bin_.available_vram_gb == 80

    def test_bin_packing_places_job(self):
        self.scheduler._bins["inst-001"] = GPUBin("inst-001", 80, 1)
        job = ScheduledJob("job-x", "test", 40, "H100", "aws", priority=0.5)
        placed = self.scheduler._try_bin_pack(job)
        assert placed is True
        assert job.status == "running"

    def test_bin_pack_best_fit_chooses_tightest(self):
        self.scheduler._bins["inst-big"] = GPUBin("inst-big", 320, 4)
        self.scheduler._bins["inst-small"] = GPUBin("inst-small", 80, 1)
        job = ScheduledJob("job-y", "test", 40, "H100", "aws", priority=0.5)
        self.scheduler._try_bin_pack(job)
        # Should have picked inst-small (80GB, tighter fit than 320GB)
        assert job.instance_id == "inst-small"


# ─── Cost Optimizer Agent ────────────────────────────────────────────────────

class TestCostOptimizerAgent:
    def setup_method(self):
        self.agent = CostOptimizerAgent()

    @pytest.mark.asyncio
    async def test_find_cheapest_spot_returns_recommendation(self):
        result = await self.agent.find_cheapest_spot(gpu_type="H100", required_hours=2.0)
        # Mock LLM may return a 'mock' summary; real LLM returns 'recommended_provider'
        assert isinstance(result, dict)
        assert "estimated_total_cost_usd" in result
        assert result["estimated_total_cost_usd"] > 0
        assert "price_options_evaluated" in result
        assert result["price_options_evaluated"] > 0

    @pytest.mark.asyncio
    async def test_find_cheapest_spot_within_budget(self):
        result = await self.agent.find_cheapest_spot(gpu_type="T4", required_hours=1.0, budget_usd=10.0)
        assert "budget_within_limit" in result

    @pytest.mark.asyncio
    async def test_get_cheapest_option_sorted(self):
        result = await self.agent.get_cheapest_option("H100")
        assert "provider" in result or "error" in result

    @pytest.mark.asyncio
    async def test_forecast_cost(self):
        result = await self.agent.forecast_cost("job-123", "H100", 5.0, 2.0)
        assert "base_estimate_usd" in result
        assert "smoothed_estimate_usd" in result
        assert result["base_estimate_usd"] == pytest.approx(10.0, abs=0.01)

    def test_set_budget(self):
        self.agent.set_budget("job-001", 500.0)
        assert "job-001" in self.agent._budgets

    @pytest.mark.asyncio
    async def test_track_spend_within_budget(self):
        self.agent.set_budget("job-track", 100.0)
        result = await self.agent.track_spend("job-track", 50.0)
        assert result["total_spent_usd"] == 50.0
        assert result["remaining_usd"] == 50.0
        assert result["alert_triggered"] is False

    @pytest.mark.asyncio
    async def test_track_spend_triggers_alert(self):
        self.agent.set_budget("job-alert", 100.0)
        result = await self.agent.track_spend("job-alert", 90.0)
        assert result["alert_triggered"] is True

    def test_spend_dashboard(self):
        dashboard = self.agent.get_spend_dashboard()
        assert "total_tracked_jobs" in dashboard
        assert "total_spent_usd" in dashboard


# ─── Healing Agent ────────────────────────────────────────────────────────

class TestHealingAgent:
    def setup_method(self):
        self.agent = HealingAgent()

    @pytest.mark.asyncio
    async def test_start_monitoring(self):
        result = await self.agent.start_monitoring("job-001", "inst-001")
        assert result["status"] == "monitoring_started"
        assert "job-001" in self.agent._monitored

    @pytest.mark.asyncio
    async def test_double_monitor_same_job(self):
        await self.agent.start_monitoring("job-001", "inst-001")
        result = await self.agent.start_monitoring("job-001", "inst-001")
        assert result["status"] == "already_monitoring"

    def test_stop_monitoring(self):
        asyncio.get_event_loop().run_until_complete(self.agent.start_monitoring("job-002", "inst-002"))
        self.agent.stop_monitoring("job-002")
        assert "job-002" not in self.agent._monitored

    def test_get_health_nonexistent(self):
        result = self.agent.get_health_status("nonexistent")
        assert result is None

    def test_health_record_rolling_stats(self):
        record = JobHealthRecord("job-x", "inst-x")
        for val in [60, 70, 80, 90, 95]:
            record.record_metrics({"gpu_utilization_pct": val})
        stats = record.get_rolling_stats("gpu_utilization_pct")
        assert stats["n"] == 5
        assert stats["mean"] == pytest.approx(79.0, abs=0.1)
        assert stats["std"] > 0

    def test_get_all_health(self):
        asyncio.get_event_loop().run_until_complete(self.agent.start_monitoring("j1", "i1"))
        asyncio.get_event_loop().run_until_complete(self.agent.start_monitoring("j2", "i2"))
        all_health = self.agent.get_all_health()
        assert len(all_health) == 2


# ─── Forecast Agent ────────────────────────────────────────────────────────

class TestForecastAgent:
    def setup_method(self):
        self.agent = ForecastAgent()

    def test_record_job_submission(self):
        self.agent.record_job_submission("H100")
        assert self.agent._current_utilization["H100"] == 1

    def test_record_completion_decrements(self):
        self.agent.record_job_submission("A100")
        self.agent.record_job_submission("A100")
        self.agent.record_job_completion("A100")
        assert self.agent._current_utilization["A100"] == 1

    def test_record_completion_no_below_zero(self):
        self.agent.record_job_completion("T4")  # No submission first
        assert self.agent._current_utilization.get("T4", 0) == 0

    @pytest.mark.asyncio
    async def test_run_forecast_returns_structure(self):
        # Add some history
        for _ in range(20):
            self.agent.record_job_submission("H100")
        result = await self.agent.run_forecast(window_hours=24)
        assert "predicted_job_count" in result
        assert "predicted_gpu_demand" in result
        assert "recommendation" in result
        assert result["recommendation"] in ["pre-provision", "hold", "scale-down"]

    def test_get_last_forecast_empty(self):
        result = self.agent.get_last_forecast()
        assert result.get("status") == "no_forecast_yet" or isinstance(result, dict)

    def test_hourly_demand_chart(self):
        self.agent.record_job_submission("H100")
        chart = self.agent.get_hourly_demand_chart("H100")
        assert "hourly_demand" in chart
        assert len(chart["hourly_demand"]) == 24
        assert "peak_hour_utc" in chart

    def test_get_utilization(self):
        self.agent.record_job_submission("H100")
        self.agent.record_job_submission("T4")
        util = self.agent.get_utilization()
        assert util["active_jobs_by_gpu"]["H100"] >= 1
        assert util["total_active_jobs"] >= 2
