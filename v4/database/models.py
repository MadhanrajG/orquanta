"""
OrQuanta Agentic v1.0 — SQLAlchemy ORM Models

Async ORM using SQLAlchemy 2.0 + asyncpg.
All models map directly to the schema in 001_initial.sql.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, ARRAY, BigInteger, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://orquanta:orquanta@localhost:5432/orquanta")
# SQLAlchemy needs asyncpg URL scheme
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


# ─── Engine setup ────────────────────────────────────────────────────────────

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db():
    """Dependency injection for FastAPI routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─── Base ────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


# ─── Models ──────────────────────────────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    plan = Column(String(50), nullable=False, default="starter")
    daily_budget_usd = Column(Numeric(12, 4), default=5000.00)
    monthly_quota_usd = Column(Numeric(12, 4), default=50000.00)
    stripe_customer_id = Column(String(100))
    stripe_subscription_id = Column(String(100))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    users = relationship("User", back_populates="organization")
    api_keys = relationship("APIKey", back_populates="organization")
    jobs = relationship("Job", back_populates="organization")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "plan": self.plan,
            "daily_budget_usd": float(self.daily_budget_usd or 0),
        }


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"))
    email = Column(String(320), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    name = Column(String(200))
    role = Column(String(50), nullable=False, default="operator")
    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization", back_populates="users")
    api_keys = relationship("APIKey", back_populates="user")
    jobs = relationship("Job", back_populates="user")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "is_active": self.is_active,
            "organization_id": self.organization_id,
        }


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(200), nullable=False)
    key_prefix = Column(String(20), nullable=False)
    key_hash = Column(String(200), nullable=False, unique=True)
    scopes = Column(ARRAY(String), nullable=False, default=["read"])
    expires_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    organization = relationship("Organization", back_populates="api_keys")
    user = relationship("User", back_populates="api_keys")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "key_prefix": self.key_prefix + "...",
            "scopes": self.scopes,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "is_active": self.is_active,
        }


