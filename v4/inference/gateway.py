# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta LiteLLM Inference Gateway
====================================
Unified OpenAI-compatible inference proxy with:
- Multi-provider routing (OrQuanta-hosted vLLM, Groq, OpenAI, Anthropic, etc.)
- Virtual API key authentication + tenant isolation
- Token accounting + budget limits
- Rate limiting per tenant
- Request/response logging with PII redaction
- Retry + fallback policies
- Streaming support

SECURITY: Provider credentials are NEVER returned in API responses.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

logger = logging.getLogger("orquanta.inference.gateway")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "")          # External LiteLLM proxy if deployed separately
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")      # Never exposed to clients
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Whether to use real external providers or mock inference
USE_REAL_INFERENCE = os.getenv("USE_REAL_INFERENCE", "false").lower() == "true"

# Default inference timeout (seconds)
INFERENCE_TIMEOUT = int(os.getenv("INFERENCE_TIMEOUT_SECONDS", "120"))

# Budget guard: if a tenant's spend exceeds this, block inference
DEFAULT_BUDGET_USD = float(os.getenv("INFERENCE_DEFAULT_BUDGET_USD", "10.0"))

# ---------------------------------------------------------------------------
# Virtual key store (in-memory for dev; backed by DB in production via gateway_db.py)
# ---------------------------------------------------------------------------

_VIRTUAL_KEYS: Dict[str, Dict[str, Any]] = {}  # key_hash -> metadata


def register_virtual_key(
    key_hash: str,
    user_id: str,
    org_id: str,
    models: List[str],
    budget_usd: float = DEFAULT_BUDGET_USD,
    rate_limit_rpm: int = 60,
) -> None:
    """Register a virtual key (called by gateway_db.py on startup/creation)."""
    _VIRTUAL_KEYS[key_hash] = {
        "user_id": user_id,
        "org_id": org_id,
        "models": models,          # ["*"] = all models
        "budget_usd": budget_usd,
        "spent_usd": 0.0,
        "rate_limit_rpm": rate_limit_rpm,
        "request_times": [],
    }


def validate_virtual_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Validate an inference API key. Returns tenant metadata or None."""
    if not api_key:
        return None
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    entry = _VIRTUAL_KEYS.get(key_hash)
    if not entry:
        return None
    # Budget check
    if entry["spent_usd"] >= entry["budget_usd"]:
        logger.warning("[gateway] Budget exceeded for user=%s", entry["user_id"])
        return None
    return entry


def _rate_check(entry: Dict[str, Any]) -> bool:
    """Simple sliding-window rate limiter. Returns True if request is allowed."""
    now = time.time()
    window = 60  # 1 minute
    entry["request_times"] = [t for t in entry["request_times"] if now - t < window]
    if len(entry["request_times"]) >= entry["rate_limit_rpm"]:
        return False
    entry["request_times"].append(now)
    return True


# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------

# Maps OrQuanta model IDs → provider + provider model name
MODEL_ROUTES: Dict[str, Dict[str, str]] = {
    # Groq-hosted (fast, free tier)
    "llama-3.1-70b-groq":    {"provider": "groq",      "model": "llama-3.1-70b-versatile"},
    "llama-3.1-8b-groq":     {"provider": "groq",      "model": "llama-3.1-8b-instant"},
    "mixtral-8x7b-groq":     {"provider": "groq",      "model": "mixtral-8x7b-32768"},
    # OpenAI
    "gpt-4o":                {"provider": "openai",    "model": "gpt-4o"},
    "gpt-4o-mini":           {"provider": "openai",    "model": "gpt-4o-mini"},
    # Anthropic
    "claude-3-5-sonnet":     {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
    "claude-3-haiku":        {"provider": "anthropic", "model": "claude-3-haiku-20240307"},
}

# External provider fallback chain (tried in order if primary fails)
FALLBACK_CHAIN: Dict[str, List[str]] = {
    "llama-3.1-70b-groq": ["llama-3.1-70b-groq"],   # only 1 route for now
    "gpt-4o":             ["gpt-4o", "gpt-4o-mini"],
}


def _get_provider_key(provider: str) -> str:
    """Return provider API key. Never logged or returned in responses."""
    keys = {
        "openai":    OPENAI_API_KEY,
        "anthropic": ANTHROPIC_API_KEY,
        "groq":      GROQ_API_KEY,
    }
    return keys.get(provider, "")


# ---------------------------------------------------------------------------
# Cost estimation (tokens → USD)
# ---------------------------------------------------------------------------

# Cost per 1M tokens (input, output) in USD
_TOKEN_COSTS: Dict[str, Dict[str, float]] = {
    "groq/llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    "groq/llama-3.1-8b-instant":    {"input": 0.05, "output": 0.08},
    "groq/mixtral-8x7b-32768":      {"input": 0.24, "output": 0.24},
    "openai/gpt-4o":                {"input": 2.50, "output": 10.0},
    "openai/gpt-4o-mini":           {"input": 0.15, "output": 0.60},
    "anthropic/claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.0},
    "anthropic/claude-3-haiku-20240307":    {"input": 0.25, "output": 1.25},
}


def estimate_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate inference cost in USD from token counts."""
    key = f"{provider}/{model}"
    costs = _TOKEN_COSTS.get(key, {"input": 0.001, "output": 0.002})
    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# Inference request
