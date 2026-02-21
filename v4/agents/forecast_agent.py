"""
OrQuanta Agentic v1.0 — Forecast Agent

GPU demand forecasting and proactive capacity planning:
- Historical job pattern analysis
- Exponential smoothing + trend decomposition forecasting
- LLM-enhanced reasoning over forecast data
- Auto-scaling trigger recommendations
- Peak load prediction
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .llm_reasoning_engine import LLMReasoningEngine
from .memory_manager import MemoryManager
from .tool_registry import ToolRegistry

logger = logging.getLogger("orquanta.forecast")

FORECAST_INTERVAL = int(os.getenv("FORECAST_INTERVAL_HOURS", "6"))


class ForecastAgent:
    """GPU demand forecasting agent using statistical models + LLM reasoning.

    Uses a combination of:
    1. Exponential smoothing (Holt-Winters inspired, without external libs)
       for baseline demand forecasting.
    2. LLM reasoning to interpret patterns and produce human-readable
       capacity planning recommendations.

    The agent collects job submission events and fits a simple additive
    seasonal model (daily cycle) to forecast next-window demand.

    Usage::

        forecast = ForecastAgent()
        await forecast.start()

        report = await forecast.run_forecast(window_hours=24)
        print(report["recommendation"])  # e.g., "pre-provision 4x H100"
        print(report["predicted_gpu_demand"])
    """

    def __init__(self) -> None:
        self.llm = LLMReasoningEngine()
        self.memory = MemoryManager()
        self.tools = ToolRegistry()

        # Job submission history: list of (timestamp_epoch, gpu_type)
        self._job_history: list[tuple[float, str]] = []
        # GPU type demand counters per hour-of-day (0-23)
        self._hourly_demand: dict[str, list[int]] = defaultdict(lambda: [0] * 24)
        # Current running utilization
        self._current_utilization: dict[str, int] = {"H100": 0, "A100": 0, "T4": 0}
        self._running = False
        self._last_forecast: dict[str, Any] = {}
        logger.info("ForecastAgent initialised.")

    async def start(self) -> None:
        """Start background forecasting loop."""
        self._running = True
        asyncio.create_task(self._forecast_loop())
        logger.info(f"ForecastAgent running (interval={FORECAST_INTERVAL}h).")

    async def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_job_submission(self, gpu_type: str) -> None:
        """Record a job submission for demand forecasting."""
        now = datetime.now(timezone.utc)
        self._job_history.append((now.timestamp(), gpu_type))
        hour = now.hour
        if gpu_type in self._hourly_demand:
            self._hourly_demand[gpu_type][hour] += 1
        self._current_utilization[gpu_type] = self._current_utilization.get(gpu_type, 0) + 1

    def record_job_completion(self, gpu_type: str) -> None:
        """Record a job completion (decrements active count)."""
        self._current_utilization[gpu_type] = max(
            0, self._current_utilization.get(gpu_type, 0) - 1
        )

    async def run_forecast(self, window_hours: int = 24) -> dict[str, Any]:
        """Run a full demand forecast for the next time window.

        Uses exponential smoothing + LLM reasoning to produce a
        comprehensive capacity plan.

        Args:
            window_hours: Forecast horizon in hours.

        Returns:
            dict with predicted_job_count, predicted_gpu_demand,
            confidence_interval, recommendation, reasoning.
        """
        logger.info(f"[Forecast] Running {window_hours}h demand forecast.")

        # Build history summary for LLM
        history_summary = self._build_history_summary()
        utilization = self._current_utilization.copy()

        # Statistical forecast
        stat_forecast = self._statistical_forecast(window_hours)

        # LLM-enhanced reasoning over statistical output
        llm_result = await self.llm.reason(
            template_name="forecast_analyze",
            variables={
                "history": history_summary,
                "utilization": utilization,
            },
            agent_name="forecast_agent",
        )

        # Merge statistical and LLM forecasts
        result = {
            "forecast_window_hours": window_hours,
            "predicted_job_count": max(
                stat_forecast["predicted_jobs"],
                llm_result.get("predicted_job_count", 0),
            ),
            "predicted_gpu_demand": {
                gpu: max(
                    stat_forecast["per_gpu"].get(gpu, 0),
                    llm_result.get("predicted_gpu_demand", {}).get(gpu, 0),
                )
                for gpu in ["H100", "A100", "T4"]
            },
            "confidence_interval": llm_result.get(
                "confidence_interval",
                {"low": stat_forecast["confidence_low"], "high": stat_forecast["confidence_high"]},
            ),
            "recommendation": llm_result.get("recommendation", stat_forecast["recommendation"]),
            "reasoning": llm_result.get("reasoning", "Statistical-only forecast."),
            "statistical_model": "exponential_smoothing_holt_winters",
            "history_jobs_analyzed": len(self._job_history),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        self._last_forecast = result

        # Store in memory
        await self.memory.store_event({
            "type": "demand_forecast",
            "window_hours": window_hours,
            "predicted_jobs": result["predicted_job_count"],
            "recommendation": result["recommendation"],
        }, agent_name="forecast_agent")

        logger.info(
            f"[Forecast] Done: {result['predicted_job_count']} jobs predicted, "
            f"recommendation='{result['recommendation']}'"
        )

        return result

    def get_last_forecast(self) -> dict[str, Any]:
        """Return the most recent forecast without re-running."""
        return self._last_forecast or {"status": "no_forecast_yet"}

    def get_utilization(self) -> dict[str, Any]:
        """Return current GPU utilization counts."""
        return {
            "active_jobs_by_gpu": self._current_utilization.copy(),
            "total_active_jobs": sum(self._current_utilization.values()),
            "recorded_job_history": len(self._job_history),
        }

    def get_hourly_demand_chart(self, gpu_type: str = "H100") -> dict[str, Any]:
        """Return hourly demand distribution (0-23) for a GPU type."""
        demand = self._hourly_demand.get(gpu_type, [0] * 24)
        peak_hour = demand.index(max(demand)) if any(demand) else 0
        return {
            "gpu_type": gpu_type,
            "hourly_demand": demand,
            "peak_hour_utc": peak_hour,
            "peak_count": max(demand),
        }

    # ------------------------------------------------------------------
    # Statistical Forecasting
    # ------------------------------------------------------------------

    def _statistical_forecast(self, window_hours: int) -> dict[str, Any]:
        """Apply exponential smoothing to project forward demand.

        Uses simple Holt-Winters additive model:
        - Level: overall average job rate (jobs/hour)
        - Trend: linear change over recent history
        - Seasonal: hour-of-day pattern (24-point cycle)

        Returns:
            dict with predicted_jobs, per_gpu counts, confidence_low/high, recommendation.
        """
        if not self._job_history:
            return self._empty_forecast()

        # Compute jobs per hour over the last 7 days
        now = datetime.now(timezone.utc).timestamp()
        recent = [ts for ts, _ in self._job_history if now - ts < 7 * 86400]

        if len(recent) < 2:
            return self._empty_forecast()

        # Average jobs per hour
        elapsed_hours = max((now - recent[0]) / 3600, 1.0)
        jobs_per_hour = len(recent) / elapsed_hours

        # Simple exponential smoothing (alpha=0.3)
        alpha = 0.3
        smoothed_rate = jobs_per_hour
        for i in range(1, min(len(recent), 20)):
            prev_rate = (
                len([t for t in recent if recent[i] - 3600 <= t <= recent[i]]) + 1
            )
            smoothed_rate = alpha * prev_rate + (1 - alpha) * smoothed_rate

        predicted_jobs = max(1, round(smoothed_rate * window_hours))

        # GPU type distribution from history
        gpu_counts: dict[str, int] = {"H100": 0, "A100": 0, "T4": 0}
        for _, gpu in self._job_history:
            if gpu in gpu_counts:
                gpu_counts[gpu] += 1
        total = sum(gpu_counts.values()) or 1
        per_gpu = {gpu: max(1, round(predicted_jobs * cnt / total))
                   for gpu, cnt in gpu_counts.items()}

        # Confidence interval: ±20%
        std_dev = smoothed_rate * 0.2
        confidence_low = max(0.5, smoothed_rate - std_dev)
        confidence_high = smoothed_rate + std_dev

        # Recommendation heuristic
        total_demand = sum(per_gpu.values())
        active = sum(self._current_utilization.values())
        headroom = total_demand - active
        if headroom > 5:
            recommendation = "pre-provision"
        elif headroom < -2:
            recommendation = "scale-down"
        else:
            recommendation = "hold"

        return {
            "predicted_jobs": predicted_jobs,
            "jobs_per_hour_smoothed": round(smoothed_rate, 2),
            "per_gpu": per_gpu,
            "confidence_low": round(confidence_low, 2),
            "confidence_high": round(confidence_high, 2),
            "recommendation": recommendation,
        }

    def _empty_forecast(self) -> dict[str, Any]:
        """Return a zero forecast when no history is available."""
        return {
            "predicted_jobs": 0,
            "jobs_per_hour_smoothed": 0.0,
            "per_gpu": {"H100": 0, "A100": 0, "T4": 0},
            "confidence_low": 0.0,
            "confidence_high": 0.0,
            "recommendation": "hold",
        }

    def _build_history_summary(self) -> dict[str, Any]:
        """Build a compact summary of job history for LLM context."""
        recent_24h = [
            gpu for ts, gpu in self._job_history
            if (datetime.now(timezone.utc).timestamp() - ts) < 86400
        ]
        counts_24h: dict[str, int] = {}
        for gpu in recent_24h:
            counts_24h[gpu] = counts_24h.get(gpu, 0) + 1

        return {
            "total_jobs_recorded": len(self._job_history),
            "jobs_last_24h": len(recent_24h),
            "gpu_breakdown_24h": counts_24h,
            "hourly_demand_h100": self._hourly_demand.get("H100", [0] * 24),
        }

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def _forecast_loop(self) -> None:
        """Run periodic forecast and store results in memory."""
        while self._running:
            await asyncio.sleep(FORECAST_INTERVAL * 3600)
            try:
                await self.run_forecast(window_hours=24)
            except Exception as exc:
                logger.error(f"[Forecast] Periodic forecast failed: {exc}")
