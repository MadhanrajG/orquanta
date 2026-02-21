"""
OrQuanta Agentic v1.0 — Cost Optimizer Agent

Real-time cost intelligence across GPU providers:
- Spot price monitoring across AWS/GCP/Azure/CoreWeave
- Budget enforcement and over-budget alerts
- Cost forecasting using simple exponential smoothing
- Provider switching recommendations
- Savings vs. on-demand comparison
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from .llm_reasoning_engine import LLMReasoningEngine
from .memory_manager import MemoryManager
from .safety_governor import get_governor
from .tool_registry import ToolRegistry

logger = logging.getLogger("orquanta.cost")

PRICE_HISTORY_WINDOW = int(os.getenv("COST_PRICE_HISTORY_WINDOW", "100"))
BUDGET_ALERT_THRESHOLD = float(os.getenv("COST_BUDGET_ALERT_PCT", "0.80"))


class CostOptimizerAgent:
    """Real-time cost monitoring and optimization across GPU cloud providers.

    Maintains a sliding window of spot price observations and uses LLM
    reasoning to produce actionable switching recommendations.

    Key capabilities:
    - get_cheapest_option: Compare all providers for a GPU type and pick best.
    - forecast_cost: Exponential smoothing for 24h cost prediction.
    - enforce_budget: Alert when a job budget is approaching limits.
    - find_cheapest_spot: Full end-to-end recommendation via LLM reasoning.

    Usage::

        cost_agent = CostOptimizerAgent()
        
        from_spot = await cost_agent.find_cheapest_spot(
            gpu_type="H100",
            required_hours=4,
            budget_usd=100.0,
        )
        print(from_spot["recommended_provider"])  # e.g., "coreweave"
        print(from_spot["estimated_total_cost"])  # e.g., 15.56
    """

    def __init__(self) -> None:
        self.llm = LLMReasoningEngine()
        self.memory = MemoryManager()
        self.tools = ToolRegistry()
        self.governor = get_governor()

        # Price history: provider:gpu:region → deque of (timestamp, price)
        self._price_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=PRICE_HISTORY_WINDOW)
        )
        # Budget tracking per job_id
        self._budgets: dict[str, dict[str, float]] = {}
        self._running = False
        logger.info("CostOptimizerAgent initialised.")

    async def start(self) -> None:
        """Start background price polling loop."""
        self._running = True
        asyncio.create_task(self._price_polling_loop())
        logger.info("CostOptimizerAgent price polling active.")

    async def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def find_cheapest_spot(
        self,
        gpu_type: str = "H100",
        required_hours: float = 1.0,
        budget_usd: float | None = None,
    ) -> dict[str, Any]:
        """Find the cheapest spot GPU option via LLM-driven analysis.

        Fetches live prices across all providers, then asks the LLM
        reasoning engine to weigh cost, availability, and stability.

        Args:
            gpu_type: GPU model (H100/A100/T4/A10G).
            required_hours: Expected duration for cost estimation.
            budget_usd: Optional maximum budget constraint.

        Returns:
            dict with recommended_provider, recommended_gpu, estimated_hourly_cost,
            estimated_total_cost, savings_vs_on_demand, reasoning, alternatives.
        """
        logger.info(f"[CostOptimizer] Finding cheapest {gpu_type} for {required_hours}h")

        # Gather live prices from all providers
        prices = await self.tools.get_all_spot_prices(gpu_type)

        # Ask LLM to weigh options
        llm_result = await self.llm.reason(
            template_name="cost_optimize",
            variables={
                "requirements": {
                    "gpu_type": gpu_type,
                    "required_hours": required_hours,
                    "budget_usd": budget_usd or "unlimited",
                },
                "prices": prices,
            },
            agent_name="cost_optimizer_agent",
        )

        # Calculate estimated total cost
        hourly = llm_result.get("estimated_hourly_cost", prices[0]["current_price_usd_hr"])
        total = round(hourly * required_hours, 4)

        # Find on-demand baseline for savings calculation
        on_demand_baseline = hourly * 1.35  # Spot is typically ~26% cheaper
        savings = round((on_demand_baseline - hourly) / on_demand_baseline * 100, 1)

        result = {
            **llm_result,
            "estimated_total_cost_usd": total,
            "savings_vs_on_demand_pct": savings,
            "price_options_evaluated": len(prices),
            "budget_within_limit": (total <= budget_usd) if budget_usd else True,
        }

        # Warn if over budget
        if budget_usd and total > budget_usd:
            await self.tools.send_alert(
                message=(
                    f"⚠️ Cheapest option (${total:.2f}) exceeds budget of ${budget_usd:.2f} "
                    f"for {gpu_type} over {required_hours}h."
                ),
                severity="warning",
                agent_name="cost_optimizer_agent",
            )

        # Store in memory
        await self.memory.store_event({
            "type": "cost_recommendation",
            "gpu_type": gpu_type,
            "required_hours": required_hours,
            "recommended_provider": llm_result.get("recommended_provider"),
            "estimated_hourly_cost": hourly,
            "total_cost": total,
            "budget_usd": budget_usd,
        }, agent_name="cost_optimizer_agent")

        return result

    async def get_cheapest_option(self, gpu_type: str) -> dict[str, Any]:
        """Simple cheapest option lookup (no LLM) for internal agent use.
        
        Returns:
            dict with provider, region, price.
        """
        prices = await self.tools.get_all_spot_prices(gpu_type)
        if not prices:
            return {"error": "no_prices_available", "gpu_type": gpu_type}
        return prices[0]  # Already sorted cheapest first

    async def forecast_cost(
        self, job_id: str, gpu_type: str, hourly_rate: float, duration_hours: float
    ) -> dict[str, Any]:
        """Forecast total job cost with exponential smoothing on price history.

        Uses the price history to smooth out spot price volatility and
        produce a confidence-bounded cost forecast.

        Args:
            job_id: Job identifier (for budget tracking).
            gpu_type: GPU type being used.
            hourly_rate: Current spot rate.
            duration_hours: Expected duration.

        Returns:
            dict with base_estimate, smoothed_estimate, confidence_bounds.
        """
        key = f"avg:{gpu_type}"
        history = self._price_history.get(key, deque([hourly_rate]))

        # Exponential smoothing: alpha=0.3
        alpha = 0.3
        smoothed = hourly_rate
        for h_price in list(history):
            smoothed = alpha * h_price + (1 - alpha) * smoothed

        base_total = round(hourly_rate * duration_hours, 4)
        smoothed_total = round(smoothed * duration_hours, 4)
        low = round(smoothed_total * 0.80, 4)
        high = round(smoothed_total * 1.25, 4)

        return {
            "job_id": job_id,
            "gpu_type": gpu_type,
            "base_estimate_usd": base_total,
            "smoothed_estimate_usd": smoothed_total,
            "confidence_bounds": {"low_usd": low, "high_usd": high},
            "hourly_rate_used": round(smoothed, 4),
            "duration_hours": duration_hours,
        }

    def set_budget(self, job_id: str, budget_usd: float) -> None:
        """Register a budget limit for a job."""
        self._budgets[job_id] = {"limit": budget_usd, "spent": 0.0}
        logger.info(f"[CostOptimizer] Budget set for {job_id}: ${budget_usd:.2f}")

    async def track_spend(self, job_id: str, amount_usd: float) -> dict[str, Any]:
        """Record spend for a job and alert if approaching budget limit.
        
        Returns:
            dict with total_spent, remaining, pct_used, alert_triggered.
        """
        if job_id not in self._budgets:
            return {"error": "no_budget_set", "job_id": job_id}

        budget = self._budgets[job_id]
        budget["spent"] += amount_usd
        spent = budget["spent"]
        limit = budget["limit"]
        pct = spent / limit if limit > 0 else 0.0
        alert_triggered = False

        if pct >= BUDGET_ALERT_THRESHOLD:
            alert_triggered = True
            severity = "critical" if pct >= 1.0 else "warning"
            await self.tools.send_alert(
                message=(
                    f"Job {job_id} has used ${spent:.2f} of ${limit:.2f} budget "
                    f"({pct*100:.1f}%)."
                ),
                severity=severity,
                agent_name="cost_optimizer_agent",
                job_id=job_id,
            )

        return {
            "job_id": job_id,
            "total_spent_usd": round(spent, 4),
            "budget_limit_usd": limit,
            "remaining_usd": round(max(0, limit - spent), 4),
            "pct_used": round(pct * 100, 2),
            "alert_triggered": alert_triggered,
        }

    def get_provider_comparison(self, gpu_type: str) -> list[dict[str, Any]]:
        """Return aggregated price statistics for each provider from history."""
        stats = []
        providers = ["aws", "gcp", "azure", "coreweave"]
        for provider in providers:
            key = f"{provider}:{gpu_type}"
            history = list(self._price_history.get(key, []))
            if not history:
                continue
            prices = [p for _, p in history]
            stats.append({
                "provider": provider,
                "gpu_type": gpu_type,
                "avg_price_usd_hr": round(sum(prices) / len(prices), 4),
                "min_price_usd_hr": round(min(prices), 4),
                "max_price_usd_hr": round(max(prices), 4),
                "samples": len(prices),
            })
        return sorted(stats, key=lambda x: x["avg_price_usd_hr"])

    def get_spend_dashboard(self) -> dict[str, Any]:
        """Return spend overview across all tracked jobs."""
        total_spent = sum(b["spent"] for b in self._budgets.values())
        total_budget = sum(b["limit"] for b in self._budgets.values())
        return {
            "total_tracked_jobs": len(self._budgets),
            "total_spent_usd": round(total_spent, 4),
            "total_budget_usd": round(total_budget, 4),
            "overall_pct_used": round(total_spent / total_budget * 100, 2) if total_budget else 0,
            "governor_spend": self.governor.get_spend_summary(),
        }

    # ------------------------------------------------------------------
    # Background price polling
    # ------------------------------------------------------------------

    async def _price_polling_loop(self) -> None:
        """Poll spot prices for common GPU types every 5 minutes."""
        GPU_TYPES = ["H100", "A100", "T4"]
        PROVIDERS = ["aws", "gcp", "azure", "coreweave"]
        REGIONS = {"aws": "us-east-1", "gcp": "us-central1", "azure": "eastus", "coreweave": "us-east1"}

        while self._running:
            for gpu in GPU_TYPES:
                for provider in PROVIDERS:
                    region = REGIONS.get(provider, "us-east-1")
                    try:
                        price_data = await self.tools.get_spot_prices(provider, region, gpu)
                        current = price_data["current_price_usd_hr"]
                        ts = datetime.now(timezone.utc).isoformat()

                        # Store in history buckets
                        self._price_history[f"{provider}:{gpu}"].append((ts, current))
                        self._price_history[f"avg:{gpu}"].append((ts, current))

                    except Exception as exc:
                        logger.debug(f"[CostOptimizer] Price poll error {provider}/{gpu}: {exc}")

            await asyncio.sleep(300)  # Poll every 5 minutes
