# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta vLLM Deployment Adapter — Phase 3D
=============================================
Manages vLLM and SGLang containerised inference deployments via the
Phase 2 Celery durable job engine.

SAFETY RULES:
- Never mark a deployment successful until the model is loaded AND
  the /health endpoint returns HTTP 200.
- Never report mock inference as real inference.
- Deployments are NEVER auto-approved; user must confirm cost estimate.
- GPU resources are cleaned up on failure, cancellation, or timeout.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("orquanta.inference.vllm_adapter")

# ---------------------------------------------------------------------------
# Deployment configuration
# ---------------------------------------------------------------------------

USE_REAL_PROVIDERS = os.getenv("USE_REAL_PROVIDERS", "false").lower() == "true"
VLLM_STARTUP_TIMEOUT_SECONDS = int(os.getenv("VLLM_STARTUP_TIMEOUT_SECONDS", "600"))  # 10 min
HEALTH_CHECK_INTERVAL_SECONDS = int(os.getenv("VLLM_HEALTH_CHECK_INTERVAL", "15"))
HEALTH_CHECK_RETRIES = int(os.getenv("VLLM_HEALTH_CHECK_RETRIES", "40"))  # 40 × 15s = 600s

# vLLM Docker image — pinned for reproducibility
VLLM_IMAGE = os.getenv("VLLM_DOCKER_IMAGE", "vllm/vllm-openai:v0.6.4")
SGLANG_IMAGE = os.getenv("SGLANG_DOCKER_IMAGE", "lmsysorg/sglang:v0.4.1-cu121")

# ---------------------------------------------------------------------------
# Deployment record
# ---------------------------------------------------------------------------

@dataclass
class DeploymentRecord:
    deployment_id: str
    model_id: str
    hf_id: str
    engine: str                     # vllm | sglang
    quantisation: str
    gpu_model: str
    gpu_count: int
    provider: str
    region: str
    status: str                     # pending | provisioning | starting | ready | failed | stopped
    instance_id: Optional[str] = None
    inference_endpoint: Optional[str] = None
    health_endpoint: Optional[str] = None
    api_key_prefix: Optional[str] = None    # First 8 chars only — full key delivered once
    hourly_rate_usd: Optional[float] = None
    deploy_job_id: Optional[str] = None     # Phase 2 Celery job ID
    failure_reason: Optional[str] = None
    created_at: Optional[str] = None
    ready_at: Optional[str] = None
    is_real: bool = False           # False if no real provider execution

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# In-memory store (Phase 3D — backed by DB in Phase 3F)
_DEPLOYMENTS: Dict[str, DeploymentRecord] = {}


# ---------------------------------------------------------------------------
# Engine startup scripts
# ---------------------------------------------------------------------------

def build_vllm_startup_command(
    hf_model_id: str,
    quantisation: str,
    gpu_count: int,
    max_model_len: Optional[int] = None,
    dtype: str = "auto",
    port: int = 8000,
) -> List[str]:
    """
    Build the vLLM server startup command.
    
    Returns a list of command arguments (safe, no shell injection).
    """
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", hf_model_id,
        "--host", "0.0.0.0",
        "--port", str(port),
        "--dtype", dtype,
        "--gpu-memory-utilization", "0.90",
        "--trust-remote-code",
    ]

    # Quantisation
    if quantisation == "int8":
        cmd += ["--quantization", "bitsandbytes", "--load-format", "bitsandbytes"]
    elif quantisation in ("int4", "awq"):
        cmd += ["--quantization", "awq"]
    elif quantisation == "gptq":
        cmd += ["--quantization", "gptq"]

    # Multi-GPU tensor parallelism
    if gpu_count > 1:
        cmd += ["--tensor-parallel-size", str(gpu_count)]

    # Context length cap
    if max_model_len:
        cmd += ["--max-model-len", str(max_model_len)]

    return cmd


def build_sglang_startup_command(
    hf_model_id: str,
    gpu_count: int,
    quantisation: str,
    port: int = 30000,
) -> List[str]:
    """Build the SGLang server startup command."""
    cmd = [
        "python", "-m", "sglang.launch_server",
        "--model-path", hf_model_id,
        "--host", "0.0.0.0",
        "--port", str(port),
        "--trust-remote-code",
    ]
    if gpu_count > 1:
        cmd += ["--tp", str(gpu_count)]
    if quantisation in ("int4", "awq"):
        cmd += ["--quantization", "awq"]
    elif quantisation == "gptq":
        cmd += ["--quantization", "gptq"]
    return cmd


