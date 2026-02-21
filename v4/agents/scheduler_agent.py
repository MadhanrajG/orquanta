"""
OrQuanta Agentic v1.0 — Scheduler Agent

Intelligent GPU job queue manager with:
- Priority scoring using LLM + heuristics
- Bin-packing algorithm for efficient GPU allocation
- Preemption and requeuing for high-priority jobs
- Provider API communication via ToolRegistry
"""

from __future__ import annotations

import asyncio
import heapq
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .llm_reasoning_engine import LLMReasoningEngine
from .memory_manager import MemoryManager
from .safety_governor import get_governor
from .tool_registry import ToolRegistry

logger = logging.getLogger("orquanta.scheduler")

# ---------------------------------------------------------------------------
# Job Priority Queue item
# ---------------------------------------------------------------------------

class ScheduledJob:
    """A GPU job in the scheduling queue."""

    def __init__(
        self,
        job_id: str,
        intent: str,
        required_vram_gb: int,
        gpu_type: str,
        provider: str,
        gpu_count: int = 1,
        user_id: str = "",
        priority: float = 0.5,
        max_cost_usd: float = 500.0,
        max_runtime_minutes: int = 120,
    ) -> None:
        self.job_id = job_id
        self.intent = intent
        self.required_vram_gb = required_vram_gb
        self.gpu_type = gpu_type
        self.provider = provider
        self.gpu_count = gpu_count
        self.user_id = user_id
        self.priority = priority
        self.max_cost_usd = max_cost_usd
        self.max_runtime_minutes = max_runtime_minutes
        self.status = "queued"
        self.instance_id: str | None = None
        self.enqueued_at = datetime.now(timezone.utc).isoformat()
        self.started_at: str | None = None
        self.preempted_count = 0

    # Priority queue uses min-heap, so negate priority for max-heap behavior
    def __lt__(self, other: "ScheduledJob") -> bool:
        return self.priority > other.priority  # Higher priority runs first

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "intent": self.intent,
            "required_vram_gb": self.required_vram_gb,
            "gpu_type": self.gpu_type,
            "provider": self.provider,
            "gpu_count": self.gpu_count,
            "user_id": self.user_id,
            "priority": self.priority,
            "max_cost_usd": self.max_cost_usd,
            "status": self.status,
            "instance_id": self.instance_id,
            "enqueued_at": self.enqueued_at,
            "started_at": self.started_at,
            "preempted_count": self.preempted_count,
        }


# ---------------------------------------------------------------------------
# GPU Bin (allocation tracking)
# ---------------------------------------------------------------------------

class GPUBin:
    """Tracks allocated GPUs on a single instance for bin-packing."""

    def __init__(self, instance_id: str, total_vram_gb: int, gpu_count: int) -> None:
        self.instance_id = instance_id
        self.total_vram_gb = total_vram_gb
        self.gpu_count = gpu_count
        self.used_vram_gb = 0
        self.jobs: list[str] = []

    @property
    def available_vram_gb(self) -> int:
        return self.total_vram_gb - self.used_vram_gb

    @property
    def utilization_pct(self) -> float:
        return (self.used_vram_gb / self.total_vram_gb * 100) if self.total_vram_gb else 0.0

    def can_fit(self, vram_needed: int) -> bool:
        return self.available_vram_gb >= vram_needed

    def allocate(self, job_id: str, vram_gb: int) -> None:
        self.jobs.append(job_id)
        self.used_vram_gb += vram_gb

    def release(self, job_id: str, vram_gb: int) -> None:
        if job_id in self.jobs:
            self.jobs.remove(job_id)
            self.used_vram_gb = max(0, self.used_vram_gb - vram_gb)


# ---------------------------------------------------------------------------
# Scheduler Agent
# ---------------------------------------------------------------------------

