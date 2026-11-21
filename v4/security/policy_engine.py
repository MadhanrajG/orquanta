# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 4A — Central Policy Decision and Enforcement Engine (PDP/PEP).

Every sensitive AI operation passes through this module before execution.

Architecture:
  PolicyEngine (PDP) — evaluates policies against context, returns Decision
  Enforcer       — PEP that wraps callables; raises PolicyDeniedError on DENY
  PolicyStore    — in-memory policy registry (Phase 5 migrates to DB)
  AuditBus       — append-only event log; protected from deletion

Decisions:
  ALLOW | DENY | REQUIRE_APPROVAL | RESTRICTED | REVIEW_REQUIRED

Every decision carries: actor, resource, action, policy_id, reason, version, timestamp.
No system actor may impersonate a human approval.
"""
from __future__ import annotations

import datetime
import hashlib
import threading
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar

import logging

logger = logging.getLogger("orquanta.security.policy")

F = TypeVar("F", bound=Callable)


# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------

class Decision(str, Enum):
    ALLOW            = "ALLOW"
    DENY             = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    RESTRICTED       = "RESTRICTED"
    REVIEW_REQUIRED  = "REVIEW_REQUIRED"


class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    INFO     = "INFO"


# ---------------------------------------------------------------------------
# Policy definition
# ---------------------------------------------------------------------------

@dataclass
class Policy:
    policy_id: str
    name: str
    version: str
    description: str
    resource_type: str          # "model" | "agent" | "tool" | "data" | "gpu" | "*"
    action_pattern: str         # glob-style: "deploy" | "infer:*" | "*"
    decision: Decision
    conditions: Dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    requires_approval_role: Optional[str] = None  # e.g. "security-admin"
    enabled: bool = True
    created_at: str = field(default_factory=lambda: _now())
    created_by: str = "system"

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Decision result
# ---------------------------------------------------------------------------

@dataclass
class PolicyResult:
    decision_id: str
    decision: Decision
    policy_id: str
    policy_name: str
    policy_version: str
    actor_id: str
    actor_type: str             # "human" | "agent" | "service" | "api_key"
    resource_type: str
    resource_id: str
    action: str
    reason: str
    risk_level: RiskLevel
    requires_approval: bool
    approval_role: Optional[str]
    context_hash: str           # SHA-256 of context dict for evidence
    timestamp: str
    tenant_id: str
    is_mock: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Audit event (append-only)
# ---------------------------------------------------------------------------

@dataclass
class AuditEvent:
    event_id: str
    event_type: str
    actor_id: str
    actor_type: str
    tenant_id: str
    resource_type: str
    resource_id: str
    action: str
    decision: str
    policy_id: str
    policy_version: str
    outcome: str                # "executed" | "blocked" | "pending_approval"
    evidence: Dict[str, Any]
    timestamp: str
    # immutable flag — events are never deleted, only appended
    _immutable: bool = field(default=True, repr=False)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d.pop("_immutable", None)
        return d


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PolicyDeniedError(PermissionError):
    def __init__(self, result: PolicyResult):
        self.result = result
        super().__init__(
            f"[{result.policy_id}] {result.decision}: {result.reason} "
            f"(actor={result.actor_id}, resource={result.resource_id}, action={result.action})"
        )


class ApprovalRequiredError(Exception):
    def __init__(self, result: PolicyResult):
        self.result = result
        super().__init__(
            f"Human approval required (role={result.approval_role}) for "
            f"actor={result.actor_id} action={result.action} on {result.resource_id}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _context_hash(ctx: Dict) -> str:
    import json
    raw = json.dumps(ctx, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _matches(pattern: str, value: str) -> bool:
    """Simple glob: exact match or wildcard suffix (*). Case-insensitive."""
    if pattern == "*":
        return True
    if pattern.endswith(":*"):
        return value.startswith(pattern[:-2])
    if pattern.endswith("*"):
        return value.startswith(pattern[:-1])
    return pattern.lower() == value.lower()


# ---------------------------------------------------------------------------
# Audit Bus (append-only)
# ---------------------------------------------------------------------------

class AuditBus:
    """Central append-only audit log. Events are never deleted."""

    def __init__(self):
        self._lock = threading.Lock()
        self._events: List[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)
        logger.info(
            "[audit] %s actor=%s resource=%s/%s action=%s decision=%s outcome=%s",
            event.event_type, event.actor_id, event.resource_type,
            event.resource_id, event.action, event.decision, event.outcome,
        )

    def query(
        self,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        decision: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict]:
        with self._lock:
            events = list(self._events)
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        if actor_id:
            events = [e for e in events if e.actor_id == actor_id]
        if resource_type:
            events = [e for e in events if e.resource_type == resource_type]
        if decision:
            events = [e for e in events if e.decision == decision]
        return [e.to_dict() for e in events[-limit:]]

    def count(self) -> int:
        with self._lock:
            return len(self._events)


_AUDIT_BUS = AuditBus()


def get_audit_bus() -> AuditBus:
    return _AUDIT_BUS


# ---------------------------------------------------------------------------
# Policy Store
# ---------------------------------------------------------------------------

class PolicyStore:
    """In-memory policy registry. Phase 5 migrates to PostgreSQL."""

    def __init__(self):
        self._lock = threading.Lock()
        self._policies: Dict[str, Policy] = {}
        self._load_defaults()

    def _load_defaults(self):
        """Load built-in baseline policies."""
        defaults = [
            Policy(
                policy_id="p-model-deploy-review",
                name="Model Deployment Review",
                version="1.0",
                description="All model deployments require security review.",
                resource_type="model",
                action_pattern="deploy",
                decision=Decision.REQUIRE_APPROVAL,
                risk_level=RiskLevel.HIGH,
                requires_approval_role="security-admin",
                created_by="system",
            ),
            Policy(
                policy_id="p-agent-exec-restrict",
                name="Agent Execution Restrictions",
                version="1.0",
                description="Autonomous agents run with restricted permissions.",
                resource_type="agent",
                action_pattern="execute",
                decision=Decision.RESTRICTED,
                risk_level=RiskLevel.MEDIUM,
                created_by="system",
            ),
            Policy(
                policy_id="p-tool-high-impact",
                name="High-Impact Tool Approval",
                version="1.0",
                description="High-impact tool calls require human approval.",
                resource_type="tool",
                action_pattern="execute:high_impact",
                decision=Decision.REQUIRE_APPROVAL,
                risk_level=RiskLevel.HIGH,
                requires_approval_role="operator",
                created_by="system",
            ),
            Policy(
                policy_id="p-data-sensitive",
                name="Sensitive Data Access Control",
                version="1.0",
                description="Sensitive data access denied without explicit grant.",
                resource_type="data",
                action_pattern="read:sensitive",
                decision=Decision.DENY,
                risk_level=RiskLevel.CRITICAL,
                created_by="system",
            ),
            Policy(
                policy_id="p-gpu-spend-limit",
                name="GPU Spend Enforcement",
                version="1.0",
                description="GPU spend above tenant budget is blocked.",
                resource_type="gpu",
                action_pattern="provision",
                decision=Decision.ALLOW,
                conditions={"check_budget": True},
                risk_level=RiskLevel.MEDIUM,
                created_by="system",
            ),
            Policy(
                policy_id="p-model-infer-allow",
                name="Model Inference Allow",
                version="1.0",
                description="Authenticated inference requests are allowed.",
                resource_type="model",
                action_pattern="infer",
                decision=Decision.ALLOW,
                risk_level=RiskLevel.LOW,
                created_by="system",
            ),
            Policy(
                policy_id="p-mcp-unregistered-deny",
                name="Unregistered MCP Tool Deny",
                version="1.0",
                description="Unregistered MCP tools are denied execution.",
                resource_type="mcp_tool",
                action_pattern="execute",
                decision=Decision.DENY,
                risk_level=RiskLevel.HIGH,
                created_by="system",
            ),
            Policy(
                policy_id="p-cross-tenant-deny",
                name="Cross-Tenant Access Deny",
                version="1.0",
                description="Cross-tenant resource access is always denied.",
                resource_type="*",
                action_pattern="*",
                decision=Decision.DENY,
                conditions={"cross_tenant": True},
                risk_level=RiskLevel.CRITICAL,
                created_by="system",
            ),
        ]
        for p in defaults:
            self._policies[p.policy_id] = p

    def add(self, policy: Policy) -> Policy:
        with self._lock:
            self._policies[policy.policy_id] = policy
        logger.info("[policy_store] Added policy %s v%s", policy.policy_id, policy.version)
        return policy

    def get(self, policy_id: str) -> Optional[Policy]:
        return self._policies.get(policy_id)

    def list_all(self, resource_type: Optional[str] = None) -> List[Policy]:
        with self._lock:
            policies = list(self._policies.values())
        if resource_type:
            policies = [p for p in policies if p.resource_type in (resource_type, "*")]
        return [p for p in policies if p.enabled]

    def disable(self, policy_id: str) -> bool:
        with self._lock:
            p = self._policies.get(policy_id)
            if p:
                p.enabled = False
                return True
        return False


_POLICY_STORE = PolicyStore()


def get_policy_store() -> PolicyStore:
    return _POLICY_STORE


# ---------------------------------------------------------------------------
# Policy Engine (PDP)
# ---------------------------------------------------------------------------

class PolicyEngine:
    """
    Policy Decision Point.

    evaluate() selects the most specific applicable policy and returns a PolicyResult.
    Priority: exact resource_type > wildcard "*"; exact action > prefix wildcard.

    Cross-tenant access is always DENY regardless of other policies.
    """

    def __init__(self, store: Optional[PolicyStore] = None, bus: Optional[AuditBus] = None):
        self._store = store or _POLICY_STORE
        self._bus = bus or _AUDIT_BUS

    def evaluate(
        self,
        actor_id: str,
        actor_type: str,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        context: Optional[Dict] = None,
        resource_tenant_id: Optional[str] = None,
    ) -> PolicyResult:
        ctx = context or {}
        ctx_hash = _context_hash({
            "actor_id": actor_id, "resource_id": resource_id,
            "action": action, "tenant_id": tenant_id, **ctx,
        })

        # 1. Cross-tenant check always wins
        effective_resource_tenant = resource_tenant_id or tenant_id
        if effective_resource_tenant != tenant_id:
            return self._result(
                actor_id=actor_id, actor_type=actor_type, tenant_id=tenant_id,
                resource_type=resource_type, resource_id=resource_id, action=action,
                policy=self._store.get("p-cross-tenant-deny"),
                decision=Decision.DENY,
                reason="Cross-tenant access denied: resource belongs to another tenant.",
                ctx_hash=ctx_hash,
            )

        # 2. Find applicable policies (most specific wins)
        candidates = [
            p for p in self._store.list_all()
            if _matches(p.resource_type, resource_type)
            and _matches(p.action_pattern, action)
        ]

        # Sort: exact resource_type first, then exact action_pattern
        def _specificity(p: Policy) -> int:
            s = 0
            if p.resource_type == resource_type:
                s += 10
            if p.action_pattern == action:
                s += 5
            return s

        candidates.sort(key=_specificity, reverse=True)

        if not candidates:
            # Default deny if no policy matches
            return self._result(
                actor_id=actor_id, actor_type=actor_type, tenant_id=tenant_id,
                resource_type=resource_type, resource_id=resource_id, action=action,
                policy=None,
                decision=Decision.DENY,
                reason=f"No policy found for resource_type={resource_type} action={action}. Default deny.",
                ctx_hash=ctx_hash,
            )

        policy = candidates[0]

        # 3. Evaluate conditions
        decision = policy.decision
        reason = policy.description

        # Budget check override
        if policy.conditions.get("check_budget"):
            budget = ctx.get("tenant_budget_usd", 0)
            cost = ctx.get("estimated_cost_usd", 0)
            if cost > budget:
                decision = Decision.DENY
                reason = f"GPU spend ${cost:.2f} exceeds tenant budget ${budget:.2f}."

        return self._result(
            actor_id=actor_id, actor_type=actor_type, tenant_id=tenant_id,
            resource_type=resource_type, resource_id=resource_id, action=action,
            policy=policy, decision=decision, reason=reason, ctx_hash=ctx_hash,
        )

    def _result(
        self,
        actor_id: str,
        actor_type: str,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        policy: Optional[Policy],
        decision: Decision,
        reason: str,
        ctx_hash: str,
    ) -> PolicyResult:
        result = PolicyResult(
            decision_id=str(uuid.uuid4()),
            decision=decision,
            policy_id=policy.policy_id if policy else "default-deny",
            policy_name=policy.name if policy else "Default Deny",
            policy_version=policy.version if policy else "1.0",
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            reason=reason,
            risk_level=policy.risk_level if policy else RiskLevel.HIGH,
            requires_approval=decision == Decision.REQUIRE_APPROVAL,
            approval_role=policy.requires_approval_role if policy else None,
            context_hash=ctx_hash,
            timestamp=_now(),
            tenant_id=tenant_id,
        )

        # Emit to audit bus
        outcome = "pending_approval" if decision == Decision.REQUIRE_APPROVAL else (
            "blocked" if decision == Decision.DENY else "allowed"
        )
        self._bus.append(AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type="POLICY_DECISION",
            actor_id=actor_id,
            actor_type=actor_type,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            decision=decision.value,
            policy_id=result.policy_id,
            policy_version=result.policy_version,
            outcome=outcome,
            evidence={"decision_id": result.decision_id, "context_hash": ctx_hash},
            timestamp=result.timestamp,
        ))

        return result


# ---------------------------------------------------------------------------
# Enforcer (PEP)
# ---------------------------------------------------------------------------

class Enforcer:
    """
    Policy Enforcement Point.

    enforce() wraps a callable — raises PolicyDeniedError on DENY,
    ApprovalRequiredError on REQUIRE_APPROVAL.
    ALLOW, RESTRICTED, REVIEW_REQUIRED execute with appropriate logging.
    """

    def __init__(self, engine: Optional[PolicyEngine] = None):
        self._engine = engine or PolicyEngine()

    def enforce(
        self,
        actor_id: str,
        actor_type: str,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        context: Optional[Dict] = None,
        resource_tenant_id: Optional[str] = None,
        raise_on_deny: bool = True,
    ) -> PolicyResult:
        result = self._engine.evaluate(
            actor_id=actor_id,
            actor_type=actor_type,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            context=context,
            resource_tenant_id=resource_tenant_id,
        )

        if result.decision == Decision.DENY and raise_on_deny:
            raise PolicyDeniedError(result)

        if result.decision == Decision.REQUIRE_APPROVAL:
            raise ApprovalRequiredError(result)

        if result.decision == Decision.RESTRICTED:
            logger.warning(
                "[enforcer] RESTRICTED actor=%s action=%s resource=%s",
                actor_id, action, resource_id,
            )

        if result.decision == Decision.REVIEW_REQUIRED:
            logger.info(
                "[enforcer] REVIEW_REQUIRED actor=%s action=%s resource=%s",
                actor_id, action, resource_id,
            )

        return result


_ENGINE  = PolicyEngine()
_ENFORCER = Enforcer(_ENGINE)


def get_policy_engine() -> PolicyEngine:
    return _ENGINE


def get_enforcer() -> Enforcer:
    return _ENFORCER
