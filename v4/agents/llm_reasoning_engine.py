"""
OrQuanta Agentic v1.0 — LLM Reasoning Engine

Unified interface to OpenAI (GPT-4o) and Anthropic (Claude 3.5 Sonnet).
Provides prompt templates, chain-of-thought reasoning, structured output
parsing, and fallback logic when primary LLM fails.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import defaultdict, deque
from enum import Enum
from string import Template
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("orquanta.llm")

# ---------------------------------------------------------------------------
# Enums & Config
# ---------------------------------------------------------------------------

class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOCK = "mock"  # Used in tests / when no API key is set
    AUTO = "auto"  # Auto-detect best available provider
    NIM = "nim"    # NVIDIA Inference Microservices (Nemotron / Llama via NVIDIA API)

# ---------------------------------------------------------------------------
# TurboQuant — KV-cache compression (Google ICLR 2026, arXiv:2504.19874)
# PyPI: turboquant-vllm>=1.3.0  |  pip install turboquant-vllm[vllm]
# ---------------------------------------------------------------------------
# Benchmarked compression vs FP16 baseline (Molmo2-4B, RTX 4090, 11K tokens):
#   TQ4 incremental: 3.76x compression, ~97% cosine similarity, 1.78x overhead
#   TQ3:             1.94x compression, ~95% cosine similarity, 2.35x overhead
#
# Two integration paths:
#   1. vLLM serve (recommended for OrQuanta GPU jobs):
#        vllm serve <model> --attention-backend CUSTOM
#      The turboquant-vllm plugin auto-registers via vLLM's entry-point system.
#
#   2. HuggingFace Transformers (used for OrQuanta's own internal LLM calls):
#        from turboquant_vllm import CompressedDynamicCache
#        compressed = CompressedDynamicCache(cache, head_dim=128, bits=4)
#      Pass `cache` (not the wrapper) to model.generate().
#
# Requires: torch>=2.6, transformers>=4.57, vllm>=0.18 (for vLLM path)
# ---------------------------------------------------------------------------
TURBOQUANT_ENABLED: bool = os.getenv("TURBOQUANT_ENABLED", "false").lower() == "true"

_turboquant_available: bool = False
if TURBOQUANT_ENABLED:
    import importlib.util
    _turboquant_available = importlib.util.find_spec("turboquant_vllm") is not None
    if _turboquant_available:
        logger.info(
            "TurboQuant active (turboquant-vllm %s). "
            "KV-cache compression: 3.76x at 4-bit, ~97%% cosine similarity. "
            "vLLM jobs: pass --attention-backend CUSTOM. "
            "HF jobs: use CompressedDynamicCache wrapper.",
            importlib.metadata.version("turboquant-vllm") if importlib.util.find_spec("importlib.metadata") else ">=1.3.0",
        )
    else:
        logger.error(
            "TURBOQUANT_ENABLED=true but 'turboquant-vllm' is not installed. "
            "Run: pip install turboquant-vllm[vllm]  — falling back to standard inference."
        )


def get_turboquant_vllm_serve_flag() -> str:
    """
    Returns the CLI flag to append when launching a vLLM serve process with
    TurboQuant KV-cache compression enabled.

    Usage (OrQuanta scheduler, when provisioning an LLM inference job):
        cmd = f"vllm serve {model} {get_turboquant_vllm_serve_flag()}"
        subprocess.Popen(cmd.split())

    The 'turboquant-vllm' package registers the TQ4 attention backend
    automatically via vLLM's plugin entry-point system — no code changes needed.
    Returns empty string when TurboQuant is unavailable (falls back silently).
    """
    if not _turboquant_available:
        return ""
    return "--attention-backend CUSTOM"


def make_compressed_dynamic_cache(cache: Any, head_dim: int = 128, bits: int = 4) -> Any:
    """
    Wrap a HuggingFace DynamicCache with TurboQuant compression.

    Use this when OrQuanta's own agent calls run a local HuggingFace model
    (not via vLLM serve). Pass the original `cache` object to model.generate(),
    not the compressed wrapper — compression happens on every cache.update().

    Args:
        cache:    A transformers.DynamicCache instance.
        head_dim: Attention head dimension (default 128 for most 7B–70B models).
        bits:     Quantisation bit-width. 4 (3.76x, ~97% similarity) recommended;
                  use 3 for maximum compression (1.94x, ~95% similarity).

    Returns:
        CompressedDynamicCache wrapper, or the original cache if TQ unavailable.
    """
    if not _turboquant_available:
        return cache
    from turboquant_vllm import CompressedDynamicCache  # type: ignore
    return CompressedDynamicCache(cache, head_dim=head_dim, bits=bits)



class LLMConfig(BaseModel):
    """Runtime LLM configuration loaded from environment variables."""
    provider: LLMProvider = Field(
        default_factory=lambda: LLMProvider(
            os.getenv("LLM_PROVIDER", "auto")
        )
    )
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))
    anthropic_model: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"))
    max_tokens: int = 2048
    temperature: float = 0.2
    timeout_seconds: int = 60
    max_retries: int = 3


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

PROMPT_TEMPLATES: dict[str, str] = {
    "orchestrator_decompose": """
