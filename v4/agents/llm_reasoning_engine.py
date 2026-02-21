"""
OrQuanta Agentic v1.0 — LLM Reasoning Engine

Unified interface to OpenAI (GPT-4o) and Anthropic (Claude 3.5 Sonnet).
Provides prompt templates, chain-of-thought reasoning, structured output
parsing, and fallback logic when primary LLM fails.
"""

from __future__ import annotations

import json
import logging
import os
import time
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


class LLMConfig(BaseModel):
    """Runtime LLM configuration loaded from environment variables."""
    provider: LLMProvider = Field(
        default_factory=lambda: LLMProvider(
            os.getenv("LLM_PROVIDER", "mock")
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
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.cfg = config or LLMConfig()
        self._openai_client: Any = None
        self._anthropic_client: Any = None
        self._init_clients()
        logger.info(f"LLMReasoningEngine initialised with provider: {self.cfg.provider}")

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_clients(self) -> None:
        """Lazily initialise LLM clients based on provider setting."""
        if self.cfg.provider == LLMProvider.OPENAI and self.cfg.openai_api_key:
            try:
                import openai  # type: ignore
                self._openai_client = openai.AsyncOpenAI(api_key=self.cfg.openai_api_key)
                logger.info("OpenAI client initialised.")
            except ImportError:
                logger.warning("openai package not installed. Falling back to mock.")
                self.cfg.provider = LLMProvider.MOCK

        elif self.cfg.provider == LLMProvider.ANTHROPIC and self.cfg.anthropic_api_key:
            try:
                import anthropic  # type: ignore
                self._anthropic_client = anthropic.AsyncAnthropic(
                    api_key=self.cfg.anthropic_api_key
                )
                logger.info("Anthropic client initialised.")
            except ImportError:
                logger.warning("anthropic package not installed. Falling back to mock.")
                self.cfg.provider = LLMProvider.MOCK

        else:
            logger.info("No valid LLM API keys found — using MOCK provider.")
            self.cfg.provider = LLMProvider.MOCK

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        prompt = self._render_template(template_name, variables)
        
        logger.info(f"[{agent_name}] Calling LLM ({self.cfg.provider}) with template '{template_name}'")
        
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                raw = await self._call_llm(prompt)
                parsed = self._parse_json_response(raw)
                logger.info(f"[{agent_name}] LLM call succeeded on attempt {attempt}.")
                return parsed
            except Exception as exc:
                logger.warning(f"[{agent_name}] LLM attempt {attempt} failed: {exc}")
                if attempt == self.cfg.max_retries:
                    logger.error(f"[{agent_name}] All LLM retries exhausted. Using mock fallback.")
                    return MOCK_RESPONSES.get(template_name, {"error": "llm_unavailable"})
                time.sleep(2 ** attempt)  # Exponential backoff

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
        """Dispatch to the correct LLM provider."""
        if self.cfg.provider == LLMProvider.MOCK:
            return json.dumps({"mock": True})

        if self.cfg.provider == LLMProvider.OPENAI:
            return await self._call_openai(prompt)

        if self.cfg.provider == LLMProvider.ANTHROPIC:
            return await self._call_anthropic(prompt)

        raise RuntimeError(f"Unknown provider: {self.cfg.provider}")

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
