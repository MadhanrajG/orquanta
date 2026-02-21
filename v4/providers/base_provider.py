"""
OrQuanta Agentic v1.0 — Base GPU Provider Contract

All cloud providers (AWS, GCP, Azure, CoreWeave) must implement this
abstract base class to guarantee a uniform interface for the ProviderRouter.

Every API call is:
  1. Retried with exponential backoff on transient errors.
  2. Timed and logged with cost attribution.
  3. Returned in a standard ProviderResponse envelope.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("orquanta.providers")

# ---------------------------------------------------------------------------
# Standard response schemas
# ---------------------------------------------------------------------------

@dataclass
class GPUInstance:
    """Represents a provisioned GPU instance across any provider."""
    instance_id: str
    provider: str
    region: str
    gpu_type: str           # H100 / A100 / T4 / V100 / L4
    gpu_count: int
    vram_gb: int
    vcpus: int
    ram_gb: float
    hourly_cost_usd: float
    status: str             # pending / running / stopping / terminated
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    spot: bool = False
    launched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)  # provider-raw response

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "provider": self.provider,
            "region": self.region,
            "gpu_type": self.gpu_type,
            "gpu_count": self.gpu_count,
            "vram_gb": self.vram_gb,
            "vcpus": self.vcpus,
            "ram_gb": self.ram_gb,
            "hourly_cost_usd": self.hourly_cost_usd,
            "status": self.status,
            "public_ip": self.public_ip,
            "private_ip": self.private_ip,
            "spot": self.spot,
            "launched_at": self.launched_at,
            "tags": self.tags,
        }


@dataclass
class SpotPrice:
    """Current spot price quote from a provider."""
    provider: str
    region: str
    gpu_type: str
    instance_type: str
    current_price_usd_hr: float
    on_demand_price_usd_hr: float
    availability: str       # high / medium / low / unavailable
    interruption_rate_pct: float = 5.0
    price_trend: str = "stable"  # rising / falling / stable
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def savings_pct(self) -> float:
        if self.on_demand_price_usd_hr <= 0:
            return 0.0
        return round((1 - self.current_price_usd_hr / self.on_demand_price_usd_hr) * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "region": self.region,
            "gpu_type": self.gpu_type,
            "instance_type": self.instance_type,
            "current_price_usd_hr": self.current_price_usd_hr,
            "on_demand_price_usd_hr": self.on_demand_price_usd_hr,
            "savings_pct": self.savings_pct(),
            "availability": self.availability,
            "interruption_rate_pct": self.interruption_rate_pct,
            "price_trend": self.price_trend,
            "fetched_at": self.fetched_at,
        }


@dataclass
class GPUMetrics:
    """Real-time telemetry from a running GPU instance."""
    instance_id: str
    provider: str
    gpu_index: int = 0
    gpu_utilization_pct: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    memory_utilization_pct: float = 0.0
    temp_celsius: float = 0.0
    power_watts: float = 0.0
    fan_speed_pct: float = 0.0
    pcie_throughput_mbps: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "provider": self.provider,
            "gpu_index": self.gpu_index,
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "memory_used_gb": round(self.memory_used_gb, 2),
            "memory_total_gb": round(self.memory_total_gb, 2),
            "memory_utilization_pct": self.memory_utilization_pct,
            "temp_celsius": self.temp_celsius,
            "power_watts": self.power_watts,
            "fan_speed_pct": self.fan_speed_pct,
            "timestamp": self.timestamp,
        }


@dataclass
class ProviderCallRecord:
    """Audit record for a single provider API call."""
    provider: str
    operation: str
    region: str
    latency_ms: float
    success: bool
    error: Optional[str] = None
    cost_usd: float = 0.0001   # Estimated API call cost
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

def with_retry(max_attempts: int = 3, base_delay: float = 1.0):
    """Async exponential backoff retry decorator for provider API calls."""
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except ProviderTemporaryError as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            f"[Provider] Retrying {fn.__name__} (attempt {attempt}/{max_attempts}) "
                            f"in {delay:.1f}s: {exc}"
                        )
                        await asyncio.sleep(delay)
                except ProviderPermanentError:
                    raise
            raise last_exc
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Provider exceptions
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Base provider error."""


class ProviderTemporaryError(ProviderError):
    """Transient error — retry is safe (throttling, network, timeout)."""


class ProviderPermanentError(ProviderError):
    """Permanent error — do not retry (auth failure, quota, bad config)."""


class ProviderUnavailableError(ProviderError):
    """Provider is completely offline or unreachable."""


class InsufficientCapacityError(ProviderError):
    """No GPU capacity available in the requested region."""


# ---------------------------------------------------------------------------
# Abstract Base Provider
# ---------------------------------------------------------------------------

