"""
OrQuanta Agentic v1.0 — Lambda Labs Cloud Provider
===================================================

Real integration with Lambda Labs GPU Cloud REST API.
API docs: https://cloud.lambdalabs.com/api/v1/

Supported GPU types:
  gpu_1x_a10        — A10  24GB  ~$0.75/hr
  gpu_1x_a100       — A100 80GB  ~$1.99/hr
  gpu_1x_h100_pcie  — H100 80GB  ~$2.99/hr
  gpu_8x_a100       — 8xA100     ~$14.32/hr
  gpu_8x_h100_sxm5  — 8xH100 SXM ~$24.80/hr

Auth: Bearer token via LAMBDA_LABS_API_KEY env var.

Usage:
    from v4.providers.lambda_labs_provider import LambdaLabsProvider
    provider = LambdaLabsProvider()
    if await provider.is_available():
        price = await provider.get_gpu_price("gpu_1x_a100", "us-tx-3")
        instance = await provider.provision_instance(config)
"""
from __future__ import annotations

import logging
import os
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from v4.providers.base_provider import BaseGPUProvider, InstanceConfig, ProvisionedInstance, GpuMetrics, CommandResult

logger = logging.getLogger("orquanta.providers.lambda_labs")

LAMBDA_API_BASE = "https://cloud.lambdalabs.com/api/v1"
LAMBDA_API_KEY  = os.getenv("LAMBDA_LABS_API_KEY", "")

# GPU type → friendly name mapping
GPU_DISPLAY_NAMES = {
    "gpu_1x_a10":        "NVIDIA A10 (24GB)",
    "gpu_1x_a100":       "NVIDIA A100 (80GB)",
    "gpu_1x_a100_sxm4":  "NVIDIA A100 SXM4 (80GB)",
    "gpu_1x_h100_pcie":  "NVIDIA H100 PCIe (80GB)",
    "gpu_1x_h100_sxm5":  "NVIDIA H100 SXM5 (80GB)",
    "gpu_2x_a100":       "2× NVIDIA A100 (80GB)",
    "gpu_4x_a100":       "4× NVIDIA A100 (80GB)",
    "gpu_8x_a100":       "8× NVIDIA A100 (80GB)",
    "gpu_8x_h100_sxm5":  "8× NVIDIA H100 SXM5 (80GB)",
    "gpu_1x_a6000":      "NVIDIA A6000 (48GB)",
    "gpu_2x_a6000":      "2× NVIDIA A6000 (48GB)",
    "gpu_4x_a6000":      "4× NVIDIA A6000 (48GB)",
}

# Region codes
REGIONS = ["us-tx-3", "us-west-3", "us-east-1", "europe-west-1", "asia-south-1"]


