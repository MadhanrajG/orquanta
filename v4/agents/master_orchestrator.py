"""
OrQuanta Agentic v1.0 — Master Orchestrator

Central brain of the OrQuanta platform. Uses the ReAct pattern
(Reason → Act → Observe → Repeat) to:
1. Accept natural-language goals from users
2. Decompose them into concrete sub-tasks via LLM
3. Dispatch to specialist agents via Redis Streams
4. Monitor progress and handle agent failures
5. Synthesise final results and update memory
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .llm_reasoning_engine import LLMReasoningEngine
from .memory_manager import MemoryManager
from .safety_governor import get_governor
from .tool_registry import ToolRegistry

logger = logging.getLogger("orquanta.orchestrator")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
MAX_REACT_ITERATIONS = int(os.getenv("ORCHESTRATOR_MAX_ITERATIONS", "10"))


class GoalExecution:
    """Tracks the state of a single goal execution."""

    def __init__(self, goal_id: str, raw_text: str, user_id: str) -> None:
        self.goal_id = goal_id
        self.raw_text = raw_text
        self.user_id = user_id
        self.status = "decomposing"
        self.plan: dict[str, Any] = {}
        self.tasks: list[dict[str, Any]] = []
        self.completed_tasks: list[str] = []
        self.failed_tasks: list[str] = []
        self.result: dict[str, Any] = {}
        self.cost_incurred_usd = 0.0
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.reasoning_log: list[dict[str, Any]] = []

    def log_reasoning(self, step: str, content: Any) -> None:
        """Append a ReAct reasoning step to the log."""
        self.reasoning_log.append({
            "step": step,
            "content": content,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "raw_text": self.raw_text,
            "user_id": self.user_id,
            "status": self.status,
            "plan": self.plan,
            "tasks": self.tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "result": self.result,
            "cost_incurred_usd": round(self.cost_incurred_usd, 4),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reasoning_steps": len(self.reasoning_log),
        }


class MasterOrchestrator:
    """ReAct-pattern orchestrator that drives OrQuanta goal execution.

    The orchestrator processes goals through a structured loop:

    REASON: Call LLM to decompose goal into tasks, analysing prior memory.
    ACT:    Dispatch tasks to specialist agents (or execute directly).
    OBSERVE: Collect results, detect failures, update memory.
    REPEAT: If goal not satisfied, generate next round of tasks.

    Usage::

        orchestrator = MasterOrchestrator()
        await orchestrator.start()

        goal_id = await orchestrator.submit_goal(
            raw_text="Train a LLaMA 3 70B model on our medical dataset",
            user_id="user-123",
        )
        
        # Poll for result
        status = orchestrator.get_goal_status(goal_id)
    """

    def __init__(self) -> None:
        self.llm = LLMReasoningEngine()
        self.memory = MemoryManager()
        self.tools = ToolRegistry()
        self.governor = get_governor()
        self._goals: dict[str, GoalExecution] = {}
        self._agent_status: dict[str, str] = {
            "scheduler_agent": "idle",
            "cost_optimizer_agent": "idle",
            "healing_agent": "idle",
            "forecast_agent": "idle",
        }
        self._running = False
        self._redis = None
        logger.info("MasterOrchestrator initialised.")

    async def start(self) -> None:
        """Start the orchestrator background loops."""
        self._running = True
        await self._init_redis()
        asyncio.create_task(self._goal_processor_loop())
        asyncio.create_task(self._agent_heartbeat_loop())
        logger.info("MasterOrchestrator started (ReAct engine active).")

    async def stop(self) -> None:
        """Gracefully shut down the orchestrator."""
        self._running = False
        logger.info("MasterOrchestrator stopped.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit_goal(self, raw_text: str, user_id: str) -> str:
        """Submit a natural-language goal for autonomous execution.

        Args:
            raw_text: Goal description in plain English.
            user_id: User submitting the goal.

        Returns:
            goal_id string for polling status.
        """
        goal_id = str(uuid4())
        execution = GoalExecution(goal_id=goal_id, raw_text=raw_text, user_id=user_id)
        self._goals[goal_id] = execution

        logger.info(f"[Orchestrator] Goal submitted: {goal_id} — '{raw_text[:80]}...'")

        # Kick off processing asynchronously
        asyncio.create_task(self._execute_goal(execution))

        return goal_id

    def get_goal_status(self, goal_id: str) -> dict[str, Any] | None:
        """Return current status of a goal execution."""
        ex = self._goals.get(goal_id)
        return ex.to_dict() if ex else None

    def get_all_goals(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """Return all goals, optionally filtered by user."""
        goals = list(self._goals.values())
        if user_id:
            goals = [g for g in goals if g.user_id == user_id]
        return [g.to_dict() for g in goals]

    def get_agent_statuses(self) -> dict[str, str]:
        """Return the current status of all specialist agents."""
        return self._agent_status.copy()

    def get_reasoning_log(self, goal_id: str) -> list[dict[str, Any]]:
        """Return the full ReAct reasoning log for a goal."""
        ex = self._goals.get(goal_id)
        return ex.reasoning_log if ex else []

    # ------------------------------------------------------------------
    # ReAct Execution Engine
    # ------------------------------------------------------------------

    async def _execute_goal(self, ex: GoalExecution) -> None:
        """Main ReAct loop for a single goal."""
        logger.info(f"[ReAct] Starting execution: {ex.goal_id}")

        try:
            # === REASON: Decompose goal into tasks ===
            ex.log_reasoning("REASON", f"Decomposing goal: {ex.raw_text}")
            self._agent_status["scheduler_agent"] = "thinking"

            # Search memory for similar past goals
            past_outcomes = await self.memory.search(ex.raw_text, n_results=3)
            ex.log_reasoning("OBSERVE_MEMORY", past_outcomes)

            # Call LLM to decompose
            plan = await self.llm.reason(
                template_name="orchestrator_decompose",
                variables={
                    "goal": ex.raw_text,
                    "past_context": past_outcomes,
                },
                agent_name="master_orchestrator",
            )

            ex.plan = plan
            ex.tasks = plan.get("tasks", [])
            ex.status = "running"
            ex.log_reasoning("ACT", f"Plan created with {len(ex.tasks)} tasks.")
            logger.info(
                f"[ReAct] Goal {ex.goal_id} decomposed into {len(ex.tasks)} tasks. "
                f"Est. cost: ${plan.get('estimated_cost_usd', 0):.2f}"
            )

            # === ACT: Execute tasks ===
            for iteration in range(MAX_REACT_ITERATIONS):
                pending = [
                    t for t in ex.tasks
                    if t["task_id"] not in ex.completed_tasks
                    and t["task_id"] not in ex.failed_tasks
                ]

                if not pending:
                    break

                # Find tasks whose dependencies are satisfied
                ready = [
                    t for t in pending
                    if all(dep in ex.completed_tasks for dep in t.get("depends_on", []))
                ]

                if not ready:
                    ex.log_reasoning(
                        "OBSERVE",
                        f"Waiting for dependency tasks at iteration {iteration + 1}.",
                    )
                    await asyncio.sleep(2)
                    continue

                ex.log_reasoning("ACT", f"Iteration {iteration + 1}: executing {len(ready)} ready tasks.")

                # Execute ready tasks (with concurrency)
                task_coroutines = [self._dispatch_task(ex, t) for t in ready]
                await asyncio.gather(*task_coroutines, return_exceptions=True)

                # === OBSERVE: Check if goal is satisfied ===
                if len(ex.completed_tasks) == len(ex.tasks):
                    break

                if len(ex.failed_tasks) > 0:
                    # Let LLM decide if we should re-plan or abort
                    should_continue = await self._handle_failures(ex)
                    if not should_continue:
                        ex.status = "failed"
                        ex.log_reasoning("OBSERVE", "Goal failed after unrecoverable task failures.")
                        return

            # === Final synthesis ===
            ex.status = "completed"
            ex.result = {
                "summary": f"Goal '{ex.raw_text[:60]}...' completed.",
                "tasks_completed": len(ex.completed_tasks),
                "tasks_failed": len(ex.failed_tasks),
                "total_cost_usd": ex.cost_incurred_usd,
                "plan_reasoning": plan.get("reasoning", ""),
            }
            ex.log_reasoning("OBSERVE", "Goal completed successfully.")

            # Store outcome in memory for future goals
            await self.memory.store_event({
                "type": "goal_completed",
                "goal_id": ex.goal_id,
                "goal_text": ex.raw_text,
                "cost_usd": ex.cost_incurred_usd,
                "tasks_count": len(ex.tasks),
                "outcome": "success",
            }, agent_name="master_orchestrator")

            logger.info(
                f"[ReAct] Goal {ex.goal_id} COMPLETED. "
                f"Tasks: {len(ex.completed_tasks)}/{len(ex.tasks)}, "
                f"Cost: ${ex.cost_incurred_usd:.2f}"
            )

        except Exception as exc:
            ex.status = "failed"
            ex.result = {"error": str(exc)}
            ex.log_reasoning("ERROR", str(exc))
            logger.error(f"[ReAct] Goal {ex.goal_id} FAILED: {exc}", exc_info=True)

        finally:
            for agent in self._agent_status:
                self._agent_status[agent] = "idle"

    async def _dispatch_task(
        self, ex: GoalExecution, task: dict[str, Any]
    ) -> None:
        """Dispatch a single task to the appropriate agent."""
        task_id = task["task_id"]
        agent = task["agent"]
        action = task["action"]
        params = task.get("parameters", {})

        self._agent_status[agent] = "acting"
        ex.log_reasoning("ACT", f"Dispatching task {task_id} to {agent}: {action}")
        logger.info(f"[Orchestrator] Task {task_id} → {agent}.{action}")

        try:
            result = await self._call_agent(agent, action, params)
            ex.completed_tasks.append(task_id)

            # Track cost if agent returns it
            cost = result.get("estimated_hourly_cost", 0) if isinstance(result, dict) else 0
            ex.cost_incurred_usd += cost

            ex.log_reasoning("OBSERVE", f"Task {task_id} completed: {result}")

        except Exception as exc:
            ex.failed_tasks.append(task_id)
            ex.log_reasoning("OBSERVE", f"Task {task_id} FAILED: {exc}")
            logger.error(f"[Orchestrator] Task {task_id} FAILED: {exc}")

        finally:
            self._agent_status[agent] = "idle"

    async def _call_agent(
        self, agent: str, action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Route an action call to the correct specialist agent.
        
        In production this publishes to Redis Streams and waits for the
        agent process to respond. In this local mode, calls are handled
        directly for simplicity.
        """
        # Direct in-process call (Redis Stream delegation for separate workers)
        if agent == "scheduler_agent":
            return await self._call_scheduler(action, params)
        if agent == "cost_optimizer_agent":
            return await self._call_cost_optimizer(action, params)
        if agent == "healing_agent":
            return await self._call_healing(action, params)
        if agent == "forecast_agent":
            return await self._call_forecast(action, params)

        raise ValueError(f"Unknown agent: {agent}")

    async def _call_scheduler(self, action: str, params: dict) -> dict:
        """Delegate to SchedulerAgent."""
        from .scheduler_agent import SchedulerAgent
        agent = SchedulerAgent()
        if action == "schedule_job":
            return await agent.schedule_job(**params)
        if action == "get_queue_status":
            return agent.get_queue_status()
        raise ValueError(f"Unknown scheduler action: {action}")

    async def _call_cost_optimizer(self, action: str, params: dict) -> dict:
        """Delegate to CostOptimizerAgent."""
        from .cost_optimizer_agent import CostOptimizerAgent
        agent = CostOptimizerAgent()
        if action == "find_cheapest_spot":
            return await agent.find_cheapest_spot(**params)
        if action == "forecast_cost":
            return await agent.forecast_cost(**params)
        raise ValueError(f"Unknown cost_optimizer action: {action}")

    async def _call_healing(self, action: str, params: dict) -> dict:
        """Delegate to HealingAgent."""
        from .healing_agent import HealingAgent
        agent = HealingAgent()
        if action == "monitor_job":
            return await agent.start_monitoring(**params)
        raise ValueError(f"Unknown healing action: {action}")

    async def _call_forecast(self, action: str, params: dict) -> dict:
        """Delegate to ForecastAgent."""
        from .forecast_agent import ForecastAgent
        agent = ForecastAgent()
        if action == "run_forecast":
            return await agent.run_forecast(**params)
        raise ValueError(f"Unknown forecast action: {action}")

    async def _handle_failures(self, ex: GoalExecution) -> bool:
        """Decide whether to re-plan or abort after task failures.
        
        Returns:
            True to continue, False to abort.
        """
        ex.log_reasoning("REASON", f"Handling {len(ex.failed_tasks)} failed tasks.")
        # Simple policy: abort if >50% of tasks failed
        fail_rate = len(ex.failed_tasks) / max(len(ex.tasks), 1)
        if fail_rate > 0.5:
            logger.warning(f"[Orchestrator] Goal {ex.goal_id}: fail rate {fail_rate:.0%} — aborting.")
            return False
        logger.info(f"[Orchestrator] Goal {ex.goal_id}: fail rate {fail_rate:.0%} — continuing.")
        return True

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    async def _goal_processor_loop(self) -> None:
        """Monitor active goals and log progress."""
        while self._running:
            running = [g for g in self._goals.values() if g.status == "running"]
            if running:
                logger.debug(f"[Orchestrator] {len(running)} goals in progress.")
            await asyncio.sleep(5)

    async def _agent_heartbeat_loop(self) -> None:
        """Periodically check agent health via Redis (stub in local mode)."""
        while self._running:
            await asyncio.sleep(30)
            logger.debug("[Orchestrator] Agent heartbeat check.")

    async def _init_redis(self) -> None:
        """Initialise Redis connection for inter-agent messaging."""
        try:
            import redis.asyncio as redis  # type: ignore
            self._redis = redis.from_url(REDIS_URL, decode_responses=True)
            await self._redis.ping()
            logger.info(f"Redis connected: {REDIS_URL}")
        except Exception as exc:
            logger.warning(f"Redis unavailable ({exc}). Running in single-process mode.")
            self._redis = None