class Goal(Base):
    __tablename__ = "goals"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    raw_text = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="accepted")
    budget_usd = Column(Numeric(12, 4))
    cost_incurred_usd = Column(Numeric(12, 4), nullable=False, default=0)
    plan = Column(JSONB)
    reasoning_log = Column(JSONB, nullable=False, default=list)
    completed_tasks = Column(JSONB, nullable=False, default=list)
    failed_tasks = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    jobs = relationship("Job", back_populates="goal")
    audit_entries = relationship("AuditLog", back_populates="goal")

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.id,
            "raw_text": self.raw_text,
            "status": self.status,
            "budget_usd": float(self.budget_usd or 0),
            "cost_incurred_usd": float(self.cost_incurred_usd or 0),
            "plan": self.plan,
            "reasoning_steps": len(self.reasoning_log or []),
            "completed_tasks": self.completed_tasks or [],
            "failed_tasks": self.failed_tasks or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Instance(Base):
    __tablename__ = "instances"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"))
    provider_instance_id = Column(String(200), unique=True, nullable=False)
    provider = Column(String(50), nullable=False)
    region = Column(String(100), nullable=False)
    gpu_type = Column(String(100), nullable=False)
    gpu_count = Column(Integer, nullable=False, default=1)
    vram_gb = Column(Integer, nullable=False)
    hourly_rate_usd = Column(Numeric(10, 6), nullable=False)
    spot = Column(Boolean, nullable=False, default=True)
    status = Column(String(50), nullable=False, default="running")
    public_ip = Column(INET)
    private_ip = Column(INET)
    tags = Column(JSONB, nullable=False, default=dict)
    launched_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    terminated_at = Column(DateTime(timezone=True))
    total_cost_usd = Column(Numeric(12, 6), nullable=False, default=0)

    jobs = relationship("Job", back_populates="instance")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider_instance_id": self.provider_instance_id,
            "provider": self.provider,
            "region": self.region,
            "gpu_type": self.gpu_type,
            "gpu_count": self.gpu_count,
            "vram_gb": self.vram_gb,
            "hourly_rate_usd": float(self.hourly_rate_usd),
            "spot": self.spot,
            "status": self.status,
            "public_ip": str(self.public_ip) if self.public_ip else None,
            "total_cost_usd": float(self.total_cost_usd or 0),
        }


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    goal_id = Column(UUID(as_uuid=False), ForeignKey("goals.id", ondelete="SET NULL"))
    instance_id = Column(UUID(as_uuid=False), ForeignKey("instances.id", ondelete="SET NULL"))
    intent = Column(Text, nullable=False)
    gpu_type = Column(String(100), nullable=False)
    gpu_count = Column(Integer, nullable=False, default=1)
    provider = Column(String(50))
    required_vram_gb = Column(Integer)
    max_cost_usd = Column(Numeric(12, 4))
    max_runtime_minutes = Column(Integer)
    priority_score = Column(Numeric(5, 4), nullable=False, default=0.5)
    status = Column(String(50), nullable=False, default="queued")
    exit_code = Column(Integer)
    cost_incurred_usd = Column(Numeric(12, 6), nullable=False, default=0)
    duration_seconds = Column(Numeric(10, 2))
    logs_url = Column(Text)
    artifacts = Column(JSONB, nullable=False, default=list)
    gpu_peak_util_pct = Column(Numeric(5, 2))
    gpu_peak_mem_gb = Column(Numeric(8, 2))
    metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    organization = relationship("Organization", back_populates="jobs")
    user = relationship("User", back_populates="jobs")
    goal = relationship("Goal", back_populates="jobs")
    instance = relationship("Instance", back_populates="jobs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "intent": self.intent,
            "gpu_type": self.gpu_type,
            "gpu_count": self.gpu_count,
            "provider": self.provider,
            "required_vram_gb": self.required_vram_gb,
            "max_cost_usd": float(self.max_cost_usd or 0),
            "priority_score": float(self.priority_score or 0.5),
            "status": self.status,
            "cost_incurred_usd": float(self.cost_incurred_usd or 0),
            "duration_seconds": float(self.duration_seconds or 0),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"))
    goal_id = Column(UUID(as_uuid=False), ForeignKey("goals.id", ondelete="SET NULL"))
    job_id = Column(UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="SET NULL"))
    agent_name = Column(String(100), nullable=False)
    action = Column(String(200), nullable=False)
    reasoning = Column(Text)
    payload = Column(JSONB, nullable=False, default=dict)
    outcome = Column(String(50), nullable=False, default="pending")
    cost_impact_usd = Column(Numeric(12, 6), nullable=False, default=0)
    duration_ms = Column(Numeric(10, 2))
    safety_approved = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    goal = relationship("Goal", back_populates="audit_entries")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "action": self.action,
            "reasoning": self.reasoning,
            "outcome": self.outcome,
            "cost_impact": float(self.cost_impact_usd or 0),
            "safety_approved": self.safety_approved,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CostRecord(Base):
    __tablename__ = "cost_records"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    organization_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"))
    job_id = Column(UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="SET NULL"))
    instance_id = Column(UUID(as_uuid=False), ForeignKey("instances.id", ondelete="SET NULL"))
    provider = Column(String(50), nullable=False)
    gpu_type = Column(String(100), nullable=False)
    gpu_count = Column(Integer, nullable=False, default=1)
    cost_usd = Column(Numeric(12, 6), nullable=False)
    duration_seconds = Column(Numeric(12, 2), nullable=False)
    hourly_rate_usd = Column(Numeric(10, 6), nullable=False)
    billing_date = Column(Date, nullable=False, default=func.current_date())
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "gpu_type": self.gpu_type,
            "gpu_count": self.gpu_count,
            "cost_usd": float(self.cost_usd),
            "duration_hours": round(float(self.duration_seconds) / 3600, 4),
            "billing_date": str(self.billing_date),
        }


class SpotPriceHistory(Base):
    __tablename__ = "spot_price_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    provider = Column(String(50), nullable=False)
    region = Column(String(100), nullable=False)
    gpu_type = Column(String(100), nullable=False)
    instance_type = Column(String(100), nullable=False)
    price_usd_hr = Column(Numeric(10, 6), nullable=False)
    availability = Column(String(20))
    recorded_at = Column(DateTime(timezone=True), default=_now, nullable=False)
