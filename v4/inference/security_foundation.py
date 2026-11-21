# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta AI Security & Governance Foundation — Phase 3H Objective 7
====================================================================
Foundational security layer: policy engine, prompt safety heuristics,
supply-chain checks, tenant isolation, and structured audit logging.

IMPORTANT LIMITATIONS (must not be misrepresented):
- Prompt injection heuristics are NOT guaranteed protection.
  Determined adversaries can bypass keyword and pattern filters.
  This is a risk signal, not a security boundary.
- Supply chain checks verify revision strings and optional checksums.
  They do not audit model weights cryptographically.
- This is a FOUNDATION layer — not a complete AI security solution.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orquanta.inference.security")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Severity + event types
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    INFO     = "INFO"
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class EventType(str, Enum):
    PROMPT_INJECTION_INDICATOR  = "PROMPT_INJECTION_INDICATOR"
    TENANT_ISOLATION_VIOLATION  = "TENANT_ISOLATION_VIOLATION"
    SUPPLY_CHAIN_MISMATCH       = "SUPPLY_CHAIN_MISMATCH"
    BUDGET_EXCEEDED             = "BUDGET_EXCEEDED"
    RATE_LIMIT_HIT              = "RATE_LIMIT_HIT"
    UNAUTHORISED_SCOPE          = "UNAUTHORISED_SCOPE"
    POLICY_BLOCKED              = "POLICY_BLOCKED"
    POLICY_FLAGGED              = "POLICY_FLAGGED"
    AUDIT_LOG                   = "AUDIT_LOG"


# ---------------------------------------------------------------------------
# Security event
# ---------------------------------------------------------------------------

@dataclass
class SecurityEvent:
    event_id: str
    timestamp: str
    event_type: EventType
    severity: Severity
    user_id: Optional[str]
    model_id: Optional[str]
    detail: str
    mitigated: bool = True
    source_ip: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["severity"]   = self.severity.value
        return d


# ---------------------------------------------------------------------------
# Policy rules
# ---------------------------------------------------------------------------

class RuleType(str, Enum):
    PROMPT_FILTER    = "PROMPT_FILTER"
    CONTENT_FILTER   = "CONTENT_FILTER"
    RATE             = "RATE"
    BUDGET           = "BUDGET"
    MODEL_ALLOWLIST  = "MODEL_ALLOWLIST"
    TENANT_ISOLATION = "TENANT_ISOLATION"


class RuleAction(str, Enum):
    ALLOW  = "ALLOW"
    BLOCK  = "BLOCK"
    REVIEW = "REVIEW"
    ALERT  = "ALERT"


@dataclass
class PolicyRule:
    rule_id: str
    rule_type: RuleType
    action: RuleAction
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class AISecurityPolicy:
    policy_id: str
    name: str
    rules: List[PolicyRule]
    enabled: bool = True
    description: str = ""


# ---------------------------------------------------------------------------
# Prompt injection heuristics
# ---------------------------------------------------------------------------

# Common injection patterns (heuristic only — not guaranteed)
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+instructions?",
    r"you\s+are\s+now\s+a",
    r"act\s+as\s+(if\s+you\s+are|a|an)",
    r"forget\s+everything",
    r"disregard\s+(your\s+)?(system\s+)?prompt",
    r"new\s+instructions?:",
    r"</?(system|prompt|context)>",
    r"(override|bypass)\s+(safety|guidelines|rules|filter)",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
    r"\\n\\n###\s*(new\s+)?instructions?",
    r"human:\s*assistant:",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _INJECTION_PATTERNS]