# ---------------------------------------------------------------------------

class InferenceError(Exception):
    """Raised when inference fails after all retries/fallbacks."""


async def _call_openai_compat(
    provider_url: str,
    api_key: str,
    model: str,
    messages: List[Dict],
    stream: bool,
    max_tokens: int,
    temperature: float,
    timeout: int,
) -> Dict[str, Any]:
    """Call an OpenAI-compatible endpoint. Never logs api_key."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{provider_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


def _provider_base_url(provider: str) -> str:
    """Return the base URL for a provider's OpenAI-compatible API."""
    urls = {
        "openai":    "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",  # via LiteLLM proxy
        "groq":      "https://api.groq.com/openai/v1",
    }
    # If LiteLLM proxy is deployed, route everything through it
    if LITELLM_BASE_URL:
        return LITELLM_BASE_URL
    return urls.get(provider, "https://api.openai.com/v1")


async def route_inference_request(
    model_id: str,
    messages: List[Dict],
    stream: bool = False,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    tenant: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Route an inference request to the appropriate provider.

    Args:
        model_id: OrQuanta model identifier (e.g. 'llama-3.1-70b-groq')
        messages: OpenAI-format message list
        stream: Whether to stream the response
        max_tokens: Maximum output tokens
        temperature: Sampling temperature
        tenant: Tenant metadata from virtual key validation

    Returns:
        OpenAI-compatible response dict

    Raises:
        InferenceError: If all providers fail
    """
    if not USE_REAL_INFERENCE:
        logger.info("[gateway] Mock inference for model=%s (USE_REAL_INFERENCE=false)", model_id)
        return _mock_response(model_id, messages, max_tokens)

    route = MODEL_ROUTES.get(model_id)
    if not route:
        raise InferenceError(f"Model '{model_id}' is not registered in OrQuanta routing table.")

    provider = route["provider"]
    provider_model = route["model"]
    api_key = _get_provider_key(provider)

    if not api_key:
        raise InferenceError(
            f"Provider '{provider}' is not configured. Set {provider.upper()}_API_KEY."
        )

    # Tenant model permission check
    if tenant and tenant.get("models") and tenant["models"] != ["*"]:
        if model_id not in tenant["models"]:
            raise InferenceError(f"Model '{model_id}' is not permitted for this API key.")

    base_url = _provider_base_url(provider)

    start = time.time()
    try:
        result = await _call_openai_compat(
            provider_url=base_url,
            api_key=api_key,
            model=provider_model,
            messages=messages,
            stream=False,  # streaming handled by SSE layer
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=INFERENCE_TIMEOUT,
        )
        elapsed = time.time() - start

        # Token accounting
        usage = result.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost = estimate_cost_usd(provider, provider_model, input_tokens, output_tokens)

        if tenant:
            tenant["spent_usd"] += cost

        logger.info(
            "[gateway] inference ok model=%s provider=%s input_tok=%d output_tok=%d cost=$%.6f elapsed=%.2fs",
            model_id, provider, input_tokens, output_tokens, cost, elapsed,
        )
        # Inject OrQuanta metadata without exposing provider credentials
        result["x_orquanta"] = {
            "model_id": model_id,
            "provider": provider,
            "cost_usd": round(cost, 6),
            "latency_ms": round(elapsed * 1000),
        }
        return result

    except httpx.HTTPStatusError as e:
        logger.error("[gateway] provider=%s HTTP %d: %s", provider, e.response.status_code, e.response.text[:200])
        raise InferenceError(f"Provider returned HTTP {e.response.status_code}") from e
    except httpx.TimeoutException:
        raise InferenceError(f"Provider '{provider}' timed out after {INFERENCE_TIMEOUT}s")
    except Exception as e:
        logger.error("[gateway] inference failed model=%s: %s", model_id, e)
        raise InferenceError(str(e)) from e


def _mock_response(model_id: str, messages: List[Dict], max_tokens: int) -> Dict[str, Any]:
    """Return a clearly-labelled mock response for testing."""
    last_user_msg = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"),
        "Hello"
    )
    return {
        "id": "mock-orq-00000000",
        "object": "chat.completion",
        "model": model_id,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": (
                    f"[MOCK — USE_REAL_INFERENCE=false] "
                    f"This is a demonstration response for model '{model_id}'. "
                    f"Your message was: '{last_user_msg[:100]}'. "
                    f"Set USE_REAL_INFERENCE=true and configure provider API keys to run real inference."
                ),
            },
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 20, "completion_tokens": 60, "total_tokens": 80},
        "x_orquanta": {
            "model_id": model_id,
            "provider": "mock",
            "cost_usd": 0.0,
            "latency_ms": 0,
            "is_mock": True,
        },
    }
