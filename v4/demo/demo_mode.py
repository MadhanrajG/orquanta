"""
OrQuanta Agentic v1.0 — Demo Mode Engine
=========================================

When DEMO_MODE=true (or --demo flag), all provider API calls
return realistic simulated responses instead of hitting live cloud APIs.

Features:
  - Realistic GPU job lifecycle simulation
  - 5-second simulated provisioning
  - Live metrics (util 60-95%, memory 40-80%, temp 65-78°C)
  - 10% failure rate with auto-recovery showcase
  - WebSocket push for dashboard live view
  - Pre-built scenarios (cost savings, self-healing, NL goal)

Usage:
    from v4.demo.demo_mode import DemoEngine
    demo = DemoEngine()
    await demo.start()        # activates demo mode globally
    await demo.run_scenario("cost_optimizer")
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger("orquanta.demo")

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")


# ─── Demo Job States ──────────────────────────────────────────────────────────

class JobPhase(str, Enum):
    QUEUED       = "queued"
    PROVISIONING = "provisioning"
    STARTING     = "starting"
    RUNNING      = "running"
    HEALING      = "healing"
    COMPLETE     = "complete"
    FAILED       = "failed"


@dataclass
class DemoJob:
    job_id:       str
    goal:         str
    gpu_type:     str
    provider:     str
    region:       str
    phase:        JobPhase = JobPhase.QUEUED
    progress_pct: float    = 0.0
    gpu_util:     float    = 0.0
    memory_pct:   float    = 0.0
    temp_c:       float    = 65.0
    loss:         float    = 3.5
    cost_so_far:  float    = 0.0
    cost_per_hr:  float    = 1.99
    saved_vs_aws: float    = 0.0
    started_at:   str      = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_min: int      = 30
    error_msg:    str      = ""
    healed:       bool     = False
    heal_count:   int      = 0


# ─── Event Types ─────────────────────────────────────────────────────────────

@dataclass
class DemoEvent:
    """WebSocket event pushed to connected clients."""
    event_type: str         # agent_thought | job_progress | healing_event | cost_update | complete
    data:       dict        # event payload
    timestamp:  str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {"type": self.event_type, "data": self.data, "ts": self.timestamp}


# ─── Demo Engine ─────────────────────────────────────────────────────────────

class DemoEngine:
    """
    Core demo orchestrator. Manages demo jobs, generates events,
    and pushes realistic metrics to WebSocket subscribers.
    """

    def __init__(self) -> None:
        self._active = False
        self._jobs: dict[str, DemoJob] = {}
        self._subscribers: list[Callable[[DemoEvent], Awaitable[None]]] = []
        self._bg_tasks: list[asyncio.Task] = []

        # Lambda Labs pricing for reference
        self._lambda_prices = {
            "gpu_1x_a10":        0.75,
            "gpu_1x_a100":       1.99,
            "gpu_1x_h100_pcie":  2.99,
            "gpu_8x_a100":      14.32,
        }
        # AWS on-demand for savings calculation
        self._aws_prices = {
            "gpu_1x_a10":        1.10,
            "gpu_1x_a100":       4.10,
            "gpu_1x_h100_pcie":  6.50,
            "gpu_8x_a100":      32.77,
        }

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Activate demo mode and start background metric generator."""
        global DEMO_MODE
        DEMO_MODE = True
        self._active = True
        logger.info("[Demo] Demo mode ACTIVE — all provider calls are simulated")
        self._bg_tasks.append(asyncio.create_task(self._global_heartbeat()))

    async def stop(self) -> None:
        """Deactivate demo mode."""
        self._active = False
        for t in self._bg_tasks:
            t.cancel()
        self._bg_tasks.clear()

    def is_active(self) -> bool:
        return self._active

    # ─── Subscription ─────────────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[DemoEvent], Awaitable[None]]) -> None:
        """Subscribe to demo events (for WebSocket broadcasting)."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[DemoEvent], Awaitable[None]]) -> None:
        self._subscribers = [s for s in self._subscribers if s != callback]

    async def _emit(self, event: DemoEvent) -> None:
        """Broadcast event to all subscribers."""
        for sub in self._subscribers:
            try:
                await sub(event)
            except Exception:
                pass

    # ─── Job Simulation ───────────────────────────────────────────────────────

    async def submit_demo_job(
        self,
        goal: str,
        gpu_type: str = "gpu_1x_a100",
        provider: str = "lambda",
        duration_min: int = 30,
        inject_failure: bool = False,
    ) -> DemoJob:
        """Create and start simulating a GPU job."""
        job_id = f"demo-{uuid.uuid4().hex[:8]}"
        lambda_price = self._lambda_prices.get(gpu_type, 1.99)
        aws_price    = self._aws_prices.get(gpu_type, 4.10)
        savings_rate = aws_price - lambda_price

        job = DemoJob(
            job_id=job_id,
            goal=goal,
            gpu_type=gpu_type,
            provider=provider,
            region="us-tx-3",
            cost_per_hr=lambda_price,
            saved_vs_aws=0.0,
            duration_min=duration_min,
        )
        self._jobs[job_id] = job

        # Start simulation task
        task = asyncio.create_task(
            self._simulate_job(job, inject_failure=inject_failure, savings_rate=savings_rate)
        )
        self._bg_tasks.append(task)
        logger.info(f"[Demo] Job {job_id} started: {goal[:50]}")
        return job

    async def _simulate_job(
        self, job: DemoJob, inject_failure: bool, savings_rate: float
    ) -> None:
        """Full lifecycle simulation for one demo job."""
        try:
            # ── Phase 1: Orchestrator plans ──────────────────────────────────
            await self._emit(DemoEvent("agent_thought", {
                "agent": "orquanta_orchestrator",
                "icon": "🧠",
                "message": f"Goal parsed: '{job.goal[:60]}' | Building execution DAG...",
                "confidence": 0.91,
            }))
            await asyncio.sleep(1.2)

            await self._emit(DemoEvent("agent_thought", {
                "agent": "cost_optimizer",
                "icon": "💸",
                "message": f"Lambda Labs {job.gpu_type}: ${job.cost_per_hr:.2f}/hr | AWS equiv: ${job.cost_per_hr + savings_rate:.2f}/hr | Saving ${savings_rate:.2f}/hr",
                "confidence": 0.95,
                "provider_selected": "lambda",
            }))
            await asyncio.sleep(0.8)

            # ── Phase 2: Provisioning ─────────────────────────────────────────
            job.phase = JobPhase.PROVISIONING
            await self._emit(DemoEvent("job_progress", {
                "job_id": job.job_id, "phase": "provisioning",
                "message": f"Provisioning {job.gpu_type} in us-tx-3...",
                "progress_pct": 0,
            }))
            await self._emit(DemoEvent("agent_thought", {
                "agent": "scheduler",
                "icon": "⚡",
                "message": "Instance launching... ETA 18 seconds.",
            }))
            for i in range(3):
                await asyncio.sleep(1.5)
                await self._emit(DemoEvent("job_progress", {
                    "job_id": job.job_id, "phase": "provisioning",
                    "message": f"Waiting for GPU... ({(i+1)*5}s)",
                    "progress_pct": i * 3,
                }))

            # ── Phase 3: Running ──────────────────────────────────────────────
            job.phase = JobPhase.RUNNING
            await self._emit(DemoEvent("job_progress", {
                "job_id": job.job_id, "phase": "running",
                "message": "GPU ready! Job started.",
                "progress_pct": 5,
            }))
            await self._emit(DemoEvent("agent_thought", {
                "agent": "healing_agent",
                "icon": "🔧",
                "message": "Monitoring enabled. 1Hz telemetry active.",
            }))

            # Determine if we inject a failure mid-run
            failure_at_pct = random.uniform(35, 55) if inject_failure else 101

            total_steps = 40
            for step in range(total_steps):
                if not self._active:
                    break

                pct = round(5 + (step / total_steps) * 90, 1)
                job.progress_pct = pct

                # Realistic GPU metrics
                base_util = 78 + 12 * math.sin(step * 0.3) + random.uniform(-5, 5)
                base_mem  = 45 + 25 * (pct / 100) + random.uniform(-3, 3)
                base_temp = 68 + 8  * math.sin(step * 0.2) + random.uniform(-2, 2)
                loss_val  = max(0.45, 3.5 * math.exp(-step * 0.09)) + random.uniform(-0.02, 0.02)

                job.gpu_util    = min(98, max(40, base_util))
                job.memory_pct  = min(96, max(35, base_mem))
                job.temp_c      = min(82, max(62, base_temp))
                job.loss        = round(loss_val, 3)
                job.cost_so_far = round(job.cost_per_hr * (step / total_steps) * (job.duration_min / 60), 4)
                job.saved_vs_aws = round(savings_rate * (step / total_steps) * (job.duration_min / 60), 4)

                # Check OOM injection
                if pct >= failure_at_pct and not job.healed and inject_failure:
                    job.memory_pct = 97.3
                    await self._simulate_healing(job)
                    inject_failure = False  # only once

                await self._emit(DemoEvent("job_progress", {
                    "job_id": job.job_id,
                    "phase": "running",
                    "progress_pct": pct,
                    "gpu_util": round(job.gpu_util, 1),
                    "memory_pct": round(job.memory_pct, 1),
                    "temp_c": round(job.temp_c, 1),
                    "loss": job.loss,
                    "cost_so_far": job.cost_so_far,
                    "saved_vs_aws": job.saved_vs_aws,
                }))

                # Cost update every 5 steps
                if step % 5 == 0:
                    await self._emit(DemoEvent("cost_update", {
                        "job_id": job.job_id,
                        "cost_usd": job.cost_so_far,
                        "saved_usd": job.saved_vs_aws,
                        "rate_per_hr": job.cost_per_hr,
                    }))

                await asyncio.sleep(0.8)  # ~32s total run time at 0.8s/step

            # ── Phase 4: Complete ────────────────────────────────────────────
            job.phase = JobPhase.COMPLETE
            job.progress_pct = 100.0
            total_cost  = round(job.cost_per_hr * (job.duration_min / 60), 2)
            total_saved = round(savings_rate * (job.duration_min / 60), 2)
            job.cost_so_far  = total_cost
            job.saved_vs_aws = total_saved

            await self._emit(DemoEvent("agent_thought", {
                "agent": "audit_agent",
                "icon": "🔒",
                "message": f"Job {job.job_id} logged. HMAC-signed. {total_cost:.2f} USD spent, {total_saved:.2f} saved.",
            }))
            await asyncio.sleep(0.5)
            await self._emit(DemoEvent("job_complete", {
                "job_id":      job.job_id,
                "goal":        job.goal,
                "cost_usd":    total_cost,
                "saved_usd":   total_saved,
                "duration_min": job.duration_min,
                "final_loss":  job.loss,
                "provider":    job.provider,
                "healed":      job.healed,
                "heal_count":  job.heal_count,
                "artifacts":   [f"s3://orquanta-demo/{job.job_id}/checkpoint_final.pt"],
            }))
            logger.info(f"[Demo] Job {job.job_id} COMPLETE — ${total_cost} spent, ${total_saved} saved")

        except asyncio.CancelledError:
            logger.info(f"[Demo] Job {job.job_id} simulation cancelled")
        except Exception as exc:
            logger.error(f"[Demo] Job {job.job_id} simulation error: {exc}")
            job.phase = JobPhase.FAILED
            job.error_msg = str(exc)

    async def _simulate_healing(self, job: DemoJob) -> None:
        """Simulate OOM detection and recovery by healing agent."""
        job.phase = JobPhase.HEALING
        job.heal_count += 1

        await self._emit(DemoEvent("healing_event", {
            "job_id":  job.job_id,
            "trigger": "oom_risk",
            "message": f"ALERT: VRAM at {job.memory_pct:.1f}% — OOM imminent in ~8 seconds",
            "severity": "warning",
            "agent": "healing_agent",
            "icon": "🔧",
        }))
        await asyncio.sleep(1.0)

        await self._emit(DemoEvent("agent_thought", {
            "agent": "healing_agent",
            "icon": "🔧",
            "message": f"Diagnosing: memory pressure at {job.memory_pct:.1f}%. Prescaling memory config...",
            "confidence": 0.88,
        }))
        await asyncio.sleep(1.5)

        # Recovery
        job.memory_pct = 71.0
        job.healed = True
        job.phase = JobPhase.RUNNING

        await self._emit(DemoEvent("healing_event", {
            "job_id":  job.job_id,
            "trigger": "oom_risk",
            "action":  "prescale_memory",
            "message": "Memory prescaled. VRAM: 97.3% → 71.0%. Job continues. No data lost.",
            "severity": "resolved",
            "response_time_ms": 8300,
            "agent": "healing_agent",
            "icon": "✅",
        }))
        logger.info(f"[Demo] Job {job.job_id} HEALED — memory prescaled")

    # ─── Background heartbeat ────────────────────────────────────────────────

    async def _global_heartbeat(self) -> None:
        """Push periodic platform stats to subscribers."""
        jobs_done = 0
        total_saved = 0.0
        while self._active:
            await asyncio.sleep(10)
            completed = [j for j in self._jobs.values() if j.phase == JobPhase.COMPLETE]
            if len(completed) > jobs_done:
                jobs_done = len(completed)
                total_saved = sum(j.saved_vs_aws for j in completed)
                await self._emit(DemoEvent("platform_stats", {
                    "jobs_completed": jobs_done,
                    "total_saved_usd": round(total_saved, 2),
                    "active_instances": len([j for j in self._jobs.values()
                                             if j.phase == JobPhase.RUNNING]),
                }))

    # ─── Job status ───────────────────────────────────────────────────────────

    def get_job(self, job_id: str) -> DemoJob | None:
        return self._jobs.get(job_id)

    def get_all_jobs(self) -> list[DemoJob]:
        return list(self._jobs.values())

    def get_stats(self) -> dict[str, Any]:
        jobs = list(self._jobs.values())
        return {
            "demo_mode": True,
            "total_jobs": len(jobs),
            "running": sum(1 for j in jobs if j.phase == JobPhase.RUNNING),
            "complete": sum(1 for j in jobs if j.phase == JobPhase.COMPLETE),
            "failed": sum(1 for j in jobs if j.phase == JobPhase.FAILED),
            "total_saved_usd": round(sum(j.saved_vs_aws for j in jobs), 2),
            "total_cost_usd": round(sum(j.cost_so_far for j in jobs), 2),
        }


# ─── Singleton ────────────────────────────────────────────────────────────────

_demo_engine: DemoEngine | None = None

def get_demo_engine() -> DemoEngine:
    global _demo_engine
    if _demo_engine is None:
        _demo_engine = DemoEngine()
    return _demo_engine
