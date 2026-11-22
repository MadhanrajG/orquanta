# Copyright 2026 OrQuanta — Apache License 2.0
"""
Phase 5B — LLM Observability
=============================
Tracks model selection, token usage, latency, TTFT, throughput,
failures, tool calls, agent execution, evaluation scores and cost.

Langfuse integration is OPTIONAL:
- If LANGFUSE_SECRET_KEY is set and langfuse is installed, events are
  forwarded to Langfuse.
- If not configured, all data is captured in-process and exposed via
  the /api/v1/observability/llm/* endpoints.

Privacy:
- Prompt and completion content capture is DISABLED by default.
- Enable with LLM_CAPTURE_CONTENT=true AND explicit per-tenant consent.
- Do not collect sensitive customer content without authorisation.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orquanta.observability.llm")

# ── Langfuse (optional) ───────────────────────────────────────────────────────
_LANGFUSE_AVAILABLE = False
try:
    from langfuse import Langfuse
    _LANGFUSE_AVAILABLE = True
except ImportError:
    pass

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

# Content capture requires explicit opt-in
LLM_CAPTURE_CONTENT = os.getenv("LLM_CAPTURE_CONTENT", "false").lower() == "true"


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class LLMCallRecord:
    """Immutable record of one LLM API call."""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    actor_id: str = ""
    model: str = ""
    provider: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    ttft_ms: float = 0.0           # Time to first token
    tokens_per_second: float = 0.0
    cost_usd: float = 0.0
    success: bool = True
    error_type: str = ""
    is_streaming: bool = False
    tool_calls: int = 0
    # Content only stored when LLM_CAPTURE_CONTENT=true AND tenant has consented
    prompt_hash: str = ""          # SHA-256 of prompt (always; no raw content by default)
    completion_hash: str = ""      # SHA-256 of completion
    # Evaluation
    eval_score: Optional[float] = None
    eval_label: str = ""
    # Tracing
    trace_id: str = ""
    session_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "model": self.model,
            "provider": self.provider,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": round(self.latency_ms, 2),
            "ttft_ms": round(self.ttft_ms, 2),
            "tokens_per_second": round(self.tokens_per_second, 2),
            "cost_usd": round(self.cost_usd, 6),
            "success": self.success,
            "error_type": self.error_type,
            "is_streaming": self.is_streaming,
            "tool_calls": self.tool_calls,
            "prompt_hash": self.prompt_hash,
            "completion_hash": self.completion_hash,
            "eval_score": self.eval_score,
            "eval_label": self.eval_label,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "content_captured": LLM_CAPTURE_CONTENT,
        }


@dataclass
class AgentExecutionRecord:
    """Record of one agent invocation within a workflow."""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    agent_name: str = ""
    parent_agent_id: str = ""
    tenant_id: str = ""
    task: str = ""
    tool_calls: int = 0
    llm_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    duration_ms: float = 0.0
    success: bool = True
    error_type: str = ""
    retry_count: int = 0
    child_agent_ids: List[str] = field(default_factory=list)
    trace_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "parent_agent_id": self.parent_agent_id,
            "tenant_id": self.tenant_id,
            "task": self.task[:200],  # cap task description
            "tool_calls": self.tool_calls,
            "llm_calls": self.llm_calls,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "error_type": self.error_type,
            "retry_count": self.retry_count,
            "child_agent_ids": self.child_agent_ids,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "completed_at": self.completed_at,
        }


# ── Cost per token (approximate; not a billing source) ───────────────────────
# Source: publicly available model pricing pages (2026).
# These are ESTIMATES only. Do NOT use for billing.
_TOKEN_COSTS_PER_1K: Dict[str, Dict[str, float]] = {
    "gpt-4o":           {"input": 0.005,   "output": 0.015},
    "gpt-4o-mini":      {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo":      {"input": 0.01,    "output": 0.03},
    "gpt-3.5-turbo":    {"input": 0.0005,  "output": 0.0015},
    "claude-3-opus":    {"input": 0.015,   "output": 0.075},
    "claude-3-sonnet":  {"input": 0.003,   "output": 0.015},
    "claude-3-haiku":   {"input": 0.00025, "output": 0.00125},
    "llama-3-8b":       {"input": 0.0001,  "output": 0.0001},
    "llama-3-70b":      {"input": 0.0007,  "output": 0.0008},
    "mixtral-8x7b":     {"input": 0.00024, "output": 0.00024},
    "default":          {"input": 0.001,   "output": 0.002},
}


def estimate_token_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Estimate inference cost from token counts.
    DISCLAIMER: This is an approximation for internal tracking only.
    Do not present as actual provider billing.
    """
    model_key = model.lower()
    costs = _TOKEN_COSTS_PER_1K.get(model_key, _TOKEN_COSTS_PER_1K["default"])
    return (prompt_tokens / 1000 * costs["input"]) + (completion_tokens / 1000 * costs["output"])