# ---------------------------------------------------------------------------
# Health checking
# ---------------------------------------------------------------------------

async def wait_for_inference_ready(
    endpoint: str,
    model_id: str,
    timeout_seconds: int = VLLM_STARTUP_TIMEOUT_SECONDS,
    interval_seconds: int = HEALTH_CHECK_INTERVAL_SECONDS,
) -> bool:
    """
    Poll the /health endpoint until the model is loaded and serving.

    Returns True only if the model responds with HTTP 200 on /health.
    Returns False after timeout.

    NEVER marks a deployment ready on a non-200 response.
    """
    health_url = f"{endpoint}/health"
    deadline = time.time() + timeout_seconds
    attempts = 0

    logger.info("[vllm] Waiting for inference ready at %s (timeout=%ds)", health_url, timeout_seconds)

    while time.time() < deadline:
        attempts += 1
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(health_url)
                if resp.status_code == 200:
                    logger.info("[vllm] Model ready after %d attempts (%.0fs)", attempts, time.time() - (deadline - timeout_seconds))
                    return True
                else:
                    logger.debug("[vllm] health check attempt %d: HTTP %d", attempts, resp.status_code)
        except (httpx.ConnectError, httpx.ReadTimeout):
            logger.debug("[vllm] health check attempt %d: not reachable yet", attempts)
        except Exception as e:
            logger.warning("[vllm] health check attempt %d unexpected error: %s", attempts, e)

        import asyncio
        await asyncio.sleep(interval_seconds)

    logger.error("[vllm] Deployment did NOT become ready within %ds for model=%s", timeout_seconds, model_id)
    return False


# ---------------------------------------------------------------------------
# Deployment workflow steps (called by Celery tasks in deploy_tasks.py)
# ---------------------------------------------------------------------------

def build_deployment_spec(
    deployment_id: str,
    model_id: str,
    hf_id: str,
    engine: str,
    quantisation: str,
    gpu_model: str,
    gpu_count: int,
    provider: str,
    region: str,
    hourly_rate_usd: float,
    max_model_len: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build a provider-agnostic deployment specification.
    
    This spec is passed to the provider adapter for GPU provisioning.
    Returns a serialisable dict (safe for Celery task arguments).
    """
    port = 8000 if engine == "vllm" else 30000

    if engine == "vllm":
        startup_cmd = build_vllm_startup_command(
            hf_model_id=hf_id,
            quantisation=quantisation,
            gpu_count=gpu_count,
            max_model_len=max_model_len,
        )
        docker_image = VLLM_IMAGE
    elif engine == "sglang":
        startup_cmd = build_sglang_startup_command(
            hf_model_id=hf_id,
            gpu_count=gpu_count,
            quantisation=quantisation,
        )
        docker_image = SGLANG_IMAGE
    else:
        raise ValueError(f"Unsupported inference engine: {engine}")

    return {
        "deployment_id": deployment_id,
        "model_id": model_id,
        "hf_id": hf_id,
        "engine": engine,
        "quantisation": quantisation,
        "gpu_model": gpu_model,
        "gpu_count": gpu_count,
        "provider": provider,
        "region": region,
        "hourly_rate_usd": hourly_rate_usd,
        "docker_image": docker_image,
        "startup_command": startup_cmd,
        "port": port,
        "health_path": "/health",
        "ready_path": "/v1/models",
        "startup_timeout_seconds": VLLM_STARTUP_TIMEOUT_SECONDS,
        "is_real": USE_REAL_PROVIDERS,
    }


def mock_deploy_response(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a clearly-labelled mock deployment response for testing.
    Never used in production.
    """
    return {
        "instance_id": "mock-instance-00000000",
        "inference_endpoint": "http://mock-endpoint:8000",
        "health_endpoint": "http://mock-endpoint:8000/health",
        "is_real": False,
        "note": (
            "[MOCK — USE_REAL_PROVIDERS=false] "
            f"Deployment spec built for model '{spec['model_id']}' on {spec['gpu_count']}× {spec['gpu_model']} "
            f"using {spec['engine']} + {spec['quantisation']}. "
            "Set USE_REAL_PROVIDERS=true and configure RUNPOD_API_KEY to provision real GPU instances."
        ),
    }