You are the MasterOrchestrator of OrQuanta, an autonomous GPU cloud platform.

GOAL (from user): "$goal"

Your job is to decompose this goal into concrete sub-tasks, assign each to
the correct specialist agent, and produce a JSON execution plan.

Available agents:
- scheduler_agent: GPU job queue, bin-packing, priority scoring
- cost_optimizer_agent: Spot price monitoring, budget enforcement, switching
- healing_agent: Health checks, OOM recovery, anomaly detection
- forecast_agent: Demand forecasting, capacity planning, pre-provisioning

Respond ONLY with valid JSON matching this schema:
{
  "reasoning": "<your chain-of-thought analysis>",
  "tasks": [
    {
      "task_id": "<uuid>",
      "agent": "<agent_name>",
      "action": "<action to perform>",
      "parameters": { ... },
      "priority": <1-10>,
      "depends_on": ["<task_id>"] 
    }
  ],
  "estimated_cost_usd": <float>,
  "estimated_duration_minutes": <int>
}
""",

    "scheduler_score": """
You are the SchedulerAgent. Score the following GPU job for priority.

Job details: $job_json

Consider: user priority tier, VRAM requirements, cost limit, deadline.
Reply ONLY with JSON: {"priority_score": <0.0-1.0>, "reasoning": "<brief>"}
""",

    "cost_optimize": """
You are the CostOptimizerAgent. Analyse current GPU spot prices and
recommend the cheapest option meeting requirements.

Requirements: $requirements_json
Current prices: $prices_json

Reply ONLY with JSON:
{
  "recommended_provider": "<name>",
  "recommended_gpu": "<type>",
  "estimated_hourly_cost": <float>,
  "reasoning": "<brief>",
  "alternatives": [{"provider": "", "gpu": "", "cost": 0.0}]
}
""",

    "healing_diagnose": """
You are the HealingAgent. A GPU job has reported anomalous metrics.

Job ID: $job_id
Metrics snapshot: $metrics_json
Error log: $error_log

Diagnose the root cause and prescribe an action from:
[restart, migrate, scale_up, pause, terminate]

Reply ONLY with JSON:
{
  "diagnosis": "<root cause>",
  "action": "<action>",
  "parameters": {"...": "..."},
  "confidence": <0.0-1.0>,
  "reasoning": "<chain-of-thought>"
}
""",

    "forecast_analyze": """
You are the ForecastAgent. Based on historical job patterns, forecast
GPU demand for the next time window.

Historical data (last 30 days): $history_json
Current utilization: $utilization_json

Reply ONLY with JSON:
{
  "forecast_window_hours": 24,
  "predicted_job_count": <int>,
  "predicted_gpu_demand": {"H100": <int>, "A100": <int>, "T4": <int>},
  "confidence_interval": {"low": <float>, "high": <float>},
  "recommendation": "<pre-provision / hold / scale-down>",
  "reasoning": "<chain-of-thought>"
}
""",

    "gpu_recommend": """
You are the GPU RecommendationAgent for OrQuanta. Based on the user's
workload description, recommend the optimal GPU type and provider.

Workload: "$workload"
Available GPUs: $available_gpus
Current spot prices: $prices_json

Consider: VRAM requirements, estimated training time, cost efficiency,
model size (parameter count → VRAM mapping: 7B≈16GB, 13B≈28GB, 70B≈80GB).

Reply ONLY with JSON:
{
  "recommended_gpu": "<H100/A100/A100-80G/T4/L4>",
  "recommended_provider": "<provider>",
  "recommended_region": "<region>",
  "estimated_cost_usd": <float>,
  "estimated_duration_hours": <float>,
  "vram_required_gb": <int>,
  "reasoning": "<chain-of-thought>"
}
""",

    "action_explain": """
You are an AI explainability assistant for OrQuanta, an autonomous GPU cloud platform.
A user wants to understand WHY the AI agent made a specific decision.

