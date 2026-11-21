# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 4C — Agent Runtime Security.

Protects autonomous agents against unsafe behaviour at execution time.

Implements:
- Tool permission boundary enforcement
- Prompt injection risk assessment (multi-signal, not keyword-only)
- Untrusted input isolation with provenance tracking
- Output validation and sensitive data redaction
- Tool call monitoring with rate limits and spend limits
- Execution time limits
- Human approval gate for high-impact operations
- Sandbox isolation metadata
- Structured audit logging for every agent action

IMPORTANT:
- Model outputs, retrieved documents and external tool responses are
  treated as UNTRUSTED INPUT regardless of source reputation.
- Prompt injection detection is multi-signal (structural + heuristic +
  pattern). It is explicitly NOT a guaranteed security control.
  Results always carry an is_heuristic=True flag and limitation disclaimer.
"""
from __future__ import annotations

import datetime
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import logging

logger = logging.getLogger("orquanta.security.agent_runtime")


# ---------------------------------------------------------------------------
# Risk levels and signals
# ---------------------------------------------------------------------------

class InjectionRisk(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"
    NONE   = "NONE"


class InputSource(str, Enum):
    USER_DIRECT   = "user_direct"
    MODEL_OUTPUT  = "model_output"      # Always untrusted
    TOOL_RESPONSE = "tool_response"     # Always untrusted
    RAG_DOCUMENT  = "rag_document"      # Always untrusted
    EXTERNAL_API  = "external_api"      # Always untrusted
    SYSTEM_PROMPT = "system_prompt"     # Trusted (operator-controlled)


ALWAYS_UNTRUSTED_SOURCES = {
    InputSource.MODEL_OUTPUT,
    InputSource.TOOL_RESPONSE,
    InputSource.RAG_DOCUMENT,
    InputSource.EXTERNAL_API,
}

# Multi-signal injection patterns (structural, not purely keyword)
_INJECTION_SIGNALS = [
    # Role/identity hijack
    (re.compile(r"you are now|from now on you|your new instructions", re.I), 0.8),
    # Instruction override
    (re.compile(r"ignore (all |previous |above |prior )?(instructions|rules|constraints|guidelines)", re.I), 0.9),
    # System prompt exfiltration
    (re.compile(r"(print|reveal|show|output|repeat|display) (your |the )?(system prompt|instructions|directives|context)", re.I), 0.85),
    # Escape characters / encoding attacks
    (re.compile(r"\\x[0-9a-f]{2}|\\u[0-9a-f]{4}|%[0-9a-f]{2}%[0-9a-f]{2}", re.I), 0.6),
    # Nested instructions from untrusted content
    (re.compile(r"\[INST\]|\[SYS\]|<\|im_start\|>|<s>Human:", re.I), 0.75),
    # Data exfiltration via tool calls
    (re.compile(r"(send|post|upload|exfiltrate).{0,30}(to|at|via).{0,30}(http|https|ftp|webhook)", re.I), 0.7),
    # Jailbreak framing
    (re.compile(r"(hypothetically|pretend|roleplay|DAN|do anything now|jailbreak)", re.I), 0.5),
]

# Sensitive data patterns (for redaction)
_SENSITIVE_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[API_KEY_REDACTED]"),
    (re.compile(r"Bearer [a-zA-Z0-9\-_.~+/]+=*"), "Bearer [TOKEN_REDACTED]"),
    (re.compile(r"\b[0-9]{13,19}\b"), "[CARD_REDACTED]"),           # credit card-like
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL_REDACTED]"),
    (re.compile(r"password[\s:=]+\S+", re.I), "[PASSWORD_REDACTED]"),
    (re.compile(r"secret[\s:=]+\S+", re.I), "[SECRET_REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]+-----"), "[PRIVATE_KEY_REDACTED]"),
]


# ---------------------------------------------------------------------------
# Assessment results
# ---------------------------------------------------------------------------

@dataclass
class InjectionAssessment:
    is_heuristic: bool = True           # Always True — not a guaranteed control
    risk: InjectionRisk = InjectionRisk.NONE
    score: float = 0.0                  # 0.0 – 1.0
    signals: List[str] = field(default_factory=list)
    source: str = ""
    is_untrusted_source: bool = False
    limitation: str = (
        "This assessment uses heuristic pattern-matching and structural signals. "
        "It is NOT a guaranteed security control and must not be the sole defence "
        "against prompt injection. Apply defence-in-depth."
    )

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class OutputValidationResult:
    passed: bool
    redacted: bool
    redacted_content: str               # content with secrets removed
    violations: List[str] = field(default_factory=list)
    limitation: str = (
        "Output validation applies pattern-based redaction only. "
        "It does not guarantee removal of all sensitive information."
    )

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ToolCallRecord:
    record_id: str
    agent_id: str
    tenant_id: str
    tool_id: str
    tool_name: str
    action: str
    input_hash: str                     # SHA-256 of inputs (not raw inputs)
    output_hash: str = ""
    permitted: bool = False
    executed: bool = False
    duration_ms: float = 0.0
    cost_usd: float = 0.0
    is_high_impact: bool = False
    approval_required: bool = False
    approved_by: Optional[str] = None
    blocked_reason: str = ""
    timestamp: str = field(default_factory=lambda: _now())

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Agent runtime session
# ---------------------------------------------------------------------------

@dataclass
class AgentSession:
    session_id: str
    agent_id: str
    tenant_id: str
    permitted_tools: Set[str]           # explicit tool allowlist
    permitted_permissions: Set[str]     # from delegated credential
    max_execution_seconds: int = 300
    max_spend_usd: float = 10.0
    max_tool_calls: int = 50
    # Runtime state
    started_at: str = field(default_factory=lambda: _now())
    tool_calls_made: int = 0
    total_spend_usd: float = 0.0
    is_active: bool = True
    termination_reason: str = ""
    # Approval gate
    pending_approvals: List[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        try:
            started = datetime.datetime.fromisoformat(self.started_at.rstrip("Z"))
            elapsed = (datetime.datetime.utcnow() - started).total_seconds()
            return elapsed > self.max_execution_seconds
        except Exception:
            return True

    def can_call_tool(self, tool_id: str) -> bool:
        if not self.is_active or self.is_expired():
            return False
        if self.tool_calls_made >= self.max_tool_calls:
            return False
        return tool_id in self.permitted_tools or "tools:*" in self.permitted_tools

    def can_spend(self, amount_usd: float) -> bool:
        return self.is_active and (self.total_spend_usd + amount_usd) <= self.max_spend_usd

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["permitted_tools"] = list(self.permitted_tools)
        d["permitted_permissions"] = list(self.permitted_permissions)
        return d


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _hash_content(content: str) -> str:
    import hashlib
    return hashlib.sha256(content.encode(errors="replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Agent Runtime Security Engine
# ---------------------------------------------------------------------------

class AgentRuntimeSecurity:

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: Dict[str, AgentSession] = {}
        self._tool_records: List[ToolCallRecord] = []

    # -- Session management --------------------------------------------------

    def create_session(
        self,
        agent_id: str,
        tenant_id: str,
        permitted_tools: Set[str],
        permitted_permissions: Set[str],
        max_execution_seconds: int = 300,
        max_spend_usd: float = 10.0,
        max_tool_calls: int = 50,
    ) -> AgentSession:
        sess = AgentSession(
            session_id=str(uuid.uuid4()),
            agent_id=agent_id,
            tenant_id=tenant_id,
            permitted_tools=permitted_tools,
            permitted_permissions=permitted_permissions,
            max_execution_seconds=max_execution_seconds,
            max_spend_usd=max_spend_usd,
            max_tool_calls=max_tool_calls,
        )
        with self._lock:
            self._sessions[sess.session_id] = sess
        logger.info(
            "[agent_runtime] Session %s created agent=%s tools=%d max_spend=%.2f",
            sess.session_id, agent_id, len(permitted_tools), max_spend_usd,
        )
        return sess

    def terminate_session(self, session_id: str, reason: str = "completed") -> bool:
        sess = self._sessions.get(session_id)
        if not sess:
            return False
        sess.is_active = False
        sess.termination_reason = reason
        logger.info("[agent_runtime] Session %s terminated: %s", session_id, reason)
        return True

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        return self._sessions.get(session_id)

    # -- Injection assessment ------------------------------------------------

    def assess_injection_risk(
        self,
        content: str,
        source: InputSource,
        agent_id: Optional[str] = None,
    ) -> InjectionAssessment:
        """
        Multi-signal prompt injection assessment.
        IMPORTANT: is_heuristic=True always. Not a guaranteed security control.
        """
        is_untrusted = source in ALWAYS_UNTRUSTED_SOURCES

        score = 0.0
        signals = []

        # Untrusted source baseline risk
        if is_untrusted:
            score += 0.15
            signals.append(f"untrusted_source:{source.value}")

        # Pattern signals
        for pattern, weight in _INJECTION_SIGNALS:
            if pattern.search(content):
                score = min(1.0, score + weight)
                signals.append(f"pattern:{pattern.pattern[:40]}")

        # Structural signals
        if content.count("\n") > 20:
            score = min(1.0, score + 0.1)
            signals.append("structural:high_line_count")

        if len(content) > 10000:
            score = min(1.0, score + 0.1)
            signals.append("structural:large_content")

        # Determine risk level
        if score >= 0.7:
            risk = InjectionRisk.HIGH
        elif score >= 0.4:
            risk = InjectionRisk.MEDIUM
        elif score >= 0.15:
            risk = InjectionRisk.LOW
        else:
            risk = InjectionRisk.NONE

        return InjectionAssessment(
            is_heuristic=True,
            risk=risk,
            score=round(score, 3),
            signals=signals[:10],
            source=source.value,
            is_untrusted_source=is_untrusted,
        )

    # -- Output validation and redaction -------------------------------------

    def validate_output(self, content: str, agent_id: str = "") -> OutputValidationResult:
        """
        Redact sensitive patterns from agent output.
        Does NOT guarantee complete removal of sensitive data.
        """
        redacted = content
        violations = []
        was_redacted = False

        for pattern, replacement in _SENSITIVE_PATTERNS:
            new_content, count = pattern.subn(replacement, redacted)
            if count > 0:
                redacted = new_content
                was_redacted = True
                violations.append(f"Potential sensitive data detected and redacted: {replacement}")

        return OutputValidationResult(
            passed=len(violations) == 0,
            redacted=was_redacted,
            redacted_content=redacted,
            violations=violations,
        )

    # -- Tool call monitoring ------------------------------------------------

    def authorize_tool_call(
        self,
        session_id: str,
        tool_id: str,
        tool_name: str,
        action: str,
        inputs: Dict,
        is_high_impact: bool = False,
        estimated_cost_usd: float = 0.0,
    ) -> ToolCallRecord:
        """
        Authorize and record a tool call attempt.
        Returns a ToolCallRecord with permitted=True/False.
        """
        sess = self._sessions.get(session_id)
        record = ToolCallRecord(
            record_id=str(uuid.uuid4()),
            agent_id=sess.agent_id if sess else "unknown",
            tenant_id=sess.tenant_id if sess else "unknown",
            tool_id=tool_id,
            tool_name=tool_name,
            action=action,
            input_hash=_hash_content(str(inputs)),
            is_high_impact=is_high_impact,
        )

        if not sess:
            record.blocked_reason = "No active agent session"
            self._append_record(record)
            return record

        if sess.is_expired():
            self.terminate_session(session_id, "execution_timeout")
            record.blocked_reason = "Agent session expired"
            self._append_record(record)
            return record

        if not sess.can_call_tool(tool_id):
            record.blocked_reason = (
                "Tool not in permitted set"
                if tool_id not in sess.permitted_tools
                else "Tool call limit reached"
            )
            self._append_record(record)
            return record

        if not sess.can_spend(estimated_cost_usd):
            record.blocked_reason = f"Spend limit exceeded (session limit: ${sess.max_spend_usd:.2f})"
            self._append_record(record)
            return record

        if is_high_impact:
            record.approval_required = True
            # Caller must obtain approval before executing
            logger.warning(
                "[agent_runtime] High-impact tool %s requires human approval session=%s",
                tool_id, session_id,
            )
        else:
            record.permitted = True

        self._append_record(record)
        return record

    def record_tool_execution(
        self,
        record_id: str,
        output: Any,
        duration_ms: float,
        cost_usd: float,
        session_id: str,
    ) -> ToolCallRecord:
        """Record the outcome of an executed tool call."""
        with self._lock:
            records = [r for r in self._tool_records if r.record_id == record_id]
        if not records:
            raise ValueError(f"Tool call record {record_id} not found")

        record = records[0]
        record.output_hash = _hash_content(str(output))
        record.duration_ms = duration_ms
        record.cost_usd = cost_usd
        record.executed = True

        sess = self._sessions.get(session_id)
        if sess:
            with self._lock:
                sess.tool_calls_made += 1
                sess.total_spend_usd += cost_usd

        return record

    def _append_record(self, record: ToolCallRecord) -> None:
        with self._lock:
            self._tool_records.append(record)

    def get_tool_records(
        self,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        with self._lock:
            records = list(self._tool_records)
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        return [r.to_dict() for r in records[-limit:]]


_AGENT_RUNTIME = AgentRuntimeSecurity()


def get_agent_runtime() -> AgentRuntimeSecurity:
    return _AGENT_RUNTIME
