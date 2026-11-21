# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 4F — Governance Engine and Human Approvals.

Configurable policy-based governance with:
- Policy decisions: ALLOW | DENY | REQUIRE_APPROVAL | RESTRICTED | REVIEW_REQUIRED
- Human approval workflow with named approver tracking
- Approval queue with expiry and escalation
- Approval decisions immutably logged
- System actors explicitly forbidden from approving

Policy coverage:
- Model deployment, model usage, agent execution
- External API access, sensitive data access
- GPU spending, high-risk operations, enterprise restrictions

Every decision has: explanation, policy version, audit record.
No system actor may impersonate a human approval.
"""
from __future__ import annotations

import datetime
import threading
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger("orquanta.security.governance")

SYSTEM_ACTOR_IDS = {"system", "auto", "automated", "orquanta", ""}


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _default_expiry(hours: int = 24) -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=hours)).isoformat() + "Z"


# ---------------------------------------------------------------------------
# Approval states
# ---------------------------------------------------------------------------

class ApprovalStatus(str, Enum):
    PENDING   = "PENDING"
    APPROVED  = "APPROVED"
    REJECTED  = "REJECTED"
    EXPIRED   = "EXPIRED"
    CANCELLED = "CANCELLED"


class GovDecision(str, Enum):
    ALLOW            = "ALLOW"
    DENY             = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    RESTRICTED       = "RESTRICTED"
    REVIEW_REQUIRED  = "REVIEW_REQUIRED"


# ---------------------------------------------------------------------------
# Approval request
# ---------------------------------------------------------------------------

@dataclass
class ApprovalRequest:
    request_id: str
    operation_type: str             # "model_deploy" | "agent_execute" | "tool_exec" | ...
    resource_id: str
    resource_type: str
    actor_id: str
    tenant_id: str
    required_approver_role: str
    justification: str
    context: Dict[str, Any]
    risk_level: str
    policy_id: str
    policy_version: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_by: Optional[str] = None
    rejected_at: Optional[str] = None
    rejection_reason: str = ""
    created_at: str = field(default_factory=lambda: _now())
    expires_at: str = field(default_factory=lambda: _default_expiry(24))
    # Escalation tracking
    escalated: bool = False
    escalated_at: Optional[str] = None

    def is_expired(self) -> bool:
        try:
            exp = datetime.datetime.fromisoformat(self.expires_at.rstrip("Z"))
            return datetime.datetime.utcnow() > exp
        except Exception:
            return True

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Governance decision result
# ---------------------------------------------------------------------------

@dataclass
class GovDecisionResult:
    result_id: str
    decision: GovDecision
    operation_type: str
    resource_id: str
    actor_id: str
    tenant_id: str
    policy_id: str
    policy_version: str
    explanation: str
    risk_level: str
    requires_approval: bool
    approval_request_id: Optional[str]
    timestamp: str
    is_final: bool                  # False if pending approval

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Governance policy definition
# ---------------------------------------------------------------------------

@dataclass
class GovPolicy:
    policy_id: str
    name: str
    version: str
    operation_types: List[str]      # e.g. ["model_deploy", "model_usage"]
    decision: GovDecision
    conditions: Dict[str, Any]      # e.g. {"risk_level_gte": "HIGH"}
    required_approver_role: Optional[str] = None
    explanation_template: str = "Policy {policy_id} decision: {decision}"
    enabled: bool = True
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Governance engine
# ---------------------------------------------------------------------------

class GovernanceApprovalEngine:
    """
    Manages governance policies and approval workflows.
    All decisions are auditable and explanations are required.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._policies: Dict[str, GovPolicy] = {}
        self._requests: Dict[str, ApprovalRequest] = {}
        self._audit_log: List[Dict] = []
        self._load_default_policies()

    def _load_default_policies(self):
        defaults = [
            GovPolicy(
                policy_id="gov-model-deploy-high-risk",
                name="High-Risk Model Deployment",
                version="1.0",
                operation_types=["model_deploy"],
                decision=GovDecision.REQUIRE_APPROVAL,
                conditions={"risk_level_in": ["HIGH", "CRITICAL"]},
                required_approver_role="security-admin",
                explanation_template="High-risk model deployment requires security-admin approval.",
            ),
            GovPolicy(
                policy_id="gov-model-deploy-low-risk",
                name="Low-Risk Model Deployment",
                version="1.0",
                operation_types=["model_deploy"],
                decision=GovDecision.ALLOW,
                conditions={"risk_level_in": ["LOW", "MEDIUM"]},
                explanation_template="Low-risk model deployment allowed with standard review.",
            ),
            GovPolicy(
                policy_id="gov-agent-execute",
                name="Agent Execution Governance",
                version="1.0",
                operation_types=["agent_execute"],
                decision=GovDecision.RESTRICTED,
                conditions={},
                explanation_template="Agent execution permitted with runtime security controls.",
            ),
            GovPolicy(
                policy_id="gov-external-api",
                name="External API Access",
                version="1.0",
                operation_types=["external_api_access"],
                decision=GovDecision.REQUIRE_APPROVAL,
                conditions={"is_new_endpoint": True},
                required_approver_role="operator",
                explanation_template="New external API endpoint requires operator approval.",
            ),
            GovPolicy(
                policy_id="gov-sensitive-data",
                name="Sensitive Data Access",
                version="1.0",
                operation_types=["sensitive_data_access"],
                decision=GovDecision.DENY,
                conditions={},
                explanation_template="Sensitive data access denied without explicit data grant.",
            ),
            GovPolicy(
                policy_id="gov-gpu-spend-high",
                name="High GPU Spend",
                version="1.0",
                operation_types=["gpu_provision"],
                decision=GovDecision.REQUIRE_APPROVAL,
                conditions={"estimated_cost_usd_gte": 100.0},
                required_approver_role="operator",
                explanation_template="GPU spend exceeding $100 requires operator approval.",
            ),
            GovPolicy(
                policy_id="gov-gpu-spend-normal",
                name="Normal GPU Spend",
                version="1.0",
                operation_types=["gpu_provision"],
                decision=GovDecision.ALLOW,
                conditions={"estimated_cost_usd_lt": 100.0},
                explanation_template="GPU spend within normal limits is allowed.",
            ),
            GovPolicy(
                policy_id="gov-tool-high-impact",
                name="High-Impact Tool Execution",
                version="1.0",
                operation_types=["tool_execute"],
                decision=GovDecision.REQUIRE_APPROVAL,
                conditions={"is_high_impact": True},
                required_approver_role="operator",
                explanation_template="High-impact tool execution requires operator approval.",
            ),
        ]
        for p in defaults:
            self._policies[p.policy_id] = p

    # -- Policy management ---------------------------------------------------

    def add_policy(self, policy: GovPolicy, created_by: str) -> GovPolicy:
        if created_by in SYSTEM_ACTOR_IDS:
            raise PermissionError("Governance policies must be created by named human actors.")
        with self._lock:
            self._policies[policy.policy_id] = policy
        self._audit("POLICY_CREATED", created_by, policy.policy_id, {"version": policy.version})
        return policy

    def disable_policy(self, policy_id: str, actor_id: str) -> bool:
        policy = self._policies.get(policy_id)
        if not policy:
            return False
        policy.enabled = False
        self._audit("POLICY_DISABLED", actor_id, policy_id, {})
        return True

    def list_policies(self, operation_type: Optional[str] = None) -> List[Dict]:
        with self._lock:
            policies = list(self._policies.values())
        if operation_type:
            policies = [p for p in policies if operation_type in p.operation_types]
        return [p.to_dict() for p in policies if p.enabled]

    # -- Governance decision -------------------------------------------------

    def evaluate(
        self,
        actor_id: str,
        tenant_id: str,
        operation_type: str,
        resource_id: str,
        resource_type: str,
        context: Optional[Dict] = None,
    ) -> GovDecisionResult:
        ctx = context or {}

        # Find applicable policies
        candidates = [
            p for p in self._policies.values()
            if p.enabled and operation_type in p.operation_types
        ]

        # Apply conditions to find best-matching policy
        matched = None
        for policy in candidates:
            if self._conditions_match(policy.conditions, ctx):
                matched = policy
                break

        if not matched:
            # Default deny if no matching governance policy
            result = GovDecisionResult(
                result_id=str(uuid.uuid4()),
                decision=GovDecision.DENY,
                operation_type=operation_type,
                resource_id=resource_id,
                actor_id=actor_id,
                tenant_id=tenant_id,
                policy_id="default-deny",
                policy_version="1.0",
                explanation=f"No governance policy matched operation '{operation_type}'. Default deny.",
                risk_level="UNKNOWN",
                requires_approval=False,
                approval_request_id=None,
                timestamp=_now(),
                is_final=True,
            )
        else:
            approval_request_id = None
            if matched.decision == GovDecision.REQUIRE_APPROVAL:
                req = self._create_approval_request(
                    operation_type=operation_type,
                    resource_id=resource_id,
                    resource_type=resource_type,
                    actor_id=actor_id,
                    tenant_id=tenant_id,
                    policy=matched,
                    context=ctx,
                )
                approval_request_id = req.request_id

            result = GovDecisionResult(
                result_id=str(uuid.uuid4()),
                decision=matched.decision,
                operation_type=operation_type,
                resource_id=resource_id,
                actor_id=actor_id,
                tenant_id=tenant_id,
                policy_id=matched.policy_id,
                policy_version=matched.version,
                explanation=matched.explanation_template.format(
                    policy_id=matched.policy_id,
                    decision=matched.decision.value,
                ),
                risk_level=ctx.get("risk_level", "MEDIUM"),
                requires_approval=matched.decision == GovDecision.REQUIRE_APPROVAL,
                approval_request_id=approval_request_id,
                timestamp=_now(),
                is_final=matched.decision != GovDecision.REQUIRE_APPROVAL,
            )

        self._audit(
            "GOVERNANCE_DECISION",
            actor_id,
            resource_id,
            {
                "operation_type": operation_type,
                "decision": result.decision.value,
                "policy_id": result.policy_id,
                "approval_request_id": result.approval_request_id,
            },
        )
        return result

    def _conditions_match(self, conditions: Dict, context: Dict) -> bool:
        for cond_key, cond_val in conditions.items():
            if cond_key == "risk_level_in":
                if context.get("risk_level") not in cond_val:
                    return False
            elif cond_key == "risk_level_gte":
                rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
                ctx_rank = rank.get(context.get("risk_level", "LOW"), 0)
                req_rank = rank.get(cond_val, 0)
                if ctx_rank < req_rank:
                    return False
            elif cond_key == "estimated_cost_usd_gte":
                if context.get("estimated_cost_usd", 0) < cond_val:
                    return False
            elif cond_key == "estimated_cost_usd_lt":
                if context.get("estimated_cost_usd", 0) >= cond_val:
                    return False
            elif cond_key == "is_new_endpoint":
                if context.get("is_new_endpoint") != cond_val:
                    return False
            elif cond_key == "is_high_impact":
                if context.get("is_high_impact") != cond_val:
                    return False
        return True

    # -- Approval workflow ---------------------------------------------------

    def _create_approval_request(
        self,
        operation_type: str,
        resource_id: str,
        resource_type: str,
        actor_id: str,
        tenant_id: str,
        policy: GovPolicy,
        context: Dict,
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            operation_type=operation_type,
            resource_id=resource_id,
            resource_type=resource_type,
            actor_id=actor_id,
            tenant_id=tenant_id,
            required_approver_role=policy.required_approver_role or "operator",
            justification=context.get("justification", "No justification provided"),
            context={k: v for k, v in context.items() if k != "justification"},
            risk_level=context.get("risk_level", "MEDIUM"),
            policy_id=policy.policy_id,
            policy_version=policy.version,
        )
        with self._lock:
            self._requests[req.request_id] = req
        logger.info(
            "[governance] Approval request %s created for operation=%s resource=%s actor=%s",
            req.request_id, operation_type, resource_id, actor_id,
        )
        return req

    def get_approval_queue(
        self,
        tenant_id: str,
        status: Optional[ApprovalStatus] = None,
    ) -> List[Dict]:
        with self._lock:
            requests = [r for r in self._requests.values() if r.tenant_id == tenant_id]
        if status:
            requests = [r for r in requests if r.status == status]
        # Expire pending requests
        for req in requests:
            if req.status == ApprovalStatus.PENDING and req.is_expired():
                req.status = ApprovalStatus.EXPIRED
        return [r.to_dict() for r in requests]

    def approve_request(
        self,
        request_id: str,
        approver_id: str,
        notes: str = "",
    ) -> ApprovalRequest:
        """
        Approve a pending request.
        approver_id must be a named human — system actors are forbidden.
        """
        if approver_id in SYSTEM_ACTOR_IDS:
            raise PermissionError(
                "Governance approvals require a named human approver. "
                "System actors cannot impersonate human approval."
            )
        req = self._requests.get(request_id)
        if not req:
            raise ValueError(f"Approval request {request_id} not found")
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Request {request_id} is not in PENDING state (current: {req.status})")
        if req.is_expired():
            req.status = ApprovalStatus.EXPIRED
            raise ValueError(f"Approval request {request_id} has expired")

        req.status = ApprovalStatus.APPROVED
        req.approved_by = approver_id
        req.approved_at = _now()

        self._audit(
            "APPROVAL_GRANTED",
            approver_id,
            req.resource_id,
            {"request_id": request_id, "notes": notes[:200]},
        )
        logger.info("[governance] Request %s approved by %s", request_id, approver_id)
        return req

    def reject_request(
        self,
        request_id: str,
        rejector_id: str,
        reason: str,
    ) -> ApprovalRequest:
        if rejector_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("Rejections require a named human actor.")
        req = self._requests.get(request_id)
        if not req:
            raise ValueError(f"Request {request_id} not found")

        req.status = ApprovalStatus.REJECTED
        req.rejected_by = rejector_id
        req.rejected_at = _now()
        req.rejection_reason = reason

        self._audit(
            "APPROVAL_REJECTED",
            rejector_id,
            req.resource_id,
            {"request_id": request_id, "reason": reason[:200]},
        )
        return req

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        return self._requests.get(request_id)

    # -- Audit ---------------------------------------------------------------

    def _audit(self, event_type: str, actor_id: str, resource_id: str, metadata: Dict):
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "actor_id": actor_id,
            "resource_id": resource_id,
            "metadata": metadata,
            "timestamp": _now(),
        }
        with self._lock:
            self._audit_log.append(event)

    def get_audit_log(self, limit: int = 200) -> List[Dict]:
        with self._lock:
            return list(self._audit_log[-limit:])


_GOV_ENGINE = GovernanceApprovalEngine()


def get_governance_engine() -> GovernanceApprovalEngine:
    return _GOV_ENGINE
