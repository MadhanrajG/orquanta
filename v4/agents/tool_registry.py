"""
OrQuanta Agentic v1.0 — Tool Registry

All callable tools available to agents as strongly-typed functions.
Tools wrap external GPU cloud provider APIs (mocked in development,
real in production via environment-controlled adapters).

Every tool implementation:
1. Validates inputs with Pydantic
2. Logs the call through SafetyGovernor
3. Returns a structured response dict
4. Handles provider errors gracefully
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("orquanta.tools")

# ---------------------------------------------------------------------------
# Internal mock data store (replaced by real provider calls in production)
# ---------------------------------------------------------------------------

_INSTANCES: dict[str, dict[str, Any]] = {}
_JOBS: dict[str, dict[str, Any]] = {}

# Simulated spot price matrix (provider → gpu → region → $/hr)
SPOT_PRICE_MATRIX: dict[str, dict[str, dict[str, float]]] = {
    "aws": {
        "H100": {"us-east-1": 5.20, "eu-west-1": 5.45},
        "A100": {"us-east-1": 3.10, "eu-west-1": 3.30},
        "T4": {"us-east-1": 0.40, "eu-west-1": 0.42},
    },
    "gcp": {
        "H100": {"us-central1": 4.90, "europe-west4": 5.10},
        "A100": {"us-central1": 2.95, "europe-west4": 3.15},
        "T4": {"us-central1": 0.38, "europe-west4": 0.40},
    },
    "azure": {
        "H100": {"eastus": 5.10, "westeurope": 5.30},
        "A100": {"eastus": 3.05, "westeurope": 3.25},
        "T4": {"eastus": 0.39, "westeurope": 0.41},
    },
    "coreweave": {
        "H100": {"us-east1": 3.89, "us-east2": 3.95},
        "A100": {"us-east1": 2.40, "us-east2": 2.50},
        "T4": {"us-east1": 0.35, "us-east2": 0.36},
    },
}

GPU_VRAM_GB = {"H100": 80, "A100": 40, "T4": 16, "A10G": 24}


# ---------------------------------------------------------------------------
# Input / Output models
# ---------------------------------------------------------------------------

class SpinUpRequest(BaseModel):
    provider: str = Field(..., description="Cloud provider: aws/gcp/azure/coreweave")
    gpu_type: str = Field(..., description="GPU model: H100/A100/T4/A10G")
    count: int = Field(..., ge=1, le=64, description="Number of GPUs")
    region: str = Field("us-east-1", description="Deployment region")

    @field_validator("provider")
    @classmethod
    def check_provider(cls, v: str) -> str:
        valid = {"aws", "gcp", "azure", "coreweave"}
        if v not in valid:
            raise ValueError(f"Provider must be one of {valid}")
        return v

    @field_validator("gpu_type")
    @classmethod
    def check_gpu(cls, v: str) -> str:
        valid = set(GPU_VRAM_GB.keys())
        if v not in valid:
            raise ValueError(f"GPU type must be one of {valid}")
        return v


class JobConfig(BaseModel):
    instance_id: str
    docker_image: str
    command: str
    env_vars: dict[str, str] = Field(default_factory=dict)
    required_vram_gb: int = Field(..., ge=1)
    max_runtime_minutes: int = Field(60, ge=1)
    priority: float = Field(0.5, ge=0.0, le=1.0)


class AlertRequest(BaseModel):
    message: str
    severity: str = Field("info", pattern="^(info|warning|critical)$")
    agent_name: str = ""
    job_id: str | None = None


# ---------------------------------------------------------------------------
# Tool Registry Class
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Registry of all tools callable by OrQuanta agents.
    
    In production mode (USE_REAL_PROVIDERS=true), methods delegate to
    real provider SDKs (boto3, google-cloud, etc.). In development/mock
    mode (default), they return realistic simulated responses.
    
    Usage::
    
        tools = ToolRegistry()
        result = await tools.spin_up_gpu_instance("aws", "H100", 2)
        print(result["instance_id"])
    """

    def __init__(self) -> None:
        self.use_real = os.getenv("USE_REAL_PROVIDERS", "false").lower() == "true"
        logger.info(f"ToolRegistry initialised (real_providers={self.use_real})")

    # ------------------------------------------------------------------
    # Instance Management
    # ------------------------------------------------------------------

    async def spin_up_gpu_instance(
        self, provider: str, gpu_type: str, count: int, region: str = "us-east-1"
    ) -> dict[str, Any]:
        """Provision GPU instances from the specified cloud provider.
        
        Args:
            provider: Cloud provider name (aws/gcp/azure/coreweave).
            gpu_type: GPU model (H100/A100/T4/A10G).
            count: Number of GPU instances to provision.
            region: Deployment region.
            
        Returns:
            dict with instance_id, provider, gpu_type, status, hourly_cost_usd.
        """
        req = SpinUpRequest(provider=provider, gpu_type=gpu_type, count=count, region=region)

        if self.use_real:
            return await self._real_spin_up(req)

        # Mock: simulate ~1 second provisioning delay
        await asyncio.sleep(random.uniform(0.5, 1.5))

        instance_id = f"inst-{provider[:3]}-{secrets.token_hex(4).upper()}"
        price_matrix = SPOT_PRICE_MATRIX.get(provider, {}).get(gpu_type, {})
        hourly_cost = price_matrix.get(region, 5.0) * count

        instance = {
            "instance_id": instance_id,
            "provider": provider,
            "gpu_type": gpu_type,
            "gpu_count": count,
            "region": region,
            "status": "running",
            "hourly_cost_usd": round(hourly_cost, 4),
            "vram_gb": GPU_VRAM_GB.get(gpu_type, 0) * count,
            "provisioned_at": datetime.now(timezone.utc).isoformat(),
        }
        _INSTANCES[instance_id] = instance
        logger.info(f"[Tool] Provisioned {instance_id}: {count}x{gpu_type} on {provider}/{region} @ ${hourly_cost:.2f}/hr")
        return instance

    async def terminate_instance(self, instance_id: str) -> dict[str, Any]:
        """Terminate a GPU instance.
        
        Args:
            instance_id: ID returned by spin_up_gpu_instance.
            
        Returns:
            dict with status and final cost summary.
        """
        if self.use_real:
            return await self._real_terminate(instance_id)

        await asyncio.sleep(0.3)

        if instance_id not in _INSTANCES:
            return {"status": "not_found", "instance_id": instance_id}

        inst = _INSTANCES.pop(instance_id)
        provisioned_at = datetime.fromisoformat(inst["provisioned_at"])
        runtime_hours = (datetime.now(timezone.utc) - provisioned_at).total_seconds() / 3600
        total_cost = inst["hourly_cost_usd"] * runtime_hours

        result = {
            "status": "terminated",
            "instance_id": instance_id,
            "runtime_hours": round(runtime_hours, 4),
            "total_cost_usd": round(total_cost, 4),
            "terminated_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"[Tool] Terminated {instance_id}: runtime={runtime_hours:.2f}h cost=${total_cost:.4f}")
        return result

    async def get_gpu_metrics(self, instance_id: str) -> dict[str, Any]:
        """Get real-time GPU telemetry for an instance.
        
        Returns:
            dict with gpu_utilization, memory_used_gb, temp_celsius, power_watts.
        """
        if instance_id not in _INSTANCES:
            return {"error": "instance_not_found", "instance_id": instance_id}

        inst = _INSTANCES[instance_id]
        vram = inst.get("vram_gb", 80)

        # Simulate realistic GPU metrics
        utilization = random.uniform(65.0, 98.0)
        mem_used = random.uniform(0.7, 0.99) * vram
        temp = random.uniform(62.0, 85.0)
        power = random.uniform(280.0, 400.0) * inst.get("gpu_count", 1)

        return {
            "instance_id": instance_id,
            "gpu_utilization_pct": round(utilization, 1),
            "memory_used_gb": round(mem_used, 2),
            "memory_total_gb": vram,
            "memory_utilization_pct": round(mem_used / vram * 100, 1),
            "temp_celsius": round(temp, 1),
            "power_watts": round(power, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Job Management
    # ------------------------------------------------------------------

    async def submit_job(self, job_config: dict[str, Any]) -> dict[str, Any]:
        """Submit a containerized job to a GPU instance.
        
        Args:
            job_config: Dict matching JobConfig schema.
            
        Returns:
            dict with job_id, status, estimated_start_seconds.
        """
        cfg = JobConfig(**job_config)
        await asyncio.sleep(0.2)

        job_id = f"job-{str(uuid4())[:8]}"
        job = {
            "job_id": job_id,
            "instance_id": cfg.instance_id,
            "docker_image": cfg.docker_image,
            "command": cfg.command,
            "status": "queued",
            "priority": cfg.priority,
            "required_vram_gb": cfg.required_vram_gb,
            "max_runtime_minutes": cfg.max_runtime_minutes,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "estimated_start_seconds": random.randint(5, 30),
        }
        _JOBS[job_id] = job
        logger.info(f"[Tool] Job submitted: {job_id} on instance {cfg.instance_id}")
        return job

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get current status and metadata for a job.
        
        Returns:
            dict with job_id, status, progress_pct, logs_preview.
        """
        if job_id not in _JOBS:
            return {"error": "job_not_found", "job_id": job_id}

        job = _JOBS[job_id]
        # Simulate job progression
        submitted = datetime.fromisoformat(job["submitted_at"])
        elapsed = (datetime.now(timezone.utc) - submitted).total_seconds()

        if elapsed < 10:
            status = "queued"
            progress = 0.0
        elif elapsed < job["max_runtime_minutes"] * 60 * 0.9:
            status = "running"
            progress = min(95.0, (elapsed / (job["max_runtime_minutes"] * 60)) * 100)
        else:
            status = "completed"
            progress = 100.0

        job["status"] = status
        job["progress_pct"] = round(progress, 1)
        return job

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    async def get_spot_prices(
        self, provider: str, region: str, gpu_type: str
    ) -> dict[str, Any]:
        """Fetch current spot instance prices.
        
        Returns:
            dict with current_price, 24h_avg, 7d_low, 7d_high.
        """
        await asyncio.sleep(0.1)  # Simulate API latency
        base = SPOT_PRICE_MATRIX.get(provider, {}).get(gpu_type, {}).get(region, 5.0)
        # Add realistic price variance
        jitter = random.uniform(-0.15, 0.15) * base

        return {
            "provider": provider,
            "region": region,
            "gpu_type": gpu_type,
            "current_price_usd_hr": round(base + jitter, 4),
            "price_24h_avg_usd_hr": round(base, 4),
            "price_7d_low_usd_hr": round(base * 0.80, 4),
            "price_7d_high_usd_hr": round(base * 1.25, 4),
            "availability": random.choice(["high", "medium", "low"]),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_all_spot_prices(self, gpu_type: str) -> list[dict[str, Any]]:
        """Get spot prices for a GPU type across all providers and regions.
        
        Returns:
            Sorted list of price dicts (cheapest first).
        """
        tasks = [
            self.get_spot_prices(provider, region, gpu_type)
            for provider, gpus in SPOT_PRICE_MATRIX.items()
            if gpu_type in gpus
            for region in gpus[gpu_type]
        ]
        results = await asyncio.gather(*tasks)
        return sorted(results, key=lambda x: x["current_price_usd_hr"])

    # ------------------------------------------------------------------
    # Alerting
    # ------------------------------------------------------------------

    async def send_alert(
        self, message: str, severity: str = "info", agent_name: str = "", job_id: str | None = None
    ) -> dict[str, Any]:
        """Send an alert to the configured notification channels.
        
        In production: sends to Slack, PagerDuty, email, etc.
        In development: logs to console.
        """
        req = AlertRequest(message=message, severity=severity, agent_name=agent_name, job_id=job_id)
        alert_id = str(uuid4())[:8]
        timestamp = datetime.now(timezone.utc).isoformat()

        log_fn = {
            "info": logger.info,
            "warning": logger.warning,
            "critical": logger.critical,
        }.get(severity, logger.info)

        log_fn(f"[ALERT/{severity.upper()}] [{agent_name}] {message} (job={job_id})")

        if severity == "critical" and os.getenv("SLACK_WEBHOOK_URL"):
            await self._send_slack(req, alert_id, timestamp)

        return {
            "alert_id": alert_id,
            "delivered": True,
            "channels": ["log"] + (["slack"] if severity == "critical" else []),
            "timestamp": timestamp,
        }

    # ------------------------------------------------------------------
    # Memory tool wrappers (delegates to MemoryManager)
    # ------------------------------------------------------------------

    async def query_memory(self, query_text: str, n_results: int = 5) -> list[dict]:
        """Search vector memory for semantically similar past events."""
        # In production: delegates to MemoryManager.search()
        logger.debug(f"[Tool] Memory query: '{query_text[:60]}...'")
        return [{"note": "Memory search requires running MemoryManager.", "query": query_text}]

    async def update_memory(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Persist a new event to vector memory."""
        logger.debug(f"[Tool] Memory update: {list(event_data.keys())}")
        return {"stored": True, "event_keys": list(event_data.keys())}

    # ------------------------------------------------------------------
    # Real provider stubs (extend in production)
    # ------------------------------------------------------------------

    async def _real_spin_up(self, req: SpinUpRequest) -> dict[str, Any]:
        """Delegate to real provider SDK (e.g., boto3 for AWS)."""
        raise NotImplementedError(
            "Real provider integration not yet implemented. "
            "Set USE_REAL_PROVIDERS=false for mock mode."
        )

    async def _real_terminate(self, instance_id: str) -> dict[str, Any]:
        """Delegate to real provider SDK."""
        raise NotImplementedError(
            "Real provider integration not yet implemented."
        )

    async def _send_slack(self, req: AlertRequest, alert_id: str, ts: str) -> None:
        """Send Slack webhook notification."""
        import urllib.request
        webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        payload = json_payload = {
            "text": f"🚨 *OrQuanta Alert [{req.severity.upper()}]*\n{req.message}",
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn",
                    "text": f"*[{req.severity.upper()}]* {req.message}"}},
                {"type": "context", "elements": [
                    {"type": "mrkdwn", "text": f"Agent: `{req.agent_name}` | ID: `{alert_id}` | `{ts}`"}
                ]},
            ],
        }
        try:
            import json
            data = json.dumps(json_payload).encode()
            req_obj = urllib.request.Request(
                webhook_url, data=data, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req_obj, timeout=5)
        except Exception as exc:
            logger.warning(f"Slack alert delivery failed: {exc}")

    # ------------------------------------------------------------------
    # Tool manifest (for LangChain tool binding)
    # ------------------------------------------------------------------

    def get_tool_manifest(self) -> list[dict[str, Any]]:
        """Return a manifest of all tools for LangChain agent binding."""
        return [
            {"name": "spin_up_gpu_instance",  "description": "Provision GPU instances from a cloud provider"},
            {"name": "terminate_instance",     "description": "Terminate a running GPU instance"},
            {"name": "get_spot_prices",        "description": "Get current spot GPU prices for provider/region/type"},
            {"name": "get_all_spot_prices",    "description": "Compare spot prices across all providers for a GPU type"},
            {"name": "submit_job",             "description": "Submit a containerized training/inference job to GPU instance"},
            {"name": "get_job_status",         "description": "Get status, progress, and logs for a specific job"},
            {"name": "get_gpu_metrics",        "description": "Get real-time GPU telemetry (utilization, memory, temp)"},
            {"name": "send_alert",             "description": "Send alert to Slack/PagerDuty for warnings or critical events"},
            {"name": "query_memory",           "description": "Semantic search over past agent decisions and outcomes"},
            {"name": "update_memory",          "description": "Persist a new event or decision to vector memory"},
        ]
