"""OrQuanta Agentic v1.0 — All Pydantic schemas and response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=254, description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password (min 8 chars)")
    name: str = Field("", max_length=120, description="Display name")

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        """Lowercase and strip whitespace; block obviously injected values."""
        import re
        v = str(v).strip().lower()
        # Block SQL/script injection — hyphen alone is valid in emails (user@my-domain.com)
        # Double-dash (SQL comment) is caught by the |-- branch
        if re.search(r"[<>'\"\\;]|--", v):
            raise ValueError("Invalid characters in email address")
        return v

    @field_validator("name", mode="before")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        import re
        return re.sub(r"<[^>]*>", "", str(v)).strip()


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: str


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

class GoalSubmitRequest(BaseModel):
    raw_text: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Natural language description of what you want to accomplish.",
        examples=["Train a LLaMA 3 70B model on my medical dataset using 4×H100 GPUs"],
    )
    budget_usd: Optional[float] = Field(None, ge=0.0, description="Optional budget cap in USD")
    priority: Optional[float] = Field(0.5, ge=0.0, le=1.0, description="Priority 0.0-1.0")

    @model_validator(mode="before")
    @classmethod
    def accept_goal_alias(cls, data: Any) -> Any:
        """Accept 'goal' as an alias for 'raw_text' so both field names work."""
        if isinstance(data, dict) and "goal" in data and "raw_text" not in data:
            data = dict(data)
            data["raw_text"] = data.pop("goal")
        return data

    @field_validator("raw_text", mode="before")
    @classmethod
    def sanitize_raw_text(cls, v: str) -> str:
        """Strip HTML/script tags to prevent XSS reflection via goal text."""
        import re
        v = re.sub(r"<[^>]*>", "", str(v))   # strip HTML tags
        v = v.replace("&", "&amp;").replace('"', "&quot;")
        return v.strip()


class TaskStatus(BaseModel):
    task_id: str
    agent: str
    action: str
    status: str  # pending/running/completed/failed
    result: Optional[dict[str, Any]] = None


class GoalResponse(BaseModel):
    goal_id: str
    raw_text: str
    status: str
    plan: Optional[dict[str, Any]] = None
    tasks: list[dict[str, Any]] = []
    completed_tasks: list[str] = []
    failed_tasks: list[str] = []
    result: dict[str, Any] = {}
    cost_incurred_usd: float = 0.0
    reasoning_steps: int = 0
    created_at: str
    updated_at: str


class GoalListResponse(BaseModel):
    goals: list[GoalResponse]
    total: int


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class JobCreateRequest(BaseModel):
    intent: str = Field(..., min_length=5, max_length=500, description="Job description")
    goal_id: Optional[str] = Field(None, description="Parent goal ID to associate this job with")
    gpu_type: str = Field("H100", description="GPU model: H100/A100/T4/A10G")
    gpu_count: int = Field(1, ge=1, le=64)
    provider: str = Field("aws", description="Cloud provider: aws/gcp/azure/coreweave")
    required_vram_gb: int = Field(40, ge=1, le=10000)
    max_runtime_minutes: int = Field(120, ge=1, le=10080)
    max_cost_usd: float = Field(500.0, ge=0.0)
    priority: float = Field(0.5, ge=0.0, le=1.0)

    @field_validator("intent", mode="before")
    @classmethod
    def sanitize_intent(cls, v: str) -> str:
        """Strip HTML tags and dangerous characters to prevent XSS reflection."""
        import re
        v = re.sub(r"<[^>]*>", "", str(v))          # strip HTML tags
        v = v.replace("&", "&amp;").replace('"', "&quot;")
        return v.strip()


class JobResponse(BaseModel):
    job_id: str
    intent: str
    gpu_type: str
    gpu_count: int
    provider: str
    required_vram_gb: int
    status: str
    priority: float
    instance_id: Optional[str] = None
    enqueued_at: str
    started_at: Optional[str] = None
    preempted_count: int = 0


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    queue_status: dict[str, Any] = {}


class JobCancelResponse(BaseModel):
    job_id: str
    status: str
    message: str = ""


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class AgentStatusResponse(BaseModel):
    name: str
    status: str  # idle/thinking/acting/monitoring/error
    description: str
    active_tasks: int = 0
    last_action: Optional[str] = None


class AgentListResponse(BaseModel):
    agents: list[AgentStatusResponse]
    emergency_stop_active: bool


class AgentControlRequest(BaseModel):
    reason: str = Field("", description="Human-readable reason for this action")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class GPUMetricsResponse(BaseModel):
    instance_id: str
    gpu_utilization_pct: float
    memory_used_gb: float
    memory_total_gb: float
    memory_utilization_pct: float
    temp_celsius: float
    power_watts: float
    timestamp: str


class PlatformMetricsResponse(BaseModel):
    total_active_jobs: int
    total_instances: int
    platform_utilization_pct: float
    daily_spend_usd: float
    daily_budget_remaining_usd: float
    jobs_completed_today: int
    jobs_failed_today: int
    avg_job_duration_minutes: float
    timestamp: str


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditEntryResponse(BaseModel):
    id: str
    agent_name: str
    action: str
    reasoning: str
    payload: dict[str, Any]
    outcome: str
    cost_impact: float
    approved: bool
    created_at: str


class AuditListResponse(BaseModel):
    entries: list[AuditEntryResponse]
    total: int
    offset: int
    limit: int


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

class SpotPriceResponse(BaseModel):
    provider: str
    region: str
    gpu_type: str
    current_price_usd_hr: float
    price_24h_avg_usd_hr: float
    price_7d_low_usd_hr: float
    price_7d_high_usd_hr: float
    availability: str
    fetched_at: str


class CostForecastResponse(BaseModel):
    job_id: str
    gpu_type: str
    base_estimate_usd: float
    smoothed_estimate_usd: float
    confidence_bounds: dict[str, float]
    hourly_rate_used: float
    duration_hours: float


class CostRecommendationResponse(BaseModel):
    recommended_provider: str
    recommended_gpu: str
    estimated_hourly_cost: float
    estimated_total_cost_usd: float
    savings_vs_on_demand_pct: float
    reasoning: str
    alternatives: list[dict[str, Any]]
    budget_within_limit: bool


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    components: dict[str, str]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    timestamp: str

    @classmethod
    def from_exception(cls, exc: Exception) -> "ErrorResponse":
        return cls(
            error=type(exc).__name__,
            detail=str(exc),
            timestamp=datetime.now().isoformat(),
        )


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = ""
