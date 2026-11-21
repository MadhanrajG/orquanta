# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Unified Inference Engine Interface — Phase 3E
=======================================================
Standardises vLLM and SGLang behind one interface.
DeploymentLifecycle state machine enforces correct readiness checks.

SAFETY: A deployment cannot be marked READY merely because a container
has started. The model must load AND pass an inference health check.
"""
from __future__ import annotations

import abc
import asyncio
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("orquanta.inference.engine")

USE_REAL_PROVIDERS = os.getenv("USE_REAL_PROVIDERS", "false").lower() == "true"
VLLM_IMAGE   = os.getenv("VLLM_DOCKER_IMAGE",   "vllm/vllm-openai:v0.6.4")
SGLANG_IMAGE = os.getenv("SGLANG_DOCKER_IMAGE",  "lmsysorg/sglang:v0.4.1-cu121")
STARTUP_TIMEOUT  = int(os.getenv("VLLM_STARTUP_TIMEOUT_SECONDS", "600"))
HEALTH_INTERVAL  = int(os.getenv("VLLM_HEALTH_CHECK_INTERVAL",   "15"))


# ---------------------------------------------------------------------------
# Deployment lifecycle state machine
# ---------------------------------------------------------------------------

class DeploymentState(str, Enum):
    PENDING        = "pending"
    PROVISIONING   = "provisioning"
    STARTING       = "starting"
    MODEL_LOADING  = "model_loading"
    HEALTH_CHECK   = "health_check"
    READY          = "ready"
    STOPPING       = "stopping"
    STOPPED        = "stopped"
    FAILED         = "failed"

VALID_LIFECYCLE_TRANSITIONS: Dict[DeploymentState, List[DeploymentState]] = {
    DeploymentState.PENDING:       [DeploymentState.PROVISIONING, DeploymentState.FAILED],
    DeploymentState.PROVISIONING:  [DeploymentState.STARTING,      DeploymentState.FAILED],
    DeploymentState.STARTING:      [DeploymentState.MODEL_LOADING,  DeploymentState.FAILED],
    DeploymentState.MODEL_LOADING: [DeploymentState.HEALTH_CHECK,   DeploymentState.FAILED],
    DeploymentState.HEALTH_CHECK:  [DeploymentState.READY,          DeploymentState.FAILED],
    DeploymentState.READY:         [DeploymentState.STOPPING,       DeploymentState.FAILED],
    DeploymentState.STOPPING:      [DeploymentState.STOPPED,        DeploymentState.FAILED],
    DeploymentState.STOPPED:       [],
    DeploymentState.FAILED:        [],
}


@dataclass
class LifecycleEvent:
    state: str
    timestamp: str
    detail: str = ""
    is_real: bool = False


@dataclass
class DeploymentLifecycle:
    deployment_id: str
    model_id: str
    engine: str
    state: DeploymentState = DeploymentState.PENDING
    events: List[LifecycleEvent] = field(default_factory=list)
    failure_reason: Optional[str] = None
    inference_endpoint: Optional[str] = None
    is_real: bool = False

    def transition(self, new_state: DeploymentState, detail: str = "") -> None:
        allowed = VALID_LIFECYCLE_TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition {self.state} → {new_state} for deployment {self.deployment_id}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        self.state = new_state
        self.events.append(LifecycleEvent(
            state=new_state.value,
            timestamp=_now(),
            detail=detail,
            is_real=self.is_real,
        ))
        logger.info("[lifecycle] %s → %s  %s", self.deployment_id, new_state.value, detail)

    def fail(self, reason: str) -> None:
        self.failure_reason = reason
        if self.state not in (DeploymentState.STOPPED, DeploymentState.FAILED):
            try:
                self.transition(DeploymentState.FAILED, reason)
            except ValueError:
                # Already in terminal state
                pass

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Abstract engine interface
# ---------------------------------------------------------------------------

class InferenceEngine(abc.ABC):
    """Base class for all inference engine adapters."""

    name: str = "base"

    @abc.abstractmethod
    def build_startup_command(
        self,
        hf_model_id: str,
        quantisation: str,
        gpu_count: int,
        port: int,
        max_model_len: Optional[int] = None,
    ) -> List[str]:
        """Return the container startup command as a list of args."""

    @abc.abstractmethod
    def get_docker_image(self) -> str:
        """Return the pinned Docker image for this engine."""

    @abc.abstractmethod
    def get_health_path(self) -> str:
        """Return the HTTP path for the health check endpoint."""

    @abc.abstractmethod
    def get_models_path(self) -> str:
        """Return the HTTP path for listing loaded models."""

    def get_port(self) -> int:
        return 8000

    async def health_check(self, endpoint: str) -> bool:
        """HTTP GET {endpoint}{health_path} → True if 200."""
        url = f"{endpoint}{self.get_health_path()}"
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(url)
                return r.status_code == 200
        except Exception as e:
            logger.debug("[engine:%s] health_check failed: %s", self.name, e)
            return False

    async def verify_model_loaded(self, endpoint: str, expected_model_id: str) -> bool:
        """
        Verify the expected model appears in the /v1/models response.
        NEVER marks ready on health check alone.
        """
        url = f"{endpoint}{self.get_models_path()}"
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(url)
                if r.status_code != 200:
                    return False
                data = r.json()
                models = data.get("data", [])
                loaded_ids = [m.get("id", "") for m in models]
                # Accept partial match (hf_id may be path-shortened)
                return any(
                    expected_model_id in m_id or m_id in expected_model_id
                    for m_id in loaded_ids
                )
        except Exception as e:
            logger.debug("[engine:%s] verify_model_loaded failed: %s", self.name, e)
            return False

    async def run_warm_up_inference(self, endpoint: str, model_id: str) -> bool:
        """
        Send a minimal inference request to confirm the model answers.
        Returns True only if a valid response is received.
        """
        url = f"{endpoint}/v1/chat/completions"
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5,
            "temperature": 0.0,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(url, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    return bool(data.get("choices"))
                return False
        except Exception as e:
            logger.debug("[engine:%s] warm_up_inference failed: %s", self.name, e)
            return False

    async def wait_for_ready(
        self,
        lifecycle: DeploymentLifecycle,
        endpoint: str,
        model_id: str,
        timeout: int = STARTUP_TIMEOUT,
        interval: int = HEALTH_INTERVAL,
    ) -> bool:
        """
        Poll until the model is loaded and passes inference check.
        Updates lifecycle state at each stage.
        Returns True only after full verification.

        Stages:
          1. STARTING      → container accepting connections
          2. MODEL_LOADING → health endpoint returns 200
          3. HEALTH_CHECK  → model appears in /v1/models + warm-up inference passes
          4. READY         → all checks passed
        """
        if not USE_REAL_PROVIDERS:
            # Mock path
            lifecycle.transition(DeploymentState.STARTING, "Mock engine starting")
            lifecycle.transition(DeploymentState.MODEL_LOADING, "Mock model loading")
            lifecycle.transition(DeploymentState.HEALTH_CHECK, "Mock health check")
            lifecycle.inference_endpoint = endpoint
            lifecycle.transition(DeploymentState.READY, "[MOCK] Model ready (USE_REAL_PROVIDERS=false)")
            logger.info("[engine:%s] Mock deployment marked ready (not real)", self.name)
            return True

        deadline = time.time() + timeout
        lifecycle.transition(DeploymentState.STARTING, f"Waiting for {endpoint} to accept connections")

        # Phase 1: health ping
        while time.time() < deadline:
            if await self.health_check(endpoint):
                break
            await asyncio.sleep(interval)
        else:
            lifecycle.fail(f"Timeout: health endpoint {endpoint}{self.get_health_path()} never returned 200 within {timeout}s")
            return False

        lifecycle.transition(DeploymentState.MODEL_LOADING, "Container healthy; waiting for model weights to load")

        # Phase 2: model load verification
        model_loaded = False
        while time.time() < deadline:
            if await self.verify_model_loaded(endpoint, model_id):
                model_loaded = True
                break
            await asyncio.sleep(interval)

        if not model_loaded:
            lifecycle.fail(f"Model '{model_id}' did not appear in /v1/models within {timeout}s")
            return False

        lifecycle.transition(DeploymentState.HEALTH_CHECK, "Model loaded; running warm-up inference check")

        # Phase 3: warm-up inference
        inference_ok = await self.run_warm_up_inference(endpoint, model_id)
        if not inference_ok:
            lifecycle.fail("Warm-up inference check failed — model loaded but not responding to requests")
            return False

        lifecycle.inference_endpoint = endpoint
        lifecycle.transition(DeploymentState.READY, f"Model '{model_id}' healthy and serving inference")
        logger.info("[engine:%s] Deployment %s READY at %s", self.name, lifecycle.deployment_id, endpoint)
        return True

    async def cleanup_resources(self, instance_id: str, provider: str) -> None:
        """Terminate container and release GPU. Logs all actions."""
        logger.info("[engine:%s] Cleaning up instance=%s provider=%s", self.name, instance_id, provider)
        # Real cleanup delegated to provider adapter; logged here
        if not USE_REAL_PROVIDERS:
            logger.info("[engine:%s] Mock cleanup — no real resources to release", self.name)
            return
        # Provider-specific teardown would go here
        logger.info("[engine:%s] Resource cleanup requested for %s/%s", self.name, provider, instance_id)


# ---------------------------------------------------------------------------
# vLLM engine implementation
# ---------------------------------------------------------------------------

class VLLMEngine(InferenceEngine):
    name = "vllm"

    def get_docker_image(self) -> str:
        return VLLM_IMAGE

    def get_health_path(self) -> str:
        return "/health"

    def get_models_path(self) -> str:
        return "/v1/models"

    def build_startup_command(
        self,
        hf_model_id: str,
        quantisation: str,
        gpu_count: int,
        port: int = 8000,
        max_model_len: Optional[int] = None,
    ) -> List[str]:
        cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", hf_model_id,
            "--host", "0.0.0.0",
            "--port", str(port),
            "--dtype", "auto",
            "--gpu-memory-utilization", "0.90",
            "--trust-remote-code",
            "--max-num-seqs", "256",
        ]
        quant_map = {"int8": "bitsandbytes", "awq": "awq", "gptq": "gptq"}
        if quantisation in quant_map:
            cmd += ["--quantization", quant_map[quantisation]]
            if quantisation == "int8":
                cmd += ["--load-format", "bitsandbytes"]
        if gpu_count > 1:
            cmd += ["--tensor-parallel-size", str(gpu_count)]
        if max_model_len:
            cmd += ["--max-model-len", str(max_model_len)]
        return cmd


# ---------------------------------------------------------------------------
# SGLang engine implementation
# ---------------------------------------------------------------------------

class SGLangEngine(InferenceEngine):
    name = "sglang"

    def get_docker_image(self) -> str:
        return SGLANG_IMAGE

    def get_health_path(self) -> str:
        return "/health"

    def get_models_path(self) -> str:
        return "/v1/models"

    def get_port(self) -> int:
        return 30000

    def build_startup_command(
        self,
        hf_model_id: str,
        quantisation: str,
        gpu_count: int,
        port: int = 30000,
        max_model_len: Optional[int] = None,
    ) -> List[str]:
        cmd = [
            "python", "-m", "sglang.launch_server",
            "--model-path", hf_model_id,
            "--host", "0.0.0.0",
            "--port", str(port),
            "--trust-remote-code",
            "--mem-fraction-static", "0.88",
        ]
        quant_map = {"awq": "awq", "gptq": "gptq", "int4": "awq"}
        if quantisation in quant_map:
            cmd += ["--quantization", quant_map[quantisation]]
        if gpu_count > 1:
            cmd += ["--tp", str(gpu_count)]
        if max_model_len:
            cmd += ["--context-length", str(max_model_len)]
        return cmd


# ---------------------------------------------------------------------------
# Transformers engine (CPU/GPU fallback)
# ---------------------------------------------------------------------------

class TransformersEngine(InferenceEngine):
    name = "transformers"

    def get_docker_image(self) -> str:
        return os.getenv("TRANSFORMERS_DOCKER_IMAGE", "huggingface/transformers-pytorch-gpu:latest")

    def get_health_path(self) -> str:
        return "/health"

    def get_models_path(self) -> str:
        return "/v1/models"

    def build_startup_command(
        self,
        hf_model_id: str,
        quantisation: str,
        gpu_count: int,
        port: int = 8000,
        max_model_len: Optional[int] = None,
    ) -> List[str]:
        return [
            "python", "-m", "text_generation_server.cli", "serve",
            hf_model_id,
            "--port", str(port),
            "--dtype", "float16" if quantisation == "fp16" else "float32",
        ]


# ---------------------------------------------------------------------------
# Engine registry
# ---------------------------------------------------------------------------

_ENGINE_CLASSES: Dict[str, type] = {
    "vllm":         VLLMEngine,
    "sglang":       SGLangEngine,
    "transformers": TransformersEngine,
}


def get_engine(name: str) -> InferenceEngine:
    cls = _ENGINE_CLASSES.get(name.lower())
    if not cls:
        raise ValueError(f"Unknown inference engine '{name}'. Supported: {list(_ENGINE_CLASSES)}")
    return cls()


def list_engines() -> List[Dict[str, Any]]:
    return [
        {
            "name":          name,
            "image":         cls().get_docker_image(),
            "health_path":   cls().get_health_path(),
            "models_path":   cls().get_models_path(),
            "default_port":  cls().get_port(),
        }
        for name, cls in _ENGINE_CLASSES.items()
    ]


# ---------------------------------------------------------------------------
# In-process lifecycle store
# ---------------------------------------------------------------------------

_LIFECYCLES: Dict[str, DeploymentLifecycle] = {}


def create_lifecycle(deployment_id: str, model_id: str, engine: str) -> DeploymentLifecycle:
    lc = DeploymentLifecycle(
        deployment_id=deployment_id,
        model_id=model_id,
        engine=engine,
        is_real=USE_REAL_PROVIDERS,
    )
    _LIFECYCLES[deployment_id] = lc
    return lc


def get_lifecycle(deployment_id: str) -> Optional[DeploymentLifecycle]:
    return _LIFECYCLES.get(deployment_id)