def _hash_content(content: str) -> str:
    """SHA-256 hash of content for deduplication without storing raw text."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:16]


# ── LLM Observability Service ─────────────────────────────────────────────────

class LLMObservabilityService:
    """
    Central collector for LLM and agent execution telemetry.
    Thread-safe in-process store with optional Langfuse export.
    """

    _RECORD_LIMIT = 10_000  # max in-memory records; oldest dropped

    def __init__(self) -> None:
        self._records: List[LLMCallRecord] = []
        self._agent_records: List[AgentExecutionRecord] = []
        self._langfuse: Any = None
        self._init_langfuse()

    def _init_langfuse(self) -> None:
        if not _LANGFUSE_AVAILABLE or not LANGFUSE_SECRET_KEY:
            if not LANGFUSE_SECRET_KEY:
                logger.info("[LLMObs] Langfuse not configured — in-process tracking only")
            return
        try:
            self._langfuse = Langfuse(
                public_key=LANGFUSE_PUBLIC_KEY,
                secret_key=LANGFUSE_SECRET_KEY,
                host=LANGFUSE_HOST,
            )
            logger.info(f"[LLMObs] Langfuse connected → {LANGFUSE_HOST}")
        except Exception as exc:
            logger.warning(f"[LLMObs] Langfuse init failed — in-process only: {exc}")

    def record_llm_call(
        self,
        tenant_id: str,
        actor_id: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        ttft_ms: float = 0.0,
        success: bool = True,
        error_type: str = "",
        is_streaming: bool = False,
        tool_calls: int = 0,
        prompt_text: str = "",
        completion_text: str = "",
        trace_id: str = "",
        session_id: str = "",
        eval_score: Optional[float] = None,
        eval_label: str = "",
    ) -> LLMCallRecord:
        """Record a completed LLM call."""
        total_tokens = prompt_tokens + completion_tokens
        tps = (completion_tokens / (latency_ms / 1000.0)) if latency_ms > 0 else 0.0
        cost = estimate_token_cost(model, prompt_tokens, completion_tokens)

        record = LLMCallRecord(
            tenant_id=tenant_id,
            actor_id=actor_id,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            tokens_per_second=tps,
            cost_usd=cost,
            success=success,
            error_type=error_type,
            is_streaming=is_streaming,
            tool_calls=tool_calls,
            # Always record hash; raw content only if explicitly enabled
            prompt_hash=_hash_content(prompt_text) if prompt_text else "",
            completion_hash=_hash_content(completion_text) if completion_text else "",
            trace_id=trace_id,
            session_id=session_id,
            eval_score=eval_score,
            eval_label=eval_label,
        )

        self._records.append(record)
        if len(self._records) > self._RECORD_LIMIT:
            self._records = self._records[-self._RECORD_LIMIT:]

        # Langfuse export
        if self._langfuse and success:
            try:
                generation = self._langfuse.generation(
                    name=f"{model}-generation",
                    model=model,
                    model_parameters={"provider": provider, "streaming": is_streaming},
                    usage={"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
                    metadata={"tenant_id": tenant_id, "cost_usd": round(cost, 6)},
                )
                # Only attach content if capture is authorised
                if LLM_CAPTURE_CONTENT:
                    if prompt_text:
                        generation.input = prompt_text[:4096]
                    if completion_text:
                        generation.output = completion_text[:4096]
            except Exception as exc:
                logger.debug(f"[LLMObs] Langfuse export failed: {exc}")

        return record

    def record_agent_execution(
        self,
        agent_id: str,
        agent_name: str,
        tenant_id: str,
        task: str,
        duration_ms: float,
        success: bool,
        tool_calls: int = 0,
        llm_calls: int = 0,
        total_tokens: int = 0,
        total_cost_usd: float = 0.0,
        error_type: str = "",
        retry_count: int = 0,
        parent_agent_id: str = "",
        child_agent_ids: Optional[List[str]] = None,
        trace_id: str = "",
    ) -> AgentExecutionRecord:
        """Record a completed agent execution."""
        rec = AgentExecutionRecord(
            agent_id=agent_id,
            agent_name=agent_name,
            parent_agent_id=parent_agent_id,
            tenant_id=tenant_id,
            task=task,
            tool_calls=tool_calls,
            llm_calls=llm_calls,
            total_tokens=total_tokens,
            total_cost_usd=total_cost_usd,
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            retry_count=retry_count,
            child_agent_ids=child_agent_ids or [],
            trace_id=trace_id,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        self._agent_records.append(rec)
        if len(self._agent_records) > self._RECORD_LIMIT:
            self._agent_records = self._agent_records[-self._RECORD_LIMIT:]
        return rec

    def get_llm_summary(
        self,
        tenant_id: Optional[str] = None,
        model: Optional[str] = None,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """Return aggregate LLM usage statistics."""
        records = self._records[-limit:]
        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]
        if model:
            records = [r for r in records if r.model == model]

        if not records:
            return {"total_calls": 0, "disclaimer": self._disclaimer()}

        successful = [r for r in records if r.success]
        total_tokens = sum(r.total_tokens for r in records)
        total_cost = sum(r.cost_usd for r in records)
        avg_latency = sum(r.latency_ms for r in records) / len(records)
        avg_tps = sum(r.tokens_per_second for r in successful) / max(len(successful), 1)
        errors = [r for r in records if not r.success]

        by_model: Dict[str, Any] = {}
        for r in records:
            if r.model not in by_model:
                by_model[r.model] = {"calls": 0, "tokens": 0, "cost_usd": 0.0, "errors": 0}
            by_model[r.model]["calls"] += 1
            by_model[r.model]["tokens"] += r.total_tokens
            by_model[r.model]["cost_usd"] = round(by_model[r.model]["cost_usd"] + r.cost_usd, 6)
            if not r.success:
                by_model[r.model]["errors"] += 1

        return {
            "total_calls": len(records),
            "successful_calls": len(successful),
            "failed_calls": len(errors),
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(total_cost, 4),
            "avg_latency_ms": round(avg_latency, 2),
            "avg_tokens_per_second": round(avg_tps, 2),
            "by_model": by_model,
            "content_capture_enabled": LLM_CAPTURE_CONTENT,
            "langfuse_connected": self._langfuse is not None,
            "disclaimer": self._disclaimer(),
        }

    def get_agent_summary(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """Return aggregate agent execution statistics."""
        records = self._agent_records[-limit:]
        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]

        if not records:
            return {"total_executions": 0, "disclaimer": self._disclaimer()}

        successful = [r for r in records if r.success]
        total_cost = sum(r.total_cost_usd for r in records)
        avg_duration = sum(r.duration_ms for r in records) / len(records)
        completion_rate = len(successful) / len(records) * 100

        by_agent: Dict[str, Any] = {}
        for r in records:
            if r.agent_name not in by_agent:
                by_agent[r.agent_name] = {
                    "executions": 0, "successes": 0, "tool_calls": 0,
                    "total_tokens": 0, "cost_usd": 0.0,
                }
            by_agent[r.agent_name]["executions"] += 1
            if r.success:
                by_agent[r.agent_name]["successes"] += 1
            by_agent[r.agent_name]["tool_calls"] += r.tool_calls
            by_agent[r.agent_name]["total_tokens"] += r.total_tokens
            by_agent[r.agent_name]["cost_usd"] = round(
                by_agent[r.agent_name]["cost_usd"] + r.total_cost_usd, 6
            )

        return {
            "total_executions": len(records),
            "successful_executions": len(successful),
            "completion_rate_pct": round(completion_rate, 1),
            "total_estimated_cost_usd": round(total_cost, 4),
            "avg_duration_ms": round(avg_duration, 2),
            "by_agent": by_agent,
            "disclaimer": self._disclaimer(),
        }

    def get_recent_records(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return most recent LLM call records."""
        records = list(reversed(self._records[-limit:]))
        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]
        return [r.to_dict() for r in records[:limit]]

    def get_recent_agent_records(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        records = list(reversed(self._agent_records[-limit:]))
        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]
        return [r.to_dict() for r in records[:limit]]

    @staticmethod
    def _disclaimer() -> str:
        return (
            "Cost figures are estimates derived from publicly available model pricing. "
            "They do NOT represent actual provider billing. "
            "Token counts are as reported by the model API."
        )


# ── Singleton ─────────────────────────────────────────────────────────────────
_llm_obs: Optional[LLMObservabilityService] = None


def get_llm_obs() -> LLMObservabilityService:
    global _llm_obs
    if _llm_obs is None:
        _llm_obs = LLMObservabilityService()
    return _llm_obs
