"""
OrQuanta Agentic v1.0 — Data Access Layer (Repositories)

Repository pattern for clean separation between business logic and DB.
All methods are async and use the SQLAlchemy 2.0 async API.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select, update, func, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Organization, User, APIKey, Goal, Instance, Job, AuditLog,
    CostRecord, SpotPriceHistory,
)

logger = logging.getLogger("orquanta.database.repositories")


# ─── Organization Repository ──────────────────────────────────────────────────

class OrganizationRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, org_id: str) -> Organization | None:
        result = await self.db.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self.db.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()

    async def create(self, name: str, slug: str, plan: str = "starter") -> Organization:
        org = Organization(name=name, slug=slug, plan=plan)
        self.db.add(org)
        await self.db.flush()
        return org

    async def update_budget(self, org_id: str, daily_budget_usd: float) -> None:
        await self.db.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(daily_budget_usd=daily_budget_usd)
        )


# ─── User Repository ─────────────────────────────────────────────────────────

class UserRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        hashed_password: str,
        name: str = "",
        role: str = "operator",
        organization_id: str | None = None,
    ) -> User:
        user = User(
            email=email.lower(),
            hashed_password=hashed_password,
            name=name,
            role=role,
            organization_id=organization_id,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def update_last_login(self, user_id: str) -> None:
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(timezone.utc))
        )

    async def list_by_org(self, org_id: str) -> list[User]:
        result = await self.db.execute(
            select(User).where(User.organization_id == org_id)
        )
        return list(result.scalars().all())


# ─── Goal Repository ─────────────────────────────────────────────────────────

class GoalRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, goal_id: str) -> Goal | None:
        result = await self.db.execute(select(Goal).where(Goal.id == goal_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        raw_text: str,
        user_id: str | None,
        organization_id: str,
        budget_usd: float | None = None,
    ) -> Goal:
        goal = Goal(
            raw_text=raw_text,
            user_id=user_id,
            organization_id=organization_id,
            budget_usd=budget_usd,
        )
        self.db.add(goal)
        await self.db.flush()
        return goal

    async def update_status(self, goal_id: str, status: str) -> None:
        await self.db.execute(
            update(Goal).where(Goal.id == goal_id).values(status=status)
        )

    async def update_plan(
        self,
        goal_id: str,
        plan: dict,
        reasoning_log: list,
        status: str | None = None,
    ) -> None:
        vals: dict[str, Any] = {"plan": plan, "reasoning_log": reasoning_log}
        if status:
            vals["status"] = status
        await self.db.execute(update(Goal).where(Goal.id == goal_id).values(**vals))

    async def mark_task_complete(self, goal_id: str, task_id: str) -> None:
        goal = await self.get_by_id(goal_id)
        if goal:
            tasks = list(goal.completed_tasks or [])
            if task_id not in tasks:
                tasks.append(task_id)
            await self.db.execute(
                update(Goal).where(Goal.id == goal_id)
                .values(completed_tasks=tasks)
            )

    async def add_cost(self, goal_id: str, cost_usd: float) -> None:
        await self.db.execute(
            update(Goal).where(Goal.id == goal_id)
            .values(cost_incurred_usd=Goal.cost_incurred_usd + cost_usd)
        )

    async def list_by_user(
        self, user_id: str | None, organization_id: str,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[Goal], int]:
        q = select(Goal).where(Goal.organization_id == organization_id)
        if user_id:
            q = q.where(Goal.user_id == user_id)
        total_q = select(func.count()).select_from(q.subquery())
        total = (await self.db.execute(total_q)).scalar_one()
        result = await self.db.execute(
            q.order_by(Goal.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total


# ─── Job Repository ──────────────────────────────────────────────────────────

class JobRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, job_id: str) -> Job | None:
        result = await self.db.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        intent: str,
        gpu_type: str,
        gpu_count: int,
        organization_id: str,
        user_id: str | None = None,
        goal_id: str | None = None,
        provider: str | None = None,
        required_vram_gb: int | None = None,
        max_cost_usd: float | None = None,
        max_runtime_minutes: int | None = None,
        priority_score: float = 0.5,
        metadata: dict | None = None,
    ) -> Job:
        job = Job(
            intent=intent,
            gpu_type=gpu_type,
            gpu_count=gpu_count,
            organization_id=organization_id,
            user_id=user_id,
            goal_id=goal_id,
            provider=provider,
            required_vram_gb=required_vram_gb,
            max_cost_usd=max_cost_usd,
            max_runtime_minutes=max_runtime_minutes,
            priority_score=priority_score,
            metadata=metadata or {},
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def update_status(
        self,
        job_id: str,
        status: str,
        exit_code: int | None = None,
        cost_usd: float | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        vals: dict[str, Any] = {"status": status}
        if exit_code is not None:
            vals["exit_code"] = exit_code
        if cost_usd is not None:
            vals["cost_incurred_usd"] = cost_usd
        if duration_seconds is not None:
            vals["duration_seconds"] = duration_seconds
        if status == "running":
            vals["started_at"] = datetime.now(timezone.utc)
        if status in ("completed", "failed", "cancelled"):
            vals["completed_at"] = datetime.now(timezone.utc)
        await self.db.execute(update(Job).where(Job.id == job_id).values(**vals))

    async def list_by_org(
        self,
        organization_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        q = select(Job).where(Job.organization_id == organization_id)
        if status:
            q = q.where(Job.status == status)
        total = (await self.db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        result = await self.db.execute(
            q.order_by(Job.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total

    async def get_org_daily_spend(self, organization_id: str) -> float:
        result = await self.db.execute(
            select(func.sum(Job.cost_incurred_usd))
            .where(
                and_(
                    Job.organization_id == organization_id,
                    func.date(Job.created_at) == date.today(),
                )
            )
        )
        return float(result.scalar_one() or 0.0)


# ─── Audit Log Repository ────────────────────────────────────────────────────

class AuditRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        organization_id: str,
        agent_name: str,
        action: str,
        reasoning: str,
        payload: dict,
        outcome: str = "pending",
        cost_impact_usd: float = 0.0,
        goal_id: str | None = None,
        job_id: str | None = None,
        duration_ms: float | None = None,
        safety_approved: bool = True,
    ) -> AuditLog:
        entry = AuditLog(
            organization_id=organization_id,
            agent_name=agent_name,
            action=action,
            reasoning=reasoning,
            payload=payload,
            outcome=outcome,
            cost_impact_usd=cost_impact_usd,
            goal_id=goal_id,
            job_id=job_id,
            duration_ms=duration_ms,
            safety_approved=safety_approved,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def update_outcome(self, entry_id: str, outcome: str) -> None:
        await self.db.execute(
            update(AuditLog).where(AuditLog.id == entry_id).values(outcome=outcome)
        )

    async def list_by_org(
        self,
        organization_id: str,
        agent: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        q = select(AuditLog).where(AuditLog.organization_id == organization_id)
        if agent:
            q = q.where(AuditLog.agent_name == agent)
        total = (await self.db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        result = await self.db.execute(
            q.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total

    async def get_daily_spend(self, organization_id: str) -> float:
        result = await self.db.execute(
            select(func.sum(AuditLog.cost_impact_usd))
            .where(
                and_(
                    AuditLog.organization_id == organization_id,
                    func.date(AuditLog.created_at) == date.today(),
                    AuditLog.outcome.in_(["success", "approved"]),
                )
            )
        )
        return float(result.scalar_one() or 0.0)

    async def get_stats(self, organization_id: str) -> dict[str, Any]:
        total = (await self.db.execute(
            select(func.count()).where(AuditLog.organization_id == organization_id)
        )).scalar_one()
        successful = (await self.db.execute(
            select(func.count()).where(
                and_(AuditLog.organization_id == organization_id, AuditLog.outcome == "success")
            )
        )).scalar_one()
        daily_spend = await self.get_daily_spend(organization_id)
        return {
            "total_actions_logged": total,
            "successful_actions": successful,
            "failed_actions": total - successful,
            "daily_spend_usd": round(daily_spend, 4),
        }


# ─── Cost Record Repository ──────────────────────────────────────────────────

class CostRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        organization_id: str,
        provider: str,
        gpu_type: str,
        gpu_count: int,
        cost_usd: float,
        duration_seconds: float,
        hourly_rate_usd: float,
        job_id: str | None = None,
        instance_id: str | None = None,
    ) -> CostRecord:
        record = CostRecord(
            organization_id=organization_id,
            provider=provider,
            gpu_type=gpu_type,
            gpu_count=gpu_count,
            cost_usd=cost_usd,
            duration_seconds=duration_seconds,
            hourly_rate_usd=hourly_rate_usd,
            job_id=job_id,
            instance_id=instance_id,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def get_monthly_by_provider(self, organization_id: str) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(CostRecord.provider, func.sum(CostRecord.cost_usd).label("total"))
            .where(
                and_(
                    CostRecord.organization_id == organization_id,
                    func.date_trunc("month", CostRecord.created_at) == func.date_trunc("month", func.now()),
                )
            )
            .group_by(CostRecord.provider)
        )
        return [{"provider": r.provider, "total_usd": float(r.total)} for r in result.all()]
