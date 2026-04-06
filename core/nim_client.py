"""
OrQuanta NIM Client — NVIDIA Inference Microservices API

Async HTTP client for NVIDIA NIM API.
NIM uses the OpenAI-compatible chat completions protocol, so this wraps
the openai library pointed at the NIM base URL.

Supported NIM models:
  - meta/llama-3.1-8b-instruct      (free-tier / development)
  - nvidia/nemotron-4-340b-instruct (enterprise production)
  - mistralai/mixtral-8x22b-instruct

Environment variables:
  NIM_API_KEY   — NVIDIA API key (from build.nvidia.com)
  NIM_API_URL   — NIM endpoint URL (default: https://integrate.api.nvidia.com/v1)
  NIM_MODEL     — Model to use (default: meta/llama-3.1-8b-instruct)
  NIM_TIMEOUT   — Seconds before timeout (default: 30)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger("orquanta.nim")

_NIM_DEFAULT_URL = "https://integrate.api.nvidia.com/v1"
_NIM_DEFAULT_MODEL = "meta/llama-3.1-8b-instruct"


class NIMClient:
    """
    Async client for NVIDIA NIM (OpenAI-compatible schema).

    Falls back to mock response when NIM is not configured so the
    rest of the platform continues to function in development.

    Usage::

        client = NIMClient()
        response = await client.chat(
            system="You are an expert GPU cloud analyst.",
            user="Explain why the agent scaled down the cluster.",
        )
        print(response)  # → natural language explanation
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("NIM_API_KEY", "")
        self.base_url = os.getenv("NIM_API_URL", _NIM_DEFAULT_URL)
        self.model = os.getenv("NIM_MODEL", _NIM_DEFAULT_MODEL)
        self.timeout = float(os.getenv("NIM_TIMEOUT", "30"))
        self._client: Any = None
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        """Initialise the OpenAI-compatible client pointed at NIM."""
        if not self.api_key:
            logger.info(
                "NIM_API_KEY not set — NIMClient in mock mode. "
                "Set NIM_API_KEY from https://build.nvidia.com to enable."
            )
            return
        try:
            import openai  # type: ignore
            self._client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
            self._available = True
            logger.info(
                f"NIMClient ready | model={self.model} | url={self.base_url}"
            )
        except ImportError:
            logger.warning(
                "openai package not installed — NIMClient disabled. "
                "pip install openai"
            )

    @property
    def is_available(self) -> bool:
        """True if NIM is configured and client is ready."""
        return self._available and self._client is not None

    async def chat(
        self,
        user: str,
        system: str = "You are an expert autonomous GPU cloud AI assistant.",
        max_tokens: int = 512,
        temperature: float = 0.4,
    ) -> str:
        """
        Send a chat completion request to NIM.

        Args:
            user: The user message / prompt.
            system: System context for the model.
            max_tokens: Maximum response tokens.
            temperature: Sampling temperature (lower = more deterministic).

        Returns:
            String response from the NIM model (or mock if not configured).
        """
        if not self.is_available:
            return self._mock_response(user)

        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            text = resp.choices[0].message.content or ""
            logger.info(
                f"[NIM] Response received. tokens={resp.usage.total_tokens if resp.usage else '?'}"
            )
            return text.strip()

        except Exception as exc:
            logger.warning(f"[NIM] API call failed: {exc} — returning mock response.")
            return self._mock_response(user)

    async def explain_agent_decision(
        self,
        goal_text: str,
        action_taken: str,
        reasoning_log: list[dict],
        cost_usd: float = 0.0,
    ) -> str:
        """
        Generate a natural language explanation of an agent decision.

        Args:
            goal_text: Original user goal.
            action_taken: What the agent ultimately did.
            reasoning_log: List of ReAct steps from the orchestrator.
            cost_usd: Total cost incurred.

        Returns:
            A clear, user-friendly explanation.
        """
        # Summarise the reasoning log to avoid token overflow
        steps_summary = "\n".join(
            f"[{step.get('step', '?')}] {str(step.get('content', ''))[:300]}"
            for step in reasoning_log[-8:]  # Last 8 steps
        )

        prompt = (
            f"An autonomous AI system was given this goal:\n"
            f'"{goal_text}"\n\n'
            f"The system took this action: {action_taken}\n"
            f"Total cost: ${cost_usd:.2f}\n\n"
            f"Internal reasoning steps:\n{steps_summary}\n\n"
            f"In 2-3 clear sentences, explain to the user WHY the system made this decision "
            f"and what it accomplished. Be specific about cost efficiency and technical choices. "
            f"Do NOT use technical jargon. Write for a non-technical business user."
        )

        return await self.chat(
            user=prompt,
            system=(
                "You are an AI explainability assistant for OrQuanta, an autonomous GPU cloud platform. "
                "Your job is to explain complex AI agent decisions in plain English. "
                "Be concise, accurate, and reassuring. Always mention cost savings when relevant."
            ),
            max_tokens=256,
            temperature=0.3,
        )

    def _mock_response(self, prompt: str) -> str:
        """Return a plausible mock explanation when NIM is not available."""
        return (
            "The OrQuanta agent analysed your GPU workload requirements and selected the most "
            "cost-efficient provider configuration available. The decision was based on real-time "
            "spot pricing data, current node health scores, and your stated budget constraints. "
            "No NIM API key configured — set NIM_API_KEY for AI-powered explanations."
        )

    def get_status(self) -> dict[str, Any]:
        """Return NIM client status for the platform health check."""
        return {
            "nim_available": self.is_available,
            "nim_model": self.model if self.is_available else None,
            "nim_url": self.base_url if self.is_available else None,
            "mode": "live" if self.is_available else "mock",
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_nim_client: NIMClient | None = None


def get_nim_client() -> NIMClient:
    """Return the global NIMClient singleton."""
    global _nim_client
    if _nim_client is None:
        _nim_client = NIMClient()
    return _nim_client
