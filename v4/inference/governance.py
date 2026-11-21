# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Model Governance Layer — Phase 3H
==========================================
Tracks model provenance, licence verification, deployment approvals, and audit trails.

RULES:
- Unknown licences ALWAYS require human review. Never auto-approved.
- Non-commercial licences BLOCK commercial deployment.
- All decisions are written to the audit trail.
- Approvals require an explicit approver_id — cannot be system-generated.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orquanta.inference.governance")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyDecision(str, Enum):
    APPROVED        = "APPROVED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    BLOCKED         = "BLOCKED"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AuditEvent:
    event_id: str
    event_type: str          # LICENCE_VERIFIED | APPROVED | REVOKED | BLOCKED | EVALUATED
    timestamp: str
    actor_id: str            # user_id or "system"
    model_id: str
    decision: Optional[str] = None
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyDecisionResult:
    decision: PolicyDecision
    model_id: str
    reasons: List[str]
    risk_level: RiskLevel
    requires_human_approval: bool
    evaluated_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["decision"] = self.decision.value
        d["risk_level"] = self.risk_level.value
        return d


@dataclass
class ModelGovernancePolicy:
    model_id: str
    licence: str
    licence_known: bool
    commercial_ok: Optional[bool]       # None = unknown
    licence_verified: bool = False
    licence_verified_at: Optional[str] = None
    licence_verified_by: str = ""
    deployment_allowed: bool = False
    deployment_approved_at: Optional[str] = None
    deployment_approved_by: str = ""
    approval_notes: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    is_revoked: bool = False
    revocation_reason: str = ""
    revoked_at: Optional[str] = None
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk_level"] = self.risk_level.value
        return d


# ---------------------------------------------------------------------------
# Governance engine
# ---------------------------------------------------------------------------