def check_prompt_injection_indicators(prompt: str) -> Dict[str, Any]:
    """
    Heuristic scan for prompt injection indicators.

    IMPORTANT: This is a heuristic signal, NOT guaranteed protection.
    Determined adversaries can bypass these patterns. Use as a risk
    signal for logging and human review — not as a security boundary.

    Returns:
        {
            "risk_score": float (0.0–1.0),
            "indicators": list of matched pattern descriptions,
            "is_heuristic": True,          # Always true — never claim complete protection
            "recommendation": str,
        }
    """
    indicators = []
    for i, pattern in enumerate(_COMPILED_PATTERNS):
        if pattern.search(prompt):
            indicators.append(f"Pattern match #{i+1}: {_INJECTION_PATTERNS[i][:60]}")

    n = len(indicators)
    risk_score = min(1.0, n * 0.25)  # 4+ matches → score 1.0

    recommendation = "low risk" if risk_score < 0.25 else \
                     "monitor and log" if risk_score < 0.5 else \
                     "human review recommended" if risk_score < 0.75 else \
                     "consider blocking — high injection signal"

    return {
        "risk_score": round(risk_score, 2),
        "indicators": indicators,
        "indicator_count": n,
        "is_heuristic": True,
        "limitation": (
            "This is a heuristic pattern-match only. It cannot guarantee detection "
            "of all prompt injection attempts. Do not rely on this as a sole security control."
        ),
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# Supply chain verification
# ---------------------------------------------------------------------------

def check_model_supply_chain(
    model_id: str,
    revision: str,
    expected_revision: Optional[str] = None,
    expected_checksum: Optional[str] = None,
    actual_checksum: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verify model revision and optional checksum.

    Args:
        model_id: HuggingFace model identifier
        revision: Actual revision/commit SHA reported by provider
        expected_revision: Expected revision (from model registry)
        expected_checksum: Expected SHA-256 of model config file
        actual_checksum: Actual SHA-256 computed after download

    Returns dict with verification status and findings.
    """
    findings = []
    passed = True

    if expected_revision and revision != expected_revision:
        findings.append(
            f"Revision mismatch: expected '{expected_revision}', got '{revision}'. "
            "Model may have been updated or substituted."
        )
        passed = False

    if expected_checksum and actual_checksum:
        if expected_checksum != actual_checksum:
            findings.append(
                f"Checksum mismatch. Expected: {expected_checksum[:16]}... "
                f"Actual: {actual_checksum[:16]}... Model integrity check FAILED."
            )
            passed = False
        else:
            findings.append("Checksum verified.")

    if not expected_revision and not expected_checksum:
        findings.append(
            "No expected revision or checksum provided. "
            "Supply chain verification is advisory only — cannot confirm model integrity."
        )

    return {
        "model_id":           model_id,
        "revision":           revision,
        "expected_revision":  expected_revision,
        "checksum_verified":  (expected_checksum is not None and actual_checksum is not None),
        "passed":             passed,
        "findings":           findings,
        "limitation":         "Revision and checksum checks do not audit model weights for tampering.",
    }


# ---------------------------------------------------------------------------
# Security evaluator
# ---------------------------------------------------------------------------

class SecurityEvaluator:
    """
    Evaluates inference requests against security policies.
    Records all events to the security audit log.
    """

    def __init__(self) -> None:
        self._events: List[SecurityEvent] = []
        self._policies: List[AISecurityPolicy] = [_default_policy()]

    def log_security_event(
        self,
        event_type: EventType,
        severity: Severity,
        detail: str,
        user_id: Optional[str] = None,
        model_id: Optional[str] = None,
        mitigated: bool = True,
        source_ip: Optional[str] = None,
    ) -> SecurityEvent:
        ev = SecurityEvent(
            event_id=str(uuid.uuid4()),
            timestamp=_now(),
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            model_id=model_id,
            detail=detail,
            mitigated=mitigated,
            source_ip=source_ip,
        )
        self._events.append(ev)
        log_fn = logger.warning if severity in (Severity.HIGH, Severity.CRITICAL) else logger.info
        log_fn("[security] %s severity=%s user=%s: %s", event_type.value, severity.value, user_id, detail[:120])
        return ev

    def check_tenant_isolation(
        self,
        request_tenant_id: str,
        resource_tenant_id: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Hard enforcement: request_tenant_id must equal resource_tenant_id.
        Any mismatch is logged as HIGH severity and returns False.
        """
        if request_tenant_id == resource_tenant_id:
            return True

        self.log_security_event(
            event_type=EventType.TENANT_ISOLATION_VIOLATION,
            severity=Severity.HIGH,
            detail=(
                f"Tenant isolation violation: request tenant '{request_tenant_id}' "
                f"attempted to access resource owned by '{resource_tenant_id}'"
            ),
            user_id=user_id,
            mitigated=True,
        )
        return False

    def evaluate_prompt(
        self,
        prompt: str,
        user_id: Optional[str] = None,
        model_id: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a prompt for injection indicators.
        Logs medium/high risk events. Returns heuristic assessment.
        """
        result = check_prompt_injection_indicators(prompt)

        if result["risk_score"] >= 0.5:
            self.log_security_event(
                event_type=EventType.PROMPT_INJECTION_INDICATOR,
                severity=Severity.MEDIUM if result["risk_score"] < 0.75 else Severity.HIGH,
                detail=f"Prompt injection indicators detected (score={result['risk_score']}): {result['indicators'][:3]}",
                user_id=user_id,
                model_id=model_id,
                mitigated=False,  # Heuristic only — may be false positive
                source_ip=source_ip,
            )

        return result

    def evaluate_supply_chain(
        self,
        model_id: str,
        revision: str,
        expected_revision: Optional[str] = None,
        expected_checksum: Optional[str] = None,
        actual_checksum: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = check_model_supply_chain(
            model_id, revision, expected_revision, expected_checksum, actual_checksum
        )
        if not result["passed"]:
            self.log_security_event(
                event_type=EventType.SUPPLY_CHAIN_MISMATCH,
                severity=Severity.HIGH,
                detail=f"Supply chain check failed for {model_id}: {result['findings']}",
                model_id=model_id,
                mitigated=False,
            )
        return result

    def get_security_events(
        self,
        severity: Optional[Severity] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        events = self._events
        if severity:
            events = [e for e in events if e.severity == severity]
        return [e.to_dict() for e in events[-limit:]]


def _default_policy() -> AISecurityPolicy:
    return AISecurityPolicy(
        policy_id="default",
        name="OrQuanta Default Security Policy",
        description="Default policy applied to all inference requests.",
        rules=[
            PolicyRule("r1", RuleType.PROMPT_FILTER,    RuleAction.ALERT,  {}, "Log prompt injection indicators"),
            PolicyRule("r2", RuleType.TENANT_ISOLATION,  RuleAction.BLOCK,  {}, "Hard-block cross-tenant access"),
            PolicyRule("r3", RuleType.BUDGET,            RuleAction.BLOCK,  {"hard_limit": True}, "Block on budget exhaustion"),
            PolicyRule("r4", RuleType.RATE,              RuleAction.BLOCK,  {}, "Block on rate limit exceeded"),
        ],
        enabled=True,
    )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_evaluator = SecurityEvaluator()


def get_security_evaluator() -> SecurityEvaluator:
    return _evaluator