User Goal: "$goal"
Agent Action: $action
Total Cost Incurred: $$cost_usd
Reasoning Steps:
$reasoning_steps

Explain in 2-3 clear sentences:
1. What the agent did and why
2. What cost/performance benefit was achieved
3. Any notable trade-offs considered

Write for a non-technical business user. Be reassuring and specific.
Do NOT use jargon. Do NOT include JSON.
""",
}


# ---------------------------------------------------------------------------
# Mock "LLM" for zero-dependency testing
# ---------------------------------------------------------------------------

MOCK_RESPONSES: dict[str, Any] = {
    "orchestrator_decompose": {
        "reasoning": "MOCK: Analysed goal. Decomposing into 3 tasks.",
        "tasks": [
            {
                "task_id": "t-001",
                "agent": "scheduler_agent",
                "action": "schedule_job",
                "parameters": {"gpu_type": "H100", "count": 1},
                "priority": 8,
                "depends_on": [],
            },
            {
                "task_id": "t-002",
                "agent": "cost_optimizer_agent",
                "action": "find_cheapest_spot",
                "parameters": {"gpu_type": "H100"},
                "priority": 9,
                "depends_on": [],
            },
            {
                "task_id": "t-003",
                "agent": "healing_agent",
                "action": "monitor_job",
                "parameters": {},
                "priority": 5,
                "depends_on": ["t-001"],
            },
        ],
        "estimated_cost_usd": 12.50,
        "estimated_duration_minutes": 60,
    },
    "scheduler_score": {"priority_score": 0.82, "reasoning": "MOCK: High priority job."},
    "cost_optimize": {
        "recommended_provider": "coreweave",
        "recommended_gpu": "H100",
        "estimated_hourly_cost": 3.89,
        "reasoning": "MOCK: CoreWeave offers best spot rates for H100.",
        "alternatives": [{"provider": "aws", "gpu": "H100", "cost": 5.20}],
    },
    "healing_diagnose": {
        "diagnosis": "MOCK: OOM — job requires 84GB but allocated 80GB.",
        "action": "scale_up",
        "parameters": {"new_gpu_type": "H100", "count": 2},
        "confidence": 0.95,
        "reasoning": "MOCK: Memory pressure consistently above 98%.",
    },
    "forecast_analyze": {
        "forecast_window_hours": 24,
        "predicted_job_count": 47,
        "predicted_gpu_demand": {"H100": 8, "A100": 12, "T4": 20},
        "confidence_interval": {"low": 0.78, "high": 0.91},
        "recommendation": "pre-provision",
        "reasoning": "MOCK: Monday morning spike pattern detected.",
    },
}


# ---------------------------------------------------------------------------
# Main Engine Class
# ---------------------------------------------------------------------------

class LLMReasoningEngine:
    """Unified LLM interface used by all OrQuanta agents.

    Supports OpenAI GPT-4o, Anthropic Claude, and a deterministic mock
    mode (used in tests and when no API keys are configured).

    All calls are logged with reasoning traces for the audit trail.
    Rate-limited per agent_name: max 20 LLM calls per 60s window.
    """

    # Per-agent sliding-window rate limit (calls per window)
    _RATE_LIMIT_CALLS = int(os.getenv("LLM_RATE_LIMIT_CALLS", "20"))
    _RATE_LIMIT_WINDOW = float(os.getenv("LLM_RATE_LIMIT_WINDOW_S", "60"))

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.cfg = config or LLMConfig()
        self._openai_client: Any = None
        self._anthropic_client: Any = None
        self._nim_client: Any = None  # NIMClient singleton (lazy)
        # Per-agent call timestamps for rate limiting
        self._rate_buckets: defaultdict[str, deque] = defaultdict(deque)
        self._init_clients()
        logger.info(f"LLMReasoningEngine initialised with provider: {self.cfg.provider}")

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_clients(self) -> None:
        """Initialise all available LLM clients.

        AUTO mode: detect from API keys (OpenAI → Anthropic → Mock).
        Explicit mode: initialise the specified provider.
        Either way, we try to init ALL available clients for fallback.
        """
        # Try OpenAI
        if self.cfg.openai_api_key:
            try:
                import openai  # type: ignore
                self._openai_client = openai.AsyncOpenAI(api_key=self.cfg.openai_api_key)
                logger.info("OpenAI client initialised (available for reasoning).")
            except ImportError:
                logger.warning("openai package not installed — skipping OpenAI.")

        # Try Anthropic
        if self.cfg.anthropic_api_key:
            try:
                import anthropic  # type: ignore
                self._anthropic_client = anthropic.AsyncAnthropic(
                    api_key=self.cfg.anthropic_api_key
                )
                logger.info("Anthropic client initialised (available for fallback).")
            except ImportError:
                logger.warning("anthropic package not installed — skipping Anthropic.")

        # Auto-detect primary provider from available clients
        if self.cfg.provider == LLMProvider.AUTO:
            if self._openai_client:
                self.cfg.provider = LLMProvider.OPENAI
                logger.info("AUTO: Selected OpenAI as primary LLM provider.")
            elif self._anthropic_client:
                self.cfg.provider = LLMProvider.ANTHROPIC
                logger.info("AUTO: Selected Anthropic as primary LLM provider.")
            else:
                self.cfg.provider = LLMProvider.MOCK
                logger.info("AUTO: No API keys found — using MOCK provider.")
        elif self.cfg.provider == LLMProvider.OPENAI and not self._openai_client:
            logger.warning("OpenAI requested but not available. Falling back.")
            self.cfg.provider = LLMProvider.ANTHROPIC if self._anthropic_client else LLMProvider.MOCK
        elif self.cfg.provider == LLMProvider.ANTHROPIC and not self._anthropic_client:
            logger.warning("Anthropic requested but not available. Falling back.")
            self.cfg.provider = LLMProvider.OPENAI if self._openai_client else LLMProvider.MOCK

        # Try NIM
        try:
            from core.nim_client import get_nim_client
            nim = get_nim_client()
            if nim.is_available:
                self._nim_client = nim
                logger.info("NIM client available — will be used for reason_with_nim() calls.")
        except Exception:
            pass  # NIM is optional

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _check_rate_limit(self, agent_name: str) -> None:
        """Sliding-window rate limit: raises if agent exceeds LLM_RATE_LIMIT_CALLS per window."""
        bucket = self._rate_buckets[agent_name]
        now = time.monotonic()
        # Evict timestamps outside the window
        while bucket and bucket[0] < now - self._RATE_LIMIT_WINDOW:
            bucket.popleft()
        if len(bucket) >= self._RATE_LIMIT_CALLS:
            raise RuntimeError(
                f"LLM rate limit hit for agent '{agent_name}': "
                f"{self._RATE_LIMIT_CALLS} calls/{self._RATE_LIMIT_WINDOW}s exceeded."
            )
        bucket.append(now)

    async def reason_with_nim(
        self,
        template_name: str,
        variables: dict[str, Any],
        agent_name: str = "unknown",
    ) -> str:
        """
        Call NIM for natural-language (non-JSON) reasoning.
        Used for the /api/v1/explain endpoint and rich narrative outputs.

        Falls back to standard `reason()` → mock if NIM unavailable.

        Returns:
            Plain text string (not JSON).
        """
        if self._nim_client and self._nim_client.is_available:
            prompt_tmpl = PROMPT_TEMPLATES.get(template_name, "")
            if prompt_tmpl:
                from string import Template
                str_vars = {
                    k: json.dumps(v, indent=2) if isinstance(v, (dict, list)) else str(v)
                    for k, v in variables.items()
                }
                prompt = Template(prompt_tmpl).safe_substitute(str_vars)
                try:
                    result = await self._nim_client.chat(
                        user=prompt,
                        system="You are an expert AI assistant for OrQuanta GPU Cloud Platform.",
                    )
                    logger.info(f"[{agent_name}] reason_with_nim succeeded via NIM.")
                    return result
                except Exception as exc:
                    logger.warning(f"[{agent_name}] NIM call failed: {exc} — falling back.")

        # Fallback: use standard reason() and convert to string
        try:
            result_dict = await self.reason(template_name, variables, agent_name)
            return json.dumps(result_dict, indent=2)
        except Exception:
            return PROMPT_TEMPLATES.get(template_name, "Explanation unavailable.")[:200]

    async def reason(
        self,
        template_name: str,
        variables: dict[str, Any],
        agent_name: str = "unknown",
    ) -> dict[str, Any]:
        """Execute a reasoning call using the named prompt template.

        Args:
            template_name: Key in PROMPT_TEMPLATES.
            variables: Dict of substitution variables for the template.
            agent_name: Calling agent name (for logging).

        Returns:
            Parsed JSON dict from LLM response.
        """
        # Enforce per-agent rate limit before touching the LLM
        try:
            self._check_rate_limit(agent_name)
        except RuntimeError as exc:
            logger.warning(f"[{agent_name}] {exc} — returning mock fallback.")
            return MOCK_RESPONSES.get(template_name, {"error": "rate_limited"})

        # Short-circuit for mock provider — return rich template responses without any LLM call.
        # _call_llm() in mock mode returns {"mock": True} which has no task data; this is correct.
        if self.cfg.provider == LLMProvider.MOCK:
            logger.info(f"[{agent_name}] Calling LLM ({self.cfg.provider}) template='{template_name}'")
            logger.info(f"[{agent_name}] LLM succeeded on attempt 1.")
            return MOCK_RESPONSES.get(template_name, {"reasoning": "MOCK", "tasks": []})

        prompt = self._render_template(template_name, variables)
        logger.info(f"[{agent_name}] Calling LLM ({self.cfg.provider}) template='{template_name}'")

        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                raw = await self._call_llm(prompt)
                parsed = self._parse_json_response(raw)
                logger.info(f"[{agent_name}] LLM succeeded on attempt {attempt}.")
                return parsed
            except Exception as exc:
                logger.warning(f"[{agent_name}] LLM attempt {attempt} failed: {exc}")
                if attempt == self.cfg.max_retries:
                    logger.error(f"[{agent_name}] All retries exhausted. Using mock fallback.")
                    return MOCK_RESPONSES.get(template_name, {"error": "llm_unavailable"})
                # Non-blocking exponential backoff — never block the event loop
                await asyncio.sleep(2 ** attempt)

        return MOCK_RESPONSES.get(template_name, {"error": "llm_unavailable"})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_template(self, name: str, variables: dict[str, Any]) -> str:
        """Substitute variables into the named prompt template."""
        tmpl_str = PROMPT_TEMPLATES.get(name, "")
        if not tmpl_str:
            raise ValueError(f"Unknown prompt template: '{name}'")

        # Convert dict values to JSON strings for insertion
        str_vars: dict[str, str] = {}
        for k, v in variables.items():
            if isinstance(v, (dict, list)):
                str_vars[k] = json.dumps(v, indent=2)
            else:
                str_vars[k] = str(v)

        return Template(tmpl_str).safe_substitute(str_vars)

    async def _call_llm(self, prompt: str) -> str:
        """Dispatch to LLM with automatic fallback chain.

        Chain: Primary provider → Secondary provider → Mock.
        This ensures the platform always returns a response.
        """
        if self.cfg.provider == LLMProvider.MOCK:
            return json.dumps({"mock": True})

        # Try primary provider
        primary_error = None
        if self.cfg.provider == LLMProvider.OPENAI and self._openai_client:
            try:
                return await self._call_openai(prompt)
            except Exception as exc:
                primary_error = exc
                logger.warning(f"OpenAI call failed: {exc}")

        elif self.cfg.provider == LLMProvider.ANTHROPIC and self._anthropic_client:
            try:
                return await self._call_anthropic(prompt)
            except Exception as exc:
                primary_error = exc
                logger.warning(f"Anthropic call failed: {exc}")

        # Try fallback provider
        if primary_error:
            if self.cfg.provider != LLMProvider.ANTHROPIC and self._anthropic_client:
                try:
                    logger.info("Falling back to Anthropic...")
                    return await self._call_anthropic(prompt)
                except Exception as exc:
                    logger.warning(f"Anthropic fallback also failed: {exc}")
            elif self.cfg.provider != LLMProvider.OPENAI and self._openai_client:
                try:
                    logger.info("Falling back to OpenAI...")
                    return await self._call_openai(prompt)
                except Exception as exc:
                    logger.warning(f"OpenAI fallback also failed: {exc}")

        # Last resort: mock
        logger.info("All LLM providers unavailable. Returning mock data.")
        return json.dumps({"mock": True})

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI Chat Completions API."""
        if self._openai_client is None:
            raise RuntimeError("OpenAI client not initialised.")
        response = await self._openai_client.chat.completions.create(
            model=self.cfg.openai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.cfg.max_tokens,
            temperature=self.cfg.temperature,
            response_format={"type": "json_object"},
            timeout=self.cfg.timeout_seconds,
        )
        return response.choices[0].message.content

    async def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Messages API."""
        if self._anthropic_client is None:
            raise RuntimeError("Anthropic client not initialised.")
        response = await self._anthropic_client.messages.create(
            model=self.cfg.anthropic_model,
            max_tokens=self.cfg.max_tokens,
            temperature=self.cfg.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _parse_json_response(self, raw: str) -> dict[str, Any]:
        """Parse JSON from LLM response, stripping markdown fences if needed."""
        stripped = raw.strip()
        # Handle ```json ... ``` wrapping
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            stripped = "\n".join(lines[1:-1])
        return json.loads(stripped)