class GovernanceEngine:
    """
    Evaluates and records model deployment governance decisions.

    Thread-safety: in-memory store with simple dict access.
    Production: replace with PostgreSQL-backed storage.
    """

    def __init__(self) -> None:
        self._policies: Dict[str, ModelGovernancePolicy] = {}
        self._audit: List[AuditEvent] = []

    # ── Internal audit ──────────────────────────────────────────────────────

    def _record(
        self,
        event_type: str,
        actor_id: str,
        model_id: str,
        decision: Optional[str] = None,
        detail: str = "",
    ) -> AuditEvent:
        ev = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=_now(),
            actor_id=actor_id,
            model_id=model_id,
            decision=decision,
            detail=detail,
        )
        self._audit.append(ev)
        logger.info("[governance] %s model=%s actor=%s decision=%s", event_type, model_id, actor_id, decision)
        return ev

    # ── Licence verification ─────────────────────────────────────────────────

    def verify_licence(
        self,
        model_id: str,
        licence: str,
        licence_info: Dict[str, Any],
        verified_by: str = "system",
    ) -> ModelGovernancePolicy:
        """
        Record licence verification for a model.
        Does NOT automatically approve deployment.
        """
        licence_known = licence_info.get("known", False)
        commercial_ok = licence_info.get("commercial")

        policy = self._policies.get(model_id) or ModelGovernancePolicy(
            model_id=model_id,
            licence=licence,
            licence_known=licence_known,
            commercial_ok=commercial_ok,
        )
        policy.licence_known = licence_known
        policy.commercial_ok = commercial_ok
        policy.licence_verified = True
        policy.licence_verified_at = _now()
        policy.licence_verified_by = verified_by

        # Risk assessment
        if not licence_known:
            policy.risk_level = RiskLevel.HIGH
        elif commercial_ok is False:
            policy.risk_level = RiskLevel.HIGH
        elif commercial_ok is True:
            policy.risk_level = RiskLevel.LOW
        else:
            policy.risk_level = RiskLevel.MEDIUM

        self._policies[model_id] = policy
        self._record("LICENCE_VERIFIED", verified_by, model_id,
                     detail=f"licence={licence} known={licence_known} commercial={commercial_ok}")
        return policy

    # ── Deployment evaluation ────────────────────────────────────────────────

    def evaluate_deployment(
        self,
        model_id: str,
        purpose: str = "commercial",
        actor_id: str = "system",
    ) -> PolicyDecisionResult:
        """
        Evaluate whether this model can be deployed.

        Rules (in priority order):
        1. Unknown licence → REQUIRES_REVIEW (never auto-approve)
        2. Non-commercial licence + commercial purpose → BLOCKED
        3. No licence verification → REQUIRES_REVIEW
        4. Revoked approval → BLOCKED
        5. All checks passed → APPROVED (or REQUIRES_REVIEW if high risk)
        """
        policy = self._policies.get(model_id)
        reasons: List[str] = []

        if policy is None:
            reasons.append(f"Model '{model_id}' has no governance record. Licence verification required before deployment.")
            result = PolicyDecisionResult(
                decision=PolicyDecision.REQUIRES_REVIEW,
                model_id=model_id,
                reasons=reasons,
                risk_level=RiskLevel.HIGH,
                requires_human_approval=True,
            )
            self._record("EVALUATED", actor_id, model_id, decision=result.decision.value,
                         detail="No governance record")
            return result

        if policy.is_revoked:
            reasons.append(f"Deployment approval was revoked: {policy.revocation_reason}")
            result = PolicyDecisionResult(
                decision=PolicyDecision.BLOCKED,
                model_id=model_id,
                reasons=reasons,
                risk_level=RiskLevel.CRITICAL,
                requires_human_approval=False,
            )
            self._record("EVALUATED", actor_id, model_id, decision="BLOCKED", detail="Revoked")
            return result

        if not policy.licence_known:
            reasons.append(
                f"Licence '{policy.licence}' is not in OrQuanta's licence database. "
                "Human review required before commercial deployment."
            )
            result = PolicyDecisionResult(
                decision=PolicyDecision.REQUIRES_REVIEW,
                model_id=model_id,
                reasons=reasons,
                risk_level=RiskLevel.HIGH,
                requires_human_approval=True,
            )
            self._record("EVALUATED", actor_id, model_id, decision="REQUIRES_REVIEW",
                         detail="Unknown licence")
            return result

        if purpose == "commercial" and policy.commercial_ok is False:
            reasons.append(
                f"Model licence '{policy.licence}' prohibits commercial use. "
                "Commercial deployment is blocked."
            )
            result = PolicyDecisionResult(
                decision=PolicyDecision.BLOCKED,
                model_id=model_id,
                reasons=reasons,
                risk_level=RiskLevel.HIGH,
                requires_human_approval=False,
            )
            self._record("EVALUATED", actor_id, model_id, decision="BLOCKED",
                         detail="Non-commercial licence")
            return result

        if purpose == "commercial" and policy.commercial_ok is None:
            reasons.append("Commercial use permission is unknown for this licence. Human review required.")
            result = PolicyDecisionResult(
                decision=PolicyDecision.REQUIRES_REVIEW,
                model_id=model_id,
                reasons=reasons,
                risk_level=RiskLevel.MEDIUM,
                requires_human_approval=True,
            )
            self._record("EVALUATED", actor_id, model_id, decision="REQUIRES_REVIEW",
                         detail="Unknown commercial_ok")
            return result

        # All checks pass
        reasons.append(
            f"Licence '{policy.licence}' verified. Commercial use: "
            f"{'allowed' if policy.commercial_ok else 'unknown'}."
        )
        if policy.deployment_allowed:
            reasons.append(f"Deployment approved by {policy.deployment_approved_by}.")

        result = PolicyDecisionResult(
            decision=PolicyDecision.APPROVED,
            model_id=model_id,
            reasons=reasons,
            risk_level=policy.risk_level,
            requires_human_approval=(policy.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)),
        )
        self._record("EVALUATED", actor_id, model_id, decision="APPROVED")
        return result

    # ── Approval management ──────────────────────────────────────────────────

    def approve_deployment(
        self,
        model_id: str,
        approver_id: str,
        notes: str = "",
    ) -> ModelGovernancePolicy:
        """
        Record explicit human approval for model deployment.
        approver_id cannot be 'system' — requires a real user identity.
        """
        if approver_id.lower() in ("system", "auto", ""):
            raise ValueError("Deployment approval requires a real user identity. System cannot self-approve.")

        policy = self._policies.get(model_id)
        if not policy:
            raise ValueError(f"No governance policy found for '{model_id}'. Run verify_licence() first.")

        policy.deployment_allowed = True
        policy.deployment_approved_at = _now()
        policy.deployment_approved_by = approver_id
        policy.approval_notes = notes
        self._policies[model_id] = policy

        self._record("APPROVED", approver_id, model_id, decision="APPROVED",
                     detail=f"notes={notes[:100]}")
        return policy

    def revoke_approval(
        self,
        model_id: str,
        revoker_id: str,
        reason: str,
    ) -> ModelGovernancePolicy:
        policy = self._policies.get(model_id)
        if not policy:
            raise ValueError(f"No governance policy for '{model_id}'.")
        policy.is_revoked = True
        policy.revocation_reason = reason
        policy.revoked_at = _now()
        policy.deployment_allowed = False
        self._policies[model_id] = policy
        self._record("REVOKED", revoker_id, model_id, decision="BLOCKED", detail=reason)
        return policy

    # ── Audit + query ────────────────────────────────────────────────────────

    def get_audit_trail(self, model_id: Optional[str] = None) -> List[Dict[str, Any]]:
        events = self._audit if model_id is None else [e for e in self._audit if e.model_id == model_id]
        return [e.to_dict() for e in events]

    def get_policy(self, model_id: str) -> Optional[ModelGovernancePolicy]:
        return self._policies.get(model_id)

    def is_deployment_allowed(self, model_id: str) -> bool:
        policy = self._policies.get(model_id)
        if not policy:
            return False
        return policy.deployment_allowed and not policy.is_revoked

    def list_policies(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self._policies.values()]


# ---------------------------------------------------------------------------
# Singleton (process-level; backed by DB in production)
# ---------------------------------------------------------------------------

_governance_engine = GovernanceEngine()


def get_governance_engine() -> GovernanceEngine:
    return _governance_engine