@dataclass
class InstanceConfig:
    """Configuration for launching a GPU instance."""
    gpu_type: str                          # e.g. "gpu_1x_a100"
    gpu_count: int = 1
    region: Optional[str] = None
    name: Optional[str] = None
    ssh_key_name: Optional[str] = None
    user_data: Optional[str] = None
    spot: bool = True
    tags: dict = field(default_factory=dict)
    budget_usd: float = 0.0
    max_runtime_hours: float = 24.0


@dataclass
class ProvisionedInstance:
    """A successfully provisioned GPU instance."""
    instance_id: str
    provider: str
    gpu_type: str
    gpu_count: int
    region: str
    ip_address: str
    status: str                            # running / stopping / terminated
    cost_per_hour: float
    started_at: str
    ssh_user: str = "ubuntu"
    ssh_key_name: str = "orquanta-default"
    tags: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "provider": self.provider,
            "gpu_type": self.gpu_type,
            "gpu_count": self.gpu_count,
            "region": self.region,
            "ip_address": self.ip_address,
            "status": self.status,
            "cost_per_hour": self.cost_per_hour,
            "started_at": self.started_at,
        }


@dataclass
class GpuMetrics:
    """Real-time GPU metrics from a running instance."""
    instance_id: str
    gpu_utilization_pct: float = 0.0
    memory_utilization_pct: float = 0.0
    temp_celsius: float = 0.0
    power_watts: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "api"
    note: str = ""


@dataclass
class CommandResult:
    """Result of an SSH command execution on an instance."""
    instance_id: str
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class BaseGPUProvider(ABC):
    """Abstract interface all GPU cloud providers must implement.

    Subclasses should call ``self._record_call(...)`` after every
    API interaction for cost tracking and auditing.
    """

    # Provider metadata — override in subclass
    PROVIDER_NAME: str = "base"
    SUPPORTED_GPU_TYPES: list[str] = []
    REGIONS: list[str] = []

    def __init__(self) -> None:
        self._call_log: list[ProviderCallRecord] = []
        self._total_api_cost_usd: float = 0.0
        logger.info(f"[{self.PROVIDER_NAME}] Provider initialised.")

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def list_instances(self, region: str | None = None) -> list[GPUInstance]:
        """List all running GPU instances (optionally filtered by region)."""

    @abstractmethod
    async def spin_up(
        self,
        gpu_type: str,
        gpu_count: int = 1,
        region: str | None = None,
        spot: bool = True,
        tags: dict[str, str] | None = None,
    ) -> GPUInstance:
        """Provision a new GPU instance. Raises InsufficientCapacityError if none available."""

    @abstractmethod
    async def terminate(self, instance_id: str, region: str | None = None) -> bool:
        """Terminate an instance. Returns True if successful."""

    @abstractmethod
    async def get_metrics(self, instance_id: str, region: str | None = None) -> list[GPUMetrics]:
        """Fetch real-time GPU telemetry for an instance (one per GPU)."""

    @abstractmethod
    async def get_spot_prices(
        self, gpu_type: str, regions: list[str] | None = None
    ) -> list[SpotPrice]:
        """Get current spot prices for a GPU type across regions, sorted cheapest first."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Quick connectivity check. Returns True if the provider API is reachable."""

    # ------------------------------------------------------------------
    # Common utilities
    # ------------------------------------------------------------------

    def _record_call(
        self,
        operation: str,
        region: str,
        latency_ms: float,
        success: bool,
        error: str | None = None,
        cost_usd: float = 0.0001,
    ) -> None:
        """Record a provider API call for auditing and cost tracking."""
        record = ProviderCallRecord(
            provider=self.PROVIDER_NAME,
            operation=operation,
            region=region,
            latency_ms=latency_ms,
            success=success,
            error=error,
            cost_usd=cost_usd,
        )
        self._call_log.append(record)
        self._total_api_cost_usd += cost_usd

        if not success:
            logger.warning(
                f"[{self.PROVIDER_NAME}] API call failed: {operation} @ {region} — {error}"
            )

    def get_call_stats(self) -> dict[str, Any]:
        """Return summary statistics of all API calls made."""
        total = len(self._call_log)
        failed = sum(1 for c in self._call_log if not c.success)
        avg_latency = (
            sum(c.latency_ms for c in self._call_log) / total if total else 0.0
        )
        return {
            "provider": self.PROVIDER_NAME,
            "total_calls": total,
            "failed_calls": failed,
            "success_rate_pct": round((1 - failed / max(total, 1)) * 100, 1),
            "avg_latency_ms": round(avg_latency, 1),
            "total_api_cost_usd": round(self._total_api_cost_usd, 6),
        }

    async def timed_call(self, operation: str, region: str, coro):
        """Wrap a coroutine with timing and call recording."""
        t0 = time.monotonic()
        try:
            result = await coro
            latency = (time.monotonic() - t0) * 1000
            self._record_call(operation, region, latency, success=True)
            return result
        except Exception as exc:
            latency = (time.monotonic() - t0) * 1000
            self._record_call(operation, region, latency, success=False, error=str(exc))
            raise
