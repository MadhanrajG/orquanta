"""
OrQuanta Agentic v1.0 — MasterOrchestrator Unit Tests
"""

import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from v4.agents.master_orchestrator import MasterOrchestrator, GoalExecution


class TestGoalExecution:
    def test_creates_with_correct_fields(self):
        ex = GoalExecution("goal-001", "Train a model", "user-1")
        assert ex.goal_id == "goal-001"
        assert ex.raw_text == "Train a model"
        assert ex.user_id == "user-1"
        assert ex.status == "decomposing"
        assert ex.cost_incurred_usd == 0.0

    def test_log_reasoning_appends(self):
        ex = GoalExecution("g1", "test", "u1")
        ex.log_reasoning("REASON", "Analysing…")
        ex.log_reasoning("ACT", "Dispatching…")
        assert len(ex.reasoning_log) == 2
        assert ex.reasoning_log[0]["step"] == "REASON"
        assert ex.reasoning_log[1]["step"] == "ACT"

    def test_to_dict_complete(self):
        ex = GoalExecution("g2", "Deploy models", "u2")
        d = ex.to_dict()
        assert "goal_id" in d
        assert "status" in d
        assert "cost_incurred_usd" in d
        assert "reasoning_steps" in d
        assert d["reasoning_steps"] == 0


class TestMasterOrchestrator:
    def setup_method(self):
        self.orch = MasterOrchestrator()

    def test_initialises(self):
        assert self.orch is not None
        assert len(self.orch._agent_status) == 4
        for status in self.orch._agent_status.values():
            assert status == "idle"

    def test_get_nonexistent_goal_returns_none(self):
        assert self.orch.get_goal_status("nonexistent-id") is None

    def test_get_all_goals_empty(self):
        goals = self.orch.get_all_goals()
        assert isinstance(goals, list)

    def test_get_all_goals_user_filter(self):
        self.orch._goals["g1"] = GoalExecution("g1", "test 1", "user-A")
        self.orch._goals["g2"] = GoalExecution("g2", "test 2", "user-B")
        user_a_goals = self.orch.get_all_goals(user_id="user-A")
        assert len(user_a_goals) == 1
        assert user_a_goals[0]["user_id"] == "user-A"

    def test_agent_statuses(self):
        statuses = self.orch.get_agent_statuses()
        assert "scheduler_agent" in statuses
        assert "cost_optimizer_agent" in statuses
        assert "healing_agent" in statuses
        assert "forecast_agent" in statuses

    @pytest.mark.asyncio
    async def test_submit_goal_returns_id(self):
        await self.orch.start()
        goal_id = await self.orch.submit_goal("Train a 7B model", "user-1")
        assert goal_id is not None
        assert len(goal_id) > 0
        # Allow async task to kick off
        await asyncio.sleep(0.5)
        status = self.orch.get_goal_status(goal_id)
        assert status is not None
        assert status["raw_text"] == "Train a 7B model"
        await self.orch.stop()

    @pytest.mark.asyncio
    async def test_goal_reasoning_log(self):
        await self.orch.start()
        goal_id = await self.orch.submit_goal("Run inference job", "user-2")
        await asyncio.sleep(1.5)  # Let orchestrator process
        log = self.orch.get_reasoning_log(goal_id)
        assert isinstance(log, list)
        await self.orch.stop()

    @pytest.mark.asyncio
    async def test_handle_failures_abort_threshold(self):
        ex = GoalExecution("g-fail", "Failing goal", "u1")
        ex.tasks = [{"task_id": f"t-{i}", "agent": "scheduler_agent", "action": "x", "parameters": {}} for i in range(10)]
        ex.failed_tasks = [f"t-{i}" for i in range(6)]  # 60% fail rate
        result = await self.orch._handle_failures(ex)
        assert result is False  # Should abort

    @pytest.mark.asyncio
    async def test_handle_failures_continue_below_threshold(self):
        ex = GoalExecution("g-ok", "Partial fail goal", "u1")
        ex.tasks = [{"task_id": f"t-{i}", "agent": "scheduler_agent", "action": "x", "parameters": {}} for i in range(10)]
        ex.failed_tasks = [f"t-{i}" for i in range(3)]  # 30% fail rate
        result = await self.orch._handle_failures(ex)
        assert result is True  # Should continue
