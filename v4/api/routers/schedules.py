"""
OrQuanta  -  Cron Scheduler for Recurring GPU Jobs (OpenClaw-inspired)

Allows users to schedule GPU workloads on a cron expression.
Examples:
  "0 2 * * MON"  -> every Monday at 2am
  "0 */6 * * *"  -> every 6 hours
  "0 9 * * *"    -> every day at 9am

API Endpoints (registered in main.py):
  POST   /api/v1/schedules              Create a schedule
  GET    /api/v1/schedules              List user schedules
  PUT    /api/v1/schedules/{id}         Update/pause/resume
  DELETE /api/v1/schedules/{id}         Delete schedule
  GET    /api/v1/schedules/{id}/runs    Run history

Background Task:
  CronScheduler.run()  -  ticks every 60s, fires due schedules
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..middleware.auth import get_current_user

logger = logging.getLogger("orquanta.scheduler.cron")

router = APIRouter(prefix="/api/v1/schedules", tags=["schedules"])

# --- In-memory store (replace with DB in production) -------------------------
_schedules: dict[str, dict] = {}   # id -> schedule record
_runs: dict[str, list] = {}        # schedule_id -> run history


# --- Schemas -----------------------------------------------------------------

class ScheduleCreate(BaseModel):
    goal: str
    cron_expr: str               # Standard 5-field cron: "0 2 * * MON"
    budget_usd: float = 50.0
    gpu_type: str = "A100"
    provider: str | None = None  # None = auto-select cheapest
    description: str = ""
    enabled: bool = True
    notify_channels: list[str] = ["email", "in_app"]


class ScheduleUpdate(BaseModel):
    goal: str | None = None
    cron_expr: str | None = None
    budget_usd: float | None = None
    gpu_type: str | None = None
    description: str | None = None
    enabled: bool | None = None
    notify_channels: list[str] | None = None


class ScheduleOut(BaseModel):
    id: str
    goal: str
    cron_expr: str
    cron_description: str
    budget_usd: float
    gpu_type: str
    provider: str | None
    description: str
    enabled: bool
    notify_channels: list[str]
    created_at: str
    next_run: str | None
    last_run: str | None
    run_count: int
    last_status: str | None


# --- Auth dependency ----------------------------------------------------------

CurrentUser = Annotated[dict, Depends(get_current_user)]


# --- Routes ------------------------------------------------------------------

@router.post("", response_model=ScheduleOut, status_code=201)
async def create_schedule(body: ScheduleCreate, user: CurrentUser):
    """Create a new recurring GPU job schedule."""
    _validate_cron(body.cron_expr)

    sid = f"sched-{secrets.token_hex(6)}"
    record = {
        "id": sid,
        "user_id": user["sub"],
        "goal": body.goal,
        "cron_expr": body.cron_expr,
        "budget_usd": body.budget_usd,
        "gpu_type": body.gpu_type,
        "provider": body.provider,
        "description": body.description,
        "enabled": body.enabled,
        "notify_channels": body.notify_channels,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "next_run": _next_run_iso(body.cron_expr),
        "last_run": None,
        "run_count": 0,
        "last_status": None,
    }
    _schedules[sid] = record
    _runs[sid] = []
    logger.info(f"[CronScheduler] Created {sid}: '{body.goal[:40]}...' @ '{body.cron_expr}'")
    return _to_out(record)


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(user: CurrentUser):
    """List all schedules for the current user."""
    return [_to_out(s) for s in _schedules.values() if s["user_id"] == user["sub"]]


@router.put("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(schedule_id: str, body: ScheduleUpdate, user: CurrentUser):
    """Update or pause/resume a schedule."""
    sched = _schedules.get(schedule_id)
    if not sched or sched["user_id"] != user["sub"]:
        raise HTTPException(status_code=404, detail="Schedule not found")

    updates = body.model_dump(exclude_none=True)
    if "cron_expr" in updates:
        _validate_cron(updates["cron_expr"])

    sched.update(updates)

    # Recalculate next run if cron changed or re-enabled
    if "cron_expr" in updates or (updates.get("enabled") is True):
        sched["next_run"] = _next_run_iso(sched["cron_expr"]) if sched["enabled"] else None

    return _to_out(sched)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: str, user: CurrentUser):
    """Delete a schedule permanently."""
    sched = _schedules.get(schedule_id)
    if not sched or sched["user_id"] != user["sub"]:
        raise HTTPException(status_code=404, detail="Schedule not found")
    _schedules.pop(schedule_id)
    _runs.pop(schedule_id, None)


@router.get("/{schedule_id}/runs")
async def get_runs(schedule_id: str, user: CurrentUser):
    """Get run history for a schedule."""
    sched = _schedules.get(schedule_id)
    if not sched or sched["user_id"] != user["sub"]:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _runs.get(schedule_id, [])[-50:]


# --- Background CronScheduler ------------------------------------------------

class CronScheduler:
    """
    Background asyncio task that checks every minute for due schedules
    and fires them through the normal OrQuanta goal pipeline.
    """

    def __init__(self, tick_interval: int = 60) -> None:
        self._tick = tick_interval
        self._running = False

    async def run(self) -> None:
        """Start the cron loop. Call this from main.py lifespan."""
        self._running = True
        logger.info("[CronScheduler] Started  -  ticking every 60s")
        while self._running:
            try:
                await self._tick_once()
            except Exception as exc:
                logger.error(f"[CronScheduler] Tick error: {exc}")
            await asyncio.sleep(self._tick)

    def stop(self) -> None:
        self._running = False

    async def _tick_once(self) -> None:
        now = datetime.now(timezone.utc)
        due = [
            s for s in _schedules.values()
            if s["enabled"] and s.get("next_run") and _is_due(s["next_run"], now)
        ]
        for sched in due:
            await self._fire_schedule(sched, now)

    async def _fire_schedule(self, sched: dict, fired_at: datetime) -> None:
        import secrets as _sec
        job_id = f"job-{_sec.token_hex(6)}"
        run_record = {
            "run_id": _sec.token_hex(6),
            "job_id": job_id,
            "fired_at": fired_at.isoformat(),
            "goal": sched["goal"][:80],
            "status": "triggered",
        }
        _runs.setdefault(sched["id"], []).append(run_record)
        if len(_runs[sched["id"]]) > 100:
            _runs[sched["id"]] = _runs[sched["id"]][-100:]

        sched["last_run"] = fired_at.isoformat()
        sched["run_count"] = sched.get("run_count", 0) + 1
        sched["last_status"] = "triggered"
        sched["next_run"] = _next_run_iso(sched["cron_expr"])

        logger.info(
            f"[CronScheduler] Fired '{sched['goal'][:40]}...' "
            f"(job_id={job_id}, next={sched['next_run']})"
        )

        # Submit goal to the orchestrator
        try:
            from .goals import get_orchestrator as _get_orch
            real_goal_id = await _get_orch().submit_goal(
                raw_text=sched["goal"],
                user_id=sched["user_id"],
            )
            run_record["goal_id"] = real_goal_id
            run_record["status"] = "submitted"
            sched["last_status"] = "submitted"
            logger.info(f"[CronScheduler] Goal submitted: {real_goal_id}")
        except Exception as exc:
            logger.error(f"[CronScheduler] Goal submission failed: {exc}")
            run_record["status"] = "failed"
            sched["last_status"] = "failed"

        # Fire notifications
        await self._notify(sched, job_id)

    async def _notify(self, sched: dict, job_id: str) -> None:
        try:
            from v4.notifications.notification_service import get_notification_service, NotificationEvent
            svc = get_notification_service()
            await svc.send(NotificationEvent(
                user_id=sched["user_id"],
                type="job_started",
                data={
                    "job_id": job_id,
                    "goal_summary": sched["goal"][:80],
                    "gpu_type": sched["gpu_type"],
                    "provider": sched.get("provider") or "auto",
                    "estimated_cost_usd": sched["budget_usd"],
                    "message": f"Scheduled job triggered: {sched['goal'][:60]}",
                },
                channels=sched.get("notify_channels", ["email", "in_app"]),
                priority="high",
            ))
        except Exception as exc:
            logger.warning(f"[CronScheduler] Notification failed: {exc}")


# --- Helpers -----------------------------------------------------------------

def _validate_cron(expr: str) -> None:
    """Validate a 5-field cron expression. Raises HTTPException on error."""
    try:
        from croniter import croniter
        if not croniter.is_valid(expr):
            raise ValueError()
    except ImportError:
        # croniter not installed  -  basic field count check
        if len(expr.split()) != 5:
            raise HTTPException(status_code=422, detail=f"Invalid cron expression: '{expr}'. Expected 5 fields.")
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: '{expr}'")


def _next_run_iso(expr: str) -> str | None:
    """Get the next scheduled run time in ISO8601."""
    try:
        from croniter import croniter
        from datetime import timezone
        import time
        it = croniter(expr, datetime.now(timezone.utc))
        return it.get_next(datetime).isoformat()
    except Exception:
        return None


def _is_due(next_run_iso: str, now: datetime) -> bool:
    """Return True if the scheduled time is now or in the past."""
    try:
        scheduled = datetime.fromisoformat(next_run_iso)
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        return now >= scheduled
    except Exception:
        return False


def _cron_description(expr: str) -> str:
    """Human-readable cron description."""
    common = {
        "0 * * * *":    "Every hour",
        "0 0 * * *":    "Every day at midnight",
        "0 9 * * *":    "Every day at 9am",
        "0 0 * * 1":    "Every Monday at midnight",
        "0 2 * * 1":    "Every Monday at 2am",
        "0 0 1 * *":    "1st of every month",
        "*/5 * * * *":  "Every 5 minutes",
        "*/15 * * * *": "Every 15 minutes",
        "0 */6 * * *":  "Every 6 hours",
    }
    return common.get(expr, f"Cron: {expr}")


def _to_out(s: dict) -> ScheduleOut:
    return ScheduleOut(
        id=s["id"],
        goal=s["goal"],
        cron_expr=s["cron_expr"],
        cron_description=_cron_description(s["cron_expr"]),
        budget_usd=s["budget_usd"],
        gpu_type=s["gpu_type"],
        provider=s.get("provider"),
        description=s.get("description", ""),
        enabled=s["enabled"],
        notify_channels=s.get("notify_channels", []),
        created_at=s["created_at"],
        next_run=s.get("next_run"),
        last_run=s.get("last_run"),
        run_count=s.get("run_count", 0),
        last_status=s.get("last_status"),
    )


# --- Singleton ----------------------------------------------------------------
_scheduler: CronScheduler | None = None

def get_cron_scheduler() -> CronScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler
