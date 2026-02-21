"""OrQuanta Agentic v1.0 — Metrics Router."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends
from ..middleware.auth import get_current_user
from ...agents.tool_registry import ToolRegistry
from ...agents.scheduler_agent import SchedulerAgent
from ...agents.safety_governor import get_governor
from ...agents.cost_optimizer_agent import CostOptimizerAgent
from ...agents.forecast_agent import ForecastAgent

router = APIRouter(prefix="/api/v1/metrics", tags=["Metrics"])
_tools = ToolRegistry()
_scheduler: SchedulerAgent | None = None
_cost: CostOptimizerAgent | None = None
_forecast: ForecastAgent | None = None

def get_scheduler():
    global _scheduler
    if _scheduler is None: _scheduler = SchedulerAgent()
    return _scheduler

def get_cost():
    global _cost
    if _cost is None: _cost = CostOptimizerAgent()
    return _cost

def get_forecast():
    global _forecast
    if _forecast is None: _forecast = ForecastAgent()
    return _forecast


@router.get("", summary="Get platform-wide metrics")
async def get_platform_metrics(_: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return aggregated platform health and utilization metrics."""
    scheduler = get_scheduler()
    governor = get_governor()
    queue = scheduler.get_queue_status()
    spend = governor.get_spend_summary()
    return {
        "total_active_jobs": queue.get("total_jobs", 0),
        "queued_jobs": queue.get("queued_jobs", 0),
        "active_bins": queue.get("active_bins", 0),
        "jobs_by_status": queue.get("jobs_by_status", {}),
        "daily_spend_usd": spend["daily_spend_usd"],
        "daily_budget_remaining_usd": spend["remaining_usd"],
        "platform_utilization_pct": min(100.0, queue.get("total_jobs", 0) * 10),
        "emergency_stop_active": governor.is_stopped,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/gpu/{instance_id}", summary="Get GPU instance metrics")
async def get_gpu_metrics(instance_id: str, _: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Get real-time GPU telemetry for a specific instance."""
    return await _tools.get_gpu_metrics(instance_id)


@router.get("/spot-prices/{gpu_type}", summary="Get best spot prices for a GPU type")
async def get_spot_prices(gpu_type: str, _: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return cheapest spot prices across all providers for a GPU type."""
    prices = await _tools.get_all_spot_prices(gpu_type)
    return {"gpu_type": gpu_type, "prices": prices, "cheapest": prices[0] if prices else None}


@router.get("/cost/dashboard", summary="Get cost spend dashboard")
async def get_cost_dashboard(_: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return cost spend overview and provider comparison data."""
    cost = get_cost()
    return {
        **cost.get_spend_dashboard(),
        "provider_comparison_h100": cost.get_provider_comparison("H100"),
        "provider_comparison_a100": cost.get_provider_comparison("A100"),
    }


@router.get("/forecast", summary="Get GPU demand forecast")
async def get_forecast(_: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return the latest GPU demand forecast."""
    forecast = get_forecast()
    last = forecast.get_last_forecast()
    if not last or last.get("status") == "no_forecast_yet":
        last = await forecast.run_forecast(window_hours=24)
    return last


@router.get("/forecast/utilization", summary="Get current GPU utilization")
async def get_utilization(_: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return current tracked GPU utilization counts."""
    return get_forecast().get_utilization()