class LambdaLabsProvider(BaseGPUProvider):
    """
    Lambda Labs GPU Cloud provider implementation.

    Implements the BaseGPUProvider interface using the Lambda Labs
    REST API v1. Falls back gracefully when API key is not configured
    (returns mock/demo responses).
    """

    provider_name = "lambda"
    display_name  = "Lambda Labs"

    def __init__(self) -> None:
        self._key = LAMBDA_API_KEY
        self._client: httpx.AsyncClient | None = None
        self._instance_cache: dict[str, dict] = {}   # instance_id → meta
        self._price_cache:    dict[str, float] = {}  # "type:region" → $/hr
        self._price_cache_ts: float = 0.0

    # ─── HTTP client ──────────────────────────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            self._client = httpx.AsyncClient(
                base_url=LAMBDA_API_BASE,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with self._get_client() as client:
            resp = await client.get(path, params=params or {})
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, payload: dict) -> dict:
        async with self._get_client() as client:
            resp = await client.post(path, json=payload)
            if resp.status_code == 400:
                body = resp.json()
                raise LambdaLabsError(f"Bad request: {body.get('error', {}).get('message', body)}")
            resp.raise_for_status()
            return resp.json()

    # ─── BaseGPUProvider interface ────────────────────────────────────────────

    async def is_available(self) -> bool:
        """Return True if the Lambda Labs API is reachable and key is valid."""
        if not self._key:
            logger.warning("[LambdaLabs] LAMBDA_LABS_API_KEY not set — using mock mode")
            return False
        try:
            await self._get("/instance-types")
            logger.info("[LambdaLabs] API healthy ✓")
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                logger.error("[LambdaLabs] Invalid API key (401)")
            else:
                logger.warning(f"[LambdaLabs] API check failed: {exc}")
            return False
        except Exception as exc:
            logger.warning(f"[LambdaLabs] is_available check failed: {exc}")
            return False

    async def get_instance_types(self) -> list[dict[str, Any]]:
        """
        List all available GPU instance types with real-time pricing.
        Returns list of dicts with: name, gpu_name, gpu_memory_gb, vcpus,
        memory_gib, storage_gib, price_cents_per_hour, regions_available.
        """
        import time
        if time.monotonic() - self._price_cache_ts < 300 and self._price_cache:
            # Return cached (5-minute TTL)
            return self._build_type_list_from_cache()

        if not self._key:
            return self._mock_instance_types()

        try:
            data = await self._get("/instance-types")
            types = []
            for name, info in data.get("data", {}).items():
                specs = info.get("instance_type", {})
                specs["name"] = name
                regions_with_capacity = [
                    r["name"]
                    for r in info.get("regions_with_capacity_available", [])
                ]
                specs["regions_available"] = regions_with_capacity
                specs["available"] = len(regions_with_capacity) > 0
                display = GPU_DISPLAY_NAMES.get(name, specs.get("gpu_description", name))
                specs["display_name"] = display
                price_cents = specs.get("price_cents_per_hour", 0)
                specs["price_usd_per_hour"] = price_cents / 100.0
                # Cache price
                for region in regions_with_capacity:
                    self._price_cache[f"{name}:{region}"] = price_cents / 100.0
                types.append(specs)

            self._price_cache_ts = time.monotonic()
            types.sort(key=lambda x: x.get("price_cents_per_hour", 999999))
            logger.info(f"[LambdaLabs] Fetched {len(types)} instance types")
            return types
        except Exception as exc:
            logger.warning(f"[LambdaLabs] get_instance_types failed: {exc}")
            return self._mock_instance_types()

    async def get_gpu_price(self, gpu_type: str, region: str) -> float:
        """Return USD per hour for gpu_type in region. 0.0 if unavailable."""
        cache_key = f"{gpu_type}:{region}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        types = await self.get_instance_types()
        for t in types:
            if t["name"] == gpu_type and region in t.get("regions_available", []):
                price = t.get("price_usd_per_hour", 0.0)
                self._price_cache[cache_key] = price
                return price
        return 0.0  # not available

    async def list_running_instances(self) -> list[dict[str, Any]]:
        """Return all currently running instances on this account."""
        if not self._key:
            return []
        try:
            data = await self._get("/instances")
            instances = data.get("data", [])
            logger.debug(f"[LambdaLabs] {len(instances)} running instances")
            return instances
        except Exception as exc:
            logger.warning(f"[LambdaLabs] list_running_instances failed: {exc}")
            return []

    async def provision_instance(self, config: InstanceConfig) -> ProvisionedInstance:
        """
        Launch a new GPU instance. Returns ProvisionedInstance.
        If API unavailable, returns a mock instance for demo mode.
        """
        if not self._key:
            return self._mock_provision(config)

        # Find an available region for this GPU type
        types = await self.get_instance_types()
        target_type = None
        chosen_region = config.region or ""

        for t in types:
            if t["name"] == config.gpu_type:
                if chosen_region and chosen_region in t.get("regions_available", []):
                    target_type = t
                    break
                elif not chosen_region and t.get("regions_available"):
                    chosen_region = t["regions_available"][0]
                    target_type = t
                    break

        if not target_type:
            raise LambdaLabsError(
                f"GPU type '{config.gpu_type}' not available in region '{chosen_region}'. "
                f"Check https://cloud.lambdalabs.com/instances for current availability."
            )

        # Get SSH key
        ssh_key_name = await self._get_or_create_ssh_key(config.ssh_key_name)

        payload = {
            "region_name": chosen_region,
            "instance_type_name": config.gpu_type,
            "ssh_key_names": [ssh_key_name],
            "quantity": 1,
        }
        if config.name:
            payload["name"] = config.name
        if config.user_data:
            payload["user_data"] = config.user_data

        try:
            logger.info(f"[LambdaLabs] Launching {config.gpu_type} in {chosen_region}...")
            resp = await self._post("/instance-operations/launch", payload)
            instance_ids = resp.get("data", {}).get("instance_ids", [])

            if not instance_ids:
                raise LambdaLabsError("Launch returned no instance IDs")

            instance_id = instance_ids[0]
            price = target_type.get("price_usd_per_hour", 0.0)

            logger.info(f"[LambdaLabs] Instance {instance_id} launching | ${price:.2f}/hr")

            # Wait for instance to get an IP (poll up to 90s)
            ip_address = await self._wait_for_ip(instance_id, timeout_s=90)

            provisioned = ProvisionedInstance(
                instance_id=instance_id,
                provider="lambda",
                gpu_type=config.gpu_type,
                gpu_count=config.gpu_count,
                region=chosen_region,
                ip_address=ip_address,
                status="running",
                cost_per_hour=price,
                started_at=datetime.now(timezone.utc).isoformat(),
                ssh_user="ubuntu",
                ssh_key_name=ssh_key_name,
            )
            self._instance_cache[instance_id] = provisioned.__dict__
            return provisioned

        except LambdaLabsError:
            raise
        except Exception as exc:
            raise LambdaLabsError(f"Provision failed: {exc}") from exc

    async def terminate_instance(self, instance_id: str) -> bool:
        """Terminate an instance. Returns True on success."""
        if not self._key:
            logger.info(f"[LambdaLabs] Mock terminate {instance_id}")
            return True

        try:
            await self._post(
                "/instance-operations/terminate",
                {"instance_ids": [instance_id]},
            )
            self._instance_cache.pop(instance_id, None)
            logger.info(f"[LambdaLabs] Terminated {instance_id}")
            return True
        except Exception as exc:
            logger.error(f"[LambdaLabs] Terminate {instance_id} failed: {exc}")
            return False

    async def get_instance_status(self, instance_id: str) -> dict[str, Any]:
        """Fetch current instance status from the API."""
        if not self._key:
            return {"id": instance_id, "status": "running"}
        try:
            data = await self._get(f"/instances/{instance_id}")
            return data.get("data", {})
        except Exception as exc:
            logger.warning(f"[LambdaLabs] get_instance_status {instance_id}: {exc}")
            return {"id": instance_id, "status": "unknown"}

    async def get_metrics(self, instance_id: str) -> GpuMetrics:
        """
        Lambda Labs doesn't expose GPU metrics via API.
        Metrics must be fetched via SSH from nvidia-smi.
        Returns an empty metrics object — caller should use SSH polling.
        """
        return GpuMetrics(
            instance_id=instance_id,
            gpu_utilization_pct=0.0,
            memory_utilization_pct=0.0,
            temp_celsius=0.0,
            power_watts=0.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="lambda_api",
            note="Lambda Labs API doesn't expose GPU metrics. Use SSH + nvidia-smi.",
        )

    async def execute_command(self, instance_id: str, command: str) -> CommandResult:
        """
        Execute a command on the instance via SSH.
        Requires: instance has IP, SSH key configured.
        """
        info = self._instance_cache.get(instance_id, {})
        ip = info.get("ip_address", "")
        ssh_key = info.get("ssh_key_name", "orquanta-default")

        if not ip:
            # Fetch fresh
            status = await self.get_instance_status(instance_id)
            ip = status.get("ip", "")

        if not ip:
            return CommandResult(
                instance_id=instance_id,
                command=command,
                stdout="",
                stderr="No IP address available for SSH",
                exit_code=1,
            )

        # Use asyncio subprocess for SSH
        ssh_cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=15",
            "-i", f"~/.ssh/{ssh_key}",
            f"ubuntu@{ip}",
            command,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            return CommandResult(
                instance_id=instance_id,
                command=command,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            return CommandResult(instance_id=instance_id, command=command,
                                  stdout="", stderr="SSH command timed out", exit_code=1)
        except Exception as exc:
            return CommandResult(instance_id=instance_id, command=command,
                                  stdout="", stderr=str(exc), exit_code=1)

    # ─── SSH Key management ───────────────────────────────────────────────────

    async def list_ssh_keys(self) -> list[dict]:
        """Return all SSH keys registered on this account."""
        try:
            data = await self._get("/ssh-keys")
            return data.get("data", [])
        except Exception as exc:
            logger.warning(f"[LambdaLabs] list_ssh_keys: {exc}")
            return []

    async def _get_or_create_ssh_key(self, preferred_name: str | None = None) -> str:
        """Return name of an available SSH key, or raise if none configured."""
        keys = await self.list_ssh_keys()
        if keys:
            # Use first available, or preferred if specified
            if preferred_name:
                for k in keys:
                    if k.get("name") == preferred_name:
                        return preferred_name
            return keys[0]["name"]
        # No keys — user needs to add one
        raise LambdaLabsError(
            "No SSH keys found on Lambda Labs account. "
            "Add an SSH key at https://cloud.lambdalabs.com/ssh-keys "
            "then set LAMBDA_LABS_SSH_KEY_NAME in .env"
        )

    # ─── Polling helpers ──────────────────────────────────────────────────────

    async def _wait_for_ip(self, instance_id: str, timeout_s: int = 90) -> str:
        """Poll until instance has an IP address or timeout."""
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                status = await self.get_instance_status(instance_id)
                ip = status.get("ip")
                if ip:
                    logger.info(f"[LambdaLabs] Instance {instance_id} IP: {ip}")
                    return ip
                inst_status = status.get("status", "")
                if inst_status == "terminated":
                    raise LambdaLabsError(f"Instance {instance_id} terminated unexpectedly")
            except LambdaLabsError:
                raise
            except Exception as exc:
                logger.debug(f"[LambdaLabs] Waiting for IP: {exc}")
            await asyncio.sleep(5)
        logger.warning(f"[LambdaLabs] Timeout waiting for IP on {instance_id}")
        return ""  # Return empty; caller can retry

    # ─── Mock / Demo helpers ──────────────────────────────────────────────────

    def _mock_instance_types(self) -> list[dict]:
        """Return realistic mock instance types when API key not set."""
        return [
            {"name": "gpu_1x_a10",       "display_name": "NVIDIA A10 (24GB)",
             "price_usd_per_hour": 0.75,  "price_cents_per_hour": 75,
             "vcpus": 30, "memory_gib": 200, "storage_gib": 1400,
             "regions_available": ["us-tx-3", "us-west-3"], "available": True},
            {"name": "gpu_1x_a100",      "display_name": "NVIDIA A100 (80GB)",
             "price_usd_per_hour": 1.99,  "price_cents_per_hour": 199,
             "vcpus": 30, "memory_gib": 200, "storage_gib": 1400,
             "regions_available": ["us-tx-3"], "available": True},
            {"name": "gpu_1x_h100_pcie", "display_name": "NVIDIA H100 PCIe (80GB)",
             "price_usd_per_hour": 2.99,  "price_cents_per_hour": 299,
             "vcpus": 26, "memory_gib": 200, "storage_gib": 512,
             "regions_available": ["us-east-1"], "available": True},
            {"name": "gpu_8x_a100",      "display_name": "8× NVIDIA A100 (80GB)",
             "price_usd_per_hour": 14.32, "price_cents_per_hour": 1432,
             "vcpus": 124, "memory_gib": 1800, "storage_gib": 12300,
             "regions_available": ["us-tx-3"], "available": True},
            {"name": "gpu_8x_h100_sxm5", "display_name": "8× NVIDIA H100 SXM5 (80GB)",
             "price_usd_per_hour": 24.80, "price_cents_per_hour": 2480,
             "vcpus": 208, "memory_gib": 1800, "storage_gib": 22100,
             "regions_available": [], "available": False},
        ]

    def _mock_provision(self, config: InstanceConfig) -> ProvisionedInstance:
        """Return a mock ProvisionedInstance for demo mode."""
        import uuid
        instance_id = f"inst_{uuid.uuid4().hex[:12]}"
        prices = {
            "gpu_1x_a10": 0.75, "gpu_1x_a100": 1.99,
            "gpu_1x_h100_pcie": 2.99, "gpu_8x_a100": 14.32,
        }
        price = prices.get(config.gpu_type, 1.99)
        logger.info(f"[LambdaLabs] DEMO: Provisioned mock {config.gpu_type} @ ${price}/hr")
        p = ProvisionedInstance(
            instance_id=instance_id,
            provider="lambda",
            gpu_type=config.gpu_type,
            gpu_count=config.gpu_count,
            region=config.region or "us-tx-3",
            ip_address=f"10.{__import__('random').randint(1,254)}.{__import__('random').randint(1,254)}.{__import__('random').randint(1,254)}",
            status="running",
            cost_per_hour=price,
            started_at=datetime.now(timezone.utc).isoformat(),
            ssh_user="ubuntu",
            ssh_key_name="orquanta-demo",
        )
        self._instance_cache[instance_id] = p.__dict__
        return p

    def _build_type_list_from_cache(self) -> list[dict]:
        return []  # Rebuild from cache in a real impl


class LambdaLabsError(Exception):
    """Lambda Labs API error."""


# ─── Register with ProviderRouter ─────────────────────────────────────────────

def register(router_registry: dict) -> None:
    """Called by ProviderRouter to register this provider."""
    router_registry["lambda"] = LambdaLabsProvider
