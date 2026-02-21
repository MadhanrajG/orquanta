"""
OrQuanta Agentic v1.0 — Recommendation Agent

Proactively analyzes customer's job history (last 30 days) and
surfaces actionable optimization recommendations:

  - Wasteful jobs (low GPU utilization)
  - Better GPU choices (oversized / undersized)
  - Cheaper time windows (run at night vs day)
  - Provider switches (cheaper equivalent GPU)
  - Redundant jobs (re-running identical jobs)

Reports monthly savings estimate for each recommendation.
Tracks if users act on recommendations (for agent improvement).

Integrates with weekly_report.py to send Monday digests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger("orquanta.agents.recommendation")


@dataclass
class Recommendation:
    id: str
    type: str            # "switch_provider" | "right_size_gpu" | "schedule_off_peak" | "batch_jobs" | "reduce_waste"
    title: str
    description: str
    estimated_monthly_savings_usd: float
    confidence: float    # 0.0 – 1.0
    evidence: list[str]  # Supporting data points
    action_url: str
    acted_on: bool = False
    dismissed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecommendationAgent:
    """Analyzes job history and surfaces optimization recommendations."""

    AGENT_NAME = "recommendation_agent"

    def __init__(self) -> None:
        self._recommendation_history: dict[str, list[Recommendation]] = {}

    async def analyze(self, org_id: str, job_history: list[dict[str, Any]]) -> list[Recommendation]:
        """
        Analyze 30 days of job history and return ranked recommendations.

        job_history items should have:
          - job_id, gpu_type, provider, duration_min, cost_usd
          - avg_gpu_utilization_pct, avg_memory_usage_pct
          - spot (bool), region, started_at (ISO string)
        """
        if not job_history:
            return []

        recommendations: list[Recommendation] = []

        # 1. Low GPU utilization → right-size or reduce parallelism
        recommendations.extend(self._check_gpu_waste(job_history))

        # 2. Oversized GPU → switch to smaller/cheaper
        recommendations.extend(self._check_gpu_oversize(job_history))

        # 3. Off-peak scheduling opportunity
        recommendations.extend(self._check_scheduling_window(job_history))

        # 4. Provider switch opportunity
        recommendations.extend(self._check_provider_switch(job_history))

        # 5. Batching opportunity (many short jobs of same type)
        recommendations.extend(self._check_batch_opportunity(job_history))

        # Sort by estimated savings descending
        recommendations.sort(key=lambda r: r.estimated_monthly_savings_usd, reverse=True)

        self._recommendation_history[org_id] = recommendations
        logger.info(f"[RecommendationAgent] {org_id}: {len(recommendations)} recommendations, "
                    f"total potential savings: ${sum(r.estimated_monthly_savings_usd for r in recommendations):.0f}/mo")
        return recommendations

    def get_digest(self, org_id: str, top_n: int = 3) -> list[dict[str, Any]]:
        """Get top N recommendations for weekly digest."""
        recs = self._recommendation_history.get(org_id, [])
        return [r.to_dict() for r in recs[:top_n] if not r.dismissed]

    def mark_acted_on(self, org_id: str, recommendation_id: str) -> bool:
        """Record that a user acted on a recommendation."""
        for rec in self._recommendation_history.get(org_id, []):
            if rec.id == recommendation_id:
                rec.acted_on = True
                logger.info(f"[RecommendationAgent] Recommendation {recommendation_id} acted on by {org_id}")
                return True
        return False

    def mark_dismissed(self, org_id: str, recommendation_id: str) -> bool:
        for rec in self._recommendation_history.get(org_id, []):
            if rec.id == recommendation_id:
                rec.dismissed = True
                return True
        return False

    # ─── Analysis modules ─────────────────────────────────────────────

    def _check_gpu_waste(self, jobs: list[dict]) -> list[Recommendation]:
        """Detect jobs with <30% average GPU utilization."""
        wasteful = [j for j in jobs if j.get("avg_gpu_utilization_pct", 100) < 30.0]
        if len(wasteful) < 3:
            return []

        wasteful_spend = sum(j.get("cost_usd", 0) for j in wasteful)
        avg_util = sum(j.get("avg_gpu_utilization_pct", 0) for j in wasteful) / len(wasteful)
        monthly_est = (wasteful_spend / 30) * 30 * 0.5  # 50% savings estimate

        return [Recommendation(
            id=f"waste-{len(wasteful)}",
            type="reduce_waste",
            title=f"🔴 {len(wasteful)} jobs averaging only {avg_util:.0f}% GPU utilization",
            description=f"These jobs are using GPU memory but keeping the chip mostly idle. "
                        f"Consider increasing batch sizes, enabling CUDA data prefetching, or "
                        f"switching to a CPU-only instance for preprocessing steps.",
            estimated_monthly_savings_usd=monthly_est,
            confidence=0.85,
            evidence=[
                f"{len(wasteful)} jobs below 30% GPU utilization in past 30 days",
                f"Average utilization: {avg_util:.1f}%",
                f"Wasted spend on idle GPUs: ${wasteful_spend:.2f}",
            ],
            action_url="/jobs?filter=low_utilization",
        )]

    def _check_gpu_oversize(self, jobs: list[dict]) -> list[Recommendation]:
        """Detect A100/H100 jobs that only use <40% VRAM (could use T4 or V100)."""
        expensive_gpus = {"A100", "H100", "A10G"}
        oversized = [
            j for j in jobs
            if j.get("gpu_type", "") in expensive_gpus
            and j.get("avg_memory_usage_pct", 100) < 40.0
        ]
        if len(oversized) < 2:
            return []

        savings_per_job = 2.0   # Est. $/hr savings by switching to T4/V100
        avg_duration_hr = sum(j.get("duration_min", 60) for j in oversized) / len(oversized) / 60
        monthly_savings = len(oversized) * savings_per_job * avg_duration_hr * 4.3  # ~4.3 weeks/month

        return [Recommendation(
            id=f"oversize-{len(oversized)}",
            type="right_size_gpu",
            title=f"💡 {len(oversized)} jobs are on A100/H100 but only use <40% VRAM",
            description=f"These jobs could run on V100 or T4 instances at 60-70% lower cost. "
                        f"Your models are small enough that the extra VRAM on A100/H100 is not utilized.",
            estimated_monthly_savings_usd=monthly_savings,
            confidence=0.75,
            evidence=[
                f"{len(oversized)} recent jobs on A100/H100 with <40% memory usage",
                f"Estimated savings by switching to T4: ~$2-3/hr per job",
                f"Average job duration: {avg_duration_hr:.1f}h",
            ],
            action_url="/settings/preferences?suggest=gpu_type",
        )]

    def _check_scheduling_window(self, jobs: list[dict]) -> list[Recommendation]:
        """Detect if most jobs run during peak spot price hours."""
        peak_hours = set(range(9, 18))    # 9am-6pm UTC (AWS peak)
        peak_jobs = []
        for j in jobs:
            try:
                hour = datetime.fromisoformat(j.get("started_at", "")).hour
                if hour in peak_hours:
                    peak_jobs.append(j)
            except Exception:
                continue

        if len(peak_jobs) < len(jobs) * 0.6:  # Less than 60% during peak
            return []

        total_spend = sum(j.get("cost_usd", 0) for j in peak_jobs)
        monthly_savings = (total_spend / 30) * 30 * 0.20  # Spot prices ~20% lower off-peak

        return [Recommendation(
            id="offpeak-scheduling",
            type="schedule_off_peak",
            title="🌙 Schedule jobs at night for lower spot prices",
            description=f"{len(peak_jobs)} of your jobs run during peak hours (9am-6pm UTC) when spot prices "
                        f"are highest. Scheduling training runs overnight or on weekends can reduce spot prices "
                        f"by 15-25%. OrQuanta can schedule these automatically.",
            estimated_monthly_savings_usd=monthly_savings,
            confidence=0.70,
            evidence=[
                f"{len(peak_jobs)} jobs running during peak hours",
                f"Peak-hour spend: ${total_spend:.2f}",
                f"Typical off-peak spot discount: 15-25%",
            ],
            action_url="/settings/scheduling?suggest=off_peak",
        )]

    def _check_provider_switch(self, jobs: list[dict]) -> list[Recommendation]:
        """Check if a different provider offers the same GPU cheaper."""
        from v4.providers.provider_router import ProviderRouter

        provider_costs = {}
        for j in jobs:
            p = j.get("provider", "")
            gpu = j.get("gpu_type", "")
            if p and gpu:
                key = (p, gpu)
                if key not in provider_costs:
                    provider_costs[key] = []
                provider_costs[key].append(j.get("cost_usd", 0))

        if not provider_costs:
            return []

        # Find jobs on AWS A100 (most common expensive combo)
        aws_a100 = provider_costs.get(("aws", "A100"), [])
        if len(aws_a100) < 3:
            return []

        # CoreWeave is typically 30-40% cheaper for A100
        total_aws_spend = sum(aws_a100)
        potential_savings = total_aws_spend * 0.35
        monthly_savings = (potential_savings / 30) * 30

        return [Recommendation(
            id="provider-switch-coreweave",
            type="switch_provider",
            title="⚡ Switch A100 jobs from AWS to CoreWeave — save ~35%",
            description=f"CoreWeave's A100 instances are typically 30-40% cheaper than AWS p4d instances "
                        f"for the same GPU. OrQuanta can transparently route future A100 jobs to CoreWeave while "
                        f"maintaining AWS as a failover.",
            estimated_monthly_savings_usd=monthly_savings,
            confidence=0.80,
            evidence=[
                f"{len(aws_a100)} A100 jobs on AWS in past 30 days",
                f"AWS A100 spend: ${total_aws_spend:.2f}",
                f"CoreWeave A100 pricing: ~35% below AWS p4d equivalent",
            ],
            action_url="/settings/providers?suggest=coreweave_a100",
        )]

    def _check_batch_opportunity(self, jobs: list[dict]) -> list[Recommendation]:
        """Detect many similar short jobs that could be batched."""
        short_jobs = [j for j in jobs if j.get("duration_min", 60) < 10]
        if len(short_jobs) < 10:
            return []

        total_wasted_startup = len(short_jobs) * 0.05 * 3.89   # 3 min avg startup at H100 price
        monthly_savings = (total_wasted_startup / 30) * 30 * 2

        return [Recommendation(
            id="batch-short-jobs",
            type="batch_jobs",
            title=f"📦 Batch {len(short_jobs)} short jobs to eliminate startup overhead",
            description=f"You have {len(short_jobs)} jobs under 10 minutes. Each job incurs ~3 minutes of "
                        f"instance startup and warmup time. Batching them into fewer, longer runs eliminates "
                        f"this overhead and can save significantly on instance-hour minimums.",
            estimated_monthly_savings_usd=monthly_savings,
            confidence=0.65,
            evidence=[
                f"{len(short_jobs)} jobs under 10 minutes in past 30 days",
                f"Estimated startup overhead: ~3 min per job",
                f"Potential batch efficiency: 20-40% cost reduction",
            ],
            action_url="/jobs/submit?template=batch_runner",
        )]