class SchedulerAgent:
    """Intelligent GPU job scheduler with priority scoring and bin-packing.

    Manages the full job lifecycle:
    1. Accepts jobs and scores priority via LLM.
    2. Bins them into existing instances using best-fit-decreasing algorithm.
    3. Provisions new instances when no bin can fit the job.
    4. Preempts low-priority jobs when a high-priority job arrives.
    5. Requeues preempted jobs automatically.

    Usage::

        scheduler = SchedulerAgent()
        await scheduler.start()

        result = await scheduler.schedule_job(
            intent="Fine-tune GPT-2 on custom dataset",
            required_vram_gb=16,
            gpu_type="T4",
            provider="aws",
        )
    """

    def __init__(self) -> None:
        self.llm = LLMReasoningEngine()
        self.memory = MemoryManager()
        self.tools = ToolRegistry()
        self.governor = get_governor()

        self._queue: list[ScheduledJob] = []  # min-heap (inverted priority)
        self._bins: dict[str, GPUBin] = {}    # instance_id → GPUBin
        self._all_jobs: dict[str, ScheduledJob] = {}
        self._running = False
        logger.info("SchedulerAgent initialised.")

    async def start(self) -> None:
        """Start background scheduling loop."""
        self._running = True
        asyncio.create_task(self._scheduling_loop())
        logger.info("SchedulerAgent running.")

    async def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def schedule_job(
        self,
        intent: str,
        required_vram_gb: int,
        gpu_type: str = "H100",
        provider: str = "aws",
        gpu_count: int = 1,
        user_id: str = "system",
        max_cost_usd: float = 500.0,
        max_runtime_minutes: int = 120,
    ) -> dict[str, Any]:
        """Schedule a GPU job for execution.

        Scores priority via LLM, then places the job in the queue.
        The background scheduling loop will pick it up and provision
        an instance if needed.

        Returns:
            dict with job_id, priority_score, estimated_start_seconds.
        """
        job_id = f"job-{str(uuid4())[:8]}"

        # Score priority using LLM
        priority = await self._score_priority(
            intent=intent,
            required_vram_gb=required_vram_gb,
            gpu_type=gpu_type,
        )

        job = ScheduledJob(
            job_id=job_id,
            intent=intent,
            required_vram_gb=required_vram_gb,
            gpu_type=gpu_type,
            provider=provider,
            gpu_count=gpu_count,
            user_id=user_id,
            priority=priority,
            max_cost_usd=max_cost_usd,
            max_runtime_minutes=max_runtime_minutes,
        )

        self._all_jobs[job_id] = job
        heapq.heappush(self._queue, job)

        logger.info(
            f"[Scheduler] Job {job_id} queued (priority={priority:.2f}, "
            f"vram={required_vram_gb}GB, gpu={gpu_type}@{provider})"
        )

        # Try to place immediately via bin-packing
        placed = self._try_bin_pack(job)
        if placed:
            estimated_start = 5
        else:
            estimated_start = 30  # Will provision new instance

        await self.memory.store_event({
            "type": "job_queued",
            "job_id": job_id,
            "intent": intent,
            "priority": priority,
            "gpu_type": gpu_type,
        }, agent_name="scheduler_agent")

        return {
            "job_id": job_id,
            "status": "queued",
            "priority_score": priority,
            "queue_position": len(self._queue),
            "estimated_start_seconds": estimated_start,
            "bin_packed": placed,
        }

    def get_queue_status(self) -> dict[str, Any]:
        """Return the current state of the job queue and GPU bins."""
        return {
            "queued_jobs": len(self._queue),
            "total_jobs": len(self._all_jobs),
            "active_bins": len(self._bins),
            "bins": [
                {
                    "instance_id": bid,
                    "utilization_pct": round(b.utilization_pct, 1),
                    "available_vram_gb": b.available_vram_gb,
                    "active_job_count": len(b.jobs),
                }
                for bid, b in self._bins.items()
            ],
            "jobs_by_status": self._count_by_status(),
        }

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Return job details by ID."""
        job = self._all_jobs.get(job_id)
        return job.to_dict() if job else None

    def list_jobs(
        self, user_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        """List all jobs, optionally filtered."""
        jobs = list(self._all_jobs.values())
        if user_id:
            jobs = [j for j in jobs if j.user_id == user_id]
        if status:
            jobs = [j for j in jobs if j.status == status]
        return [j.to_dict() for j in sorted(jobs, key=lambda x: x.enqueued_at, reverse=True)]

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        """Cancel a queued or running job."""
        job = self._all_jobs.get(job_id)
        if not job:
            return {"error": "job_not_found", "job_id": job_id}

        if job.status == "running" and job.instance_id:
            # Release the bin allocation
            bin_ = self._bins.get(job.instance_id)
            if bin_:
                bin_.release(job_id, job.required_vram_gb)

        job.status = "cancelled"
        logger.info(f"[Scheduler] Job {job_id} cancelled.")
        return {"job_id": job_id, "status": "cancelled"}

    # ------------------------------------------------------------------
    # Priority Scoring
    # ------------------------------------------------------------------

    async def _score_priority(
        self, intent: str, required_vram_gb: int, gpu_type: str
    ) -> float:
        """Use LLM to score job priority on a 0.0-1.0 scale."""
        result = await self.llm.reason(
            template_name="scheduler_score",
            variables={
                "job_json": {
                    "intent": intent,
                    "required_vram_gb": required_vram_gb,
                    "gpu_type": gpu_type,
                }
            },
            agent_name="scheduler_agent",
        )
        score = float(result.get("priority_score", 0.5))
        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Bin-Packing (Best-Fit Decreasing)
    # ------------------------------------------------------------------

    def _try_bin_pack(self, job: ScheduledJob) -> bool:
        """Try to fit the job into an existing GPU bin (Best-Fit).

        Best-Fit Decreasing: choose the bin with the least remaining
        capacity that still fits the job (minimises fragmentation).
        
        Returns:
            True if job was placed in an existing bin.
        """
        eligible_bins = [
            b for b in self._bins.values()
            if b.can_fit(job.required_vram_gb)
        ]
        if not eligible_bins:
            return False

        # Best-fit: bin with smallest available_vram that still fits
        best_bin = min(eligible_bins, key=lambda b: b.available_vram_gb)
        best_bin.allocate(job.job_id, job.required_vram_gb)
        job.instance_id = best_bin.instance_id
        job.status = "running"
        job.started_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            f"[Scheduler/BinPack] Job {job.job_id} placed in {best_bin.instance_id} "
            f"(utilization: {best_bin.utilization_pct:.1f}%)"
        )
        return True

    async def _provision_and_place(self, job: ScheduledJob) -> None:
        """Provision a new GPU instance and start the job."""
        logger.info(
            f"[Scheduler] Provisioning new {job.gpu_count}x{job.gpu_type} on {job.provider} "
            f"for job {job.job_id}."
        )

        async def _do_provision():
            return await self.tools.spin_up_gpu_instance(
                provider=job.provider,
                gpu_type=job.gpu_type,
                count=job.gpu_count,
            )

        try:
            result = await self.governor.authorize_and_run(
                agent_name="scheduler_agent",
                action="provision_instance",
                reasoning=f"Job {job.job_id} requires {job.gpu_count}x{job.gpu_type}: '{job.intent[:60]}'",
                payload={"provider": job.provider, "gpu_type": job.gpu_type, "count": job.gpu_count},
                cost_estimate_usd=_estimate_provision_cost(job),
                fn=_do_provision,
            )

            instance = result["result"]
            instance_id = instance["instance_id"]
            total_vram = instance["vram_gb"]

            # Register new bin
            self._bins[instance_id] = GPUBin(
                instance_id=instance_id,
                total_vram_gb=total_vram,
                gpu_count=job.gpu_count,
            )
            self._bins[instance_id].allocate(job.job_id, job.required_vram_gb)

            job.instance_id = instance_id
            job.status = "running"
            job.started_at = datetime.now(timezone.utc).isoformat()

            logger.info(f"[Scheduler] Job {job.job_id} running on {instance_id}.")
        except Exception as exc:
            job.status = "failed"
            logger.error(f"[Scheduler] Failed to provision for job {job.job_id}: {exc}")

    async def _check_preemption(self, new_job: ScheduledJob) -> bool:
        """Check if a low-priority running job should be preempted.

        Returns:
            True if preemption was performed and the new job can now start.
        """
        running_jobs = [
            j for j in self._all_jobs.values()
            if j.status == "running" and j.priority < new_job.priority - 0.3
        ]
        if not running_jobs:
            return False

        # Preempt the lowest-priority running job on an instance with enough VRAM
        for victim in sorted(running_jobs, key=lambda x: x.priority):
            if victim.instance_id:
                bin_ = self._bins.get(victim.instance_id)
                if bin_:
                    bin_.release(victim.job_id, victim.required_vram_gb)
                    victim.status = "queued"
                    victim.preempted_count += 1
                    victim.instance_id = None
                    heapq.heappush(self._queue, victim)

                    logger.warning(
                        f"[Scheduler] Job {victim.job_id} preempted (priority={victim.priority:.2f}) "
                        f"for {new_job.job_id} (priority={new_job.priority:.2f})"
                    )

                    # Try to place the new job in the freed space
                    if bin_.can_fit(new_job.required_vram_gb):
                        bin_.allocate(new_job.job_id, new_job.required_vram_gb)
                        new_job.instance_id = bin_.instance_id
                        new_job.status = "running"
                        new_job.started_at = datetime.now(timezone.utc).isoformat()
                        return True

        return False

    # ------------------------------------------------------------------
    # Background Scheduling Loop
    # ------------------------------------------------------------------

    async def _scheduling_loop(self) -> None:
        """Main scheduling loop: process queue and provision instances."""
        while self._running:
            await asyncio.sleep(2)
            while self._queue:
                job = heapq.heappop(self._queue)

                if job.status != "queued":
                    continue

                # Try bin-packing first (cheapest)
                if self._try_bin_pack(job):
                    continue

                # Try preemption
                if await self._check_preemption(job):
                    continue

                # Provision new instance (most expensive)
                await self._provision_and_place(job)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for job in self._all_jobs.values():
            counts[job.status] = counts.get(job.status, 0) + 1
        return counts


def _estimate_provision_cost(job: ScheduledJob) -> float:
    """Rough hourly cost estimate for safety governor check."""
    cost_map = {
        ("aws", "H100"): 5.20, ("aws", "A100"): 3.10, ("aws", "T4"): 0.40,
        ("gcp", "H100"): 4.90, ("gcp", "A100"): 2.95, ("gcp", "T4"): 0.38,
        ("azure", "H100"): 5.10, ("azure", "A100"): 3.05, ("azure", "T4"): 0.39,
        ("coreweave", "H100"): 3.89, ("coreweave", "A100"): 2.40, ("coreweave", "T4"): 0.35,
    }
    base = cost_map.get((job.provider, job.gpu_type), 5.0)
    return base * job.gpu_count * (job.max_runtime_minutes / 60)
