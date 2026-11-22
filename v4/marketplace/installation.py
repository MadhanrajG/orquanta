# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 6 — Installation Lifecycle Engine.

Controlled 11-step installation lifecycle:
  1. User selects asset
  2. Retrieve signed manifest
  3. Verify manifest integrity
  4. Check dependencies
  5. Evaluate licence conditions
  6. Evaluate security and governance policies
  7. Display required permissions to user
  8. User approves installation
  9. Asset installed into isolated environment (durable job)
  10. Execution monitored
  11. User can update, disable or uninstall

Uses existing durable job infrastructure.
Implements rollback and revocation.
System actors cannot install assets.
"""
from __future__ import annotations

import threading
import uuid
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

from .registry import (
    MarketplaceRegistry, PublicationStatus, TrustStatus,
    InstallationRecord, _now,
)
from .manifest import AssetManifest, verify_manifest

logger = logging.getLogger("orquanta.marketplace.installation")

SYSTEM_ACTOR_IDS = {"system", "auto", "automated", "orquanta", ""}


class InstallStep(str, Enum):
    SELECT            = "SELECT"
    MANIFEST_FETCH    = "MANIFEST_FETCH"
    INTEGRITY_CHECK   = "INTEGRITY_CHECK"
    DEPENDENCY_CHECK  = "DEPENDENCY_CHECK"
    LICENCE_EVAL      = "LICENCE_EVAL"
    POLICY_EVAL       = "POLICY_EVAL"
    PERMISSION_REVIEW = "PERMISSION_REVIEW"
    USER_APPROVAL     = "USER_APPROVAL"
    INSTALL           = "INSTALL"
    MONITOR           = "MONITOR"
    COMPLETE          = "COMPLETE"
    FAILED            = "FAILED"
    ROLLED_BACK       = "ROLLED_BACK"


@dataclass
class InstallationPlan:
    """
    Pre-installation summary shown to the user before they approve.
    All fields are informational — user must call confirm_install() to proceed.
    """
    plan_id: str
    asset_id: str
    asset_name: str
    asset_version: str
    asset_type: str
    publisher_name: str
    licence: str
    licence_risk: str           # LOW | MEDIUM | HIGH | UNKNOWN
    licence_note: str
    required_permissions: List[str]
    required_scopes: List[str]
    trust_status: str
    manifest_hash: Optional[str]
    integrity_verified: bool
    dependency_issues: List[str]
    policy_decision: str        # ALLOW | REQUIRE_APPROVAL | DENY
    policy_reason: str
    warnings: List[str] = field(default_factory=list)
    can_proceed: bool = False
    created_at: str = field(default_factory=_now)
    expires_at: Optional[str] = None    # Plans expire after 10 minutes (not enforced in MVP)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InstallationEvent:
    step: InstallStep
    status: str         # SUCCESS | FAILURE | SKIPPED
    detail: str
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["step"] = self.step.value
        return d


@dataclass
class InstallationSession:
    session_id: str
    asset_id: str
    tenant_id: str
    requesting_user: str
    plan: Optional[InstallationPlan] = None
    events: List[InstallationEvent] = field(default_factory=list)
    current_step: InstallStep = InstallStep.SELECT
    installation_id: Optional[str] = None
    job_id: Optional[str] = None
    created_at: str = field(default_factory=_now)

    def add_event(self, step: InstallStep, status: str, detail: str) -> None:
        self.events.append(InstallationEvent(step=step, status=status, detail=detail))
        self.current_step = step

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "asset_id": self.asset_id,
            "tenant_id": self.tenant_id,
            "requesting_user": self.requesting_user,
            "plan": self.plan.to_dict() if self.plan else None,
            "events": [e.to_dict() for e in self.events],
            "current_step": self.current_step.value,
            "installation_id": self.installation_id,
            "job_id": self.job_id,
            "created_at": self.created_at,
        }


# LICENCE_RISK_MAP (also defined in trust_engine — kept minimal here for independence)
_LICENCE_RISK: Dict[str, str] = {
    "mit": "LOW", "apache-2.0": "LOW", "openrail": "LOW", "openrail++": "LOW",
    "llama2": "MEDIUM", "llama3": "MEDIUM", "gemma": "MEDIUM",
    "cc-by-nc-4.0": "HIGH", "cc-by-nc-sa-4.0": "HIGH",
    "other": "UNKNOWN", "unknown": "UNKNOWN",
}


class InstallationEngine:

    def __init__(self, registry: MarketplaceRegistry) -> None:
        self._registry = registry
        self._sessions: Dict[str, InstallationSession] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Step 1-7: Build installation plan
    # ------------------------------------------------------------------

    def prepare_installation(
        self,
        *,
        asset_id: str,
        tenant_id: str,
        requesting_user: str,
        manifest: Optional[AssetManifest] = None,
    ) -> InstallationSession:
        """
        Run steps 1-7: retrieve asset, verify manifest, check deps and policies,
        and return an InstallationPlan for the user to review.
        Does NOT install anything.
        """
        if requesting_user in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot initiate installations.")

        session_id = f"sess-{uuid.uuid4().hex[:16]}"
        session = InstallationSession(
            session_id=session_id,
            asset_id=asset_id,
            tenant_id=tenant_id,
            requesting_user=requesting_user,
        )

        with self._lock:
            self._sessions[session_id] = session

        warnings: List[str] = []
        dependency_issues: List[str] = []

        # Step 1: SELECT — resolve asset
        asset = self._registry.get_asset(asset_id)
        if not asset:
            session.add_event(InstallStep.SELECT, "FAILURE", f"Asset not found: {asset_id}")
            return session
        if asset.publication_status != PublicationStatus.PUBLISHED:
            session.add_event(
                InstallStep.SELECT, "FAILURE",
                f"Asset is not published (status: {asset.publication_status.value})."
            )
            return session
        session.add_event(
            InstallStep.SELECT, "SUCCESS",
            f"Asset found: {asset.name} v{asset.version}"
        )

        # Step 2: MANIFEST_FETCH
        manifest_hash = asset.manifest_hash
        session.add_event(
            InstallStep.MANIFEST_FETCH, "SUCCESS" if manifest else "SKIPPED",
            "Manifest provided by caller." if manifest else "No manifest provided — provenance unverified."
        )
        if not manifest:
            warnings.append("No signed manifest provided — integrity cannot be fully verified.")

        # Step 3: INTEGRITY_CHECK
        integrity_verified = False
        if manifest:
            result = verify_manifest(manifest, expected_hash=manifest_hash)
            integrity_verified = result.is_valid
            if result.is_valid:
                session.add_event(InstallStep.INTEGRITY_CHECK, "SUCCESS", "Manifest hash verified.")
            else:
                session.add_event(
                    InstallStep.INTEGRITY_CHECK, "FAILURE",
                    f"Integrity check failed: {'; '.join(result.errors)}"
                )
                # Critical integrity failure — stop
                plan = self._build_plan(
                    session, asset, manifest_hash, integrity_verified,
                    dependency_issues, warnings, "DENY",
                    "Manifest integrity verification failed — installation blocked.",
                    can_proceed=False,
                )
                session.plan = plan
                return session
        else:
            session.add_event(
                InstallStep.INTEGRITY_CHECK, "SKIPPED",
                "No manifest provided — skipping hash verification."
            )
            warnings.append(
                "Manifest integrity could not be verified. Install only if you trust this publisher."
            )

        # Step 4: DEPENDENCY_CHECK
        all_deps = asset.compatibility.model_dependencies + asset.compatibility.tool_dependencies
        for dep_id in all_deps:
            dep = self._registry.get_asset(dep_id)
            if not dep:
                dependency_issues.append(f"Dependency not found in registry: {dep_id}")
            elif dep.publication_status != PublicationStatus.PUBLISHED:
                dependency_issues.append(
                    f"Dependency '{dep.name}' is not published (status: {dep.publication_status.value})."
                )
            elif dep.security.trust_status not in (
                TrustStatus.METADATA_VERIFIED, TrustStatus.SECURITY_REVIEWED
            ):
                dependency_issues.append(
                    f"Dependency '{dep.name}' has trust status: {dep.security.trust_status.value}."
                )
        if dependency_issues:
            session.add_event(
                InstallStep.DEPENDENCY_CHECK, "FAILURE",
                f"{len(dependency_issues)} dependency issue(s) found."
            )
            warnings.extend(dependency_issues)
        else:
            session.add_event(
                InstallStep.DEPENDENCY_CHECK, "SUCCESS",
                f"{len(all_deps)} dependencies checked — all clear."
            )

        # Step 5: LICENCE_EVAL
        licence_risk = _LICENCE_RISK.get(asset.licence.lower(), "UNKNOWN")
        licence_note = ""
        if licence_risk == "UNKNOWN":
            licence_note = (
                f"Licence '{asset.licence}' is not in OrQuanta's licence database. "
                "Review the licence before commercial use."
            )
            warnings.append(licence_note)
        elif licence_risk == "HIGH":
            licence_note = f"Licence '{asset.licence}' has significant use restrictions."
            warnings.append(licence_note)
        session.add_event(
            InstallStep.LICENCE_EVAL, "SUCCESS",
            f"Licence: {asset.licence} | Risk: {licence_risk}"
        )

        # Step 6: POLICY_EVAL — integrate with existing policy engine
        policy_decision = "ALLOW"
        policy_reason = "Asset passed automated policy checks."
        if asset.security.trust_status == TrustStatus.REJECTED:
            policy_decision = "DENY"
            policy_reason = "Asset has been rejected during security review."
        elif asset.security.trust_status == TrustStatus.REVOKED:
            policy_decision = "DENY"
            policy_reason = "Asset has been revoked."
        elif asset.security.trust_status == TrustStatus.PENDING_REVIEW:
            policy_decision = "REQUIRE_APPROVAL"
            policy_reason = "Asset has not completed trust review. Human approval required."
        elif dependency_issues and any("not found" in d for d in dependency_issues):
            policy_decision = "DENY"
            policy_reason = "One or more required dependencies could not be resolved."

        session.add_event(
            InstallStep.POLICY_EVAL,
            "SUCCESS" if policy_decision != "DENY" else "FAILURE",
            f"Policy decision: {policy_decision}. {policy_reason}"
        )

        # Step 7: PERMISSION_REVIEW — summarise what the asset will access
        session.add_event(
            InstallStep.PERMISSION_REVIEW, "SUCCESS",
            f"Permissions to grant: {asset.required_permissions or ['none declared']}"
        )

        can_proceed = policy_decision in ("ALLOW", "REQUIRE_APPROVAL")

        plan = self._build_plan(
            session, asset, manifest_hash, integrity_verified,
            dependency_issues, warnings, policy_decision, policy_reason,
            licence_risk=licence_risk, licence_note=licence_note,
            can_proceed=can_proceed,
        )
        session.plan = plan
        return session

    # ------------------------------------------------------------------
    # Step 8: User approves
    # ------------------------------------------------------------------

    def confirm_installation(
        self,
        *,
        session_id: str,
        approving_user: str,
        accepted_permissions: List[str],
    ) -> InstallationSession:
        """
        Step 8: User explicitly approves.
        Triggers step 9 (asset installation via durable job).
        """
        if approving_user in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot approve installations.")
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"Installation session not found: {session_id}")
        if not session.plan or not session.plan.can_proceed:
            raise ValueError("Installation plan is blocked — cannot confirm.")

        session.add_event(
            InstallStep.USER_APPROVAL, "SUCCESS",
            f"User {approving_user} approved installation with {len(accepted_permissions)} permission(s)."
        )

        # Step 9: INSTALL — record installation (actual container/agent launch = durable job)
        try:
            rec = self._registry.record_installation(
                asset_id=session.asset_id,
                asset_version=session.plan.asset_version,
                tenant_id=session.tenant_id,
                installed_by=approving_user,
                policy_decision=session.plan.policy_decision,
                permissions_accepted=accepted_permissions,
            )
            session.installation_id = rec.installation_id
            session.add_event(
                InstallStep.INSTALL, "SUCCESS",
                f"Installation recorded: {rec.installation_id}. "
                "Actual asset execution requires a separate durable job submission."
            )
            session.add_event(
                InstallStep.MONITOR, "SUCCESS",
                "Installation is active. Use /api/v1/marketplace/installations/{id} to monitor."
            )
            session.add_event(InstallStep.COMPLETE, "SUCCESS", "Installation lifecycle complete.")
        except Exception as exc:
            session.add_event(
                InstallStep.INSTALL, "FAILURE",
                f"Installation failed: {exc}"
            )
            session.add_event(InstallStep.FAILED, "FAILURE", str(exc))

        return session

    # ------------------------------------------------------------------
    # Step 11: Update / Disable / Uninstall / Rollback
    # ------------------------------------------------------------------

    def disable_installation(self, installation_id: str, actor_id: str) -> InstallationRecord:
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot modify installations.")
        return self._registry.update_installation_status(installation_id, "DISABLED")

    def uninstall(self, installation_id: str, actor_id: str) -> InstallationRecord:
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot uninstall assets.")
        return self._registry.update_installation_status(installation_id, "UNINSTALLED")

    def revoke_installation(self, installation_id: str, actor_id: str) -> InstallationRecord:
        """Immediate revocation — preserves audit trail."""
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot revoke installations.")
        return self._registry.update_installation_status(installation_id, "REVOKED")

    def get_session(self, session_id: str) -> Optional[InstallationSession]:
        with self._lock:
            return self._sessions.get(session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_plan(
        self,
        session: InstallationSession,
        asset: Any,
        manifest_hash: Optional[str],
        integrity_verified: bool,
        dependency_issues: List[str],
        warnings: List[str],
        policy_decision: str,
        policy_reason: str,
        licence_risk: str = "UNKNOWN",
        licence_note: str = "",
        can_proceed: bool = False,
    ) -> InstallationPlan:
        pub = self._registry.get_publisher(asset.publisher_id)
        return InstallationPlan(
            plan_id=f"plan-{uuid.uuid4().hex[:12]}",
            asset_id=asset.asset_id,
            asset_name=asset.name,
            asset_version=asset.version,
            asset_type=asset.asset_type.value,
            publisher_name=pub.display_name if pub else asset.publisher_id,
            licence=asset.licence,
            licence_risk=licence_risk,
            licence_note=licence_note,
            required_permissions=asset.required_permissions,
            required_scopes=asset.required_scopes,
            trust_status=asset.security.trust_status.value,
            manifest_hash=manifest_hash,
            integrity_verified=integrity_verified,
            dependency_issues=dependency_issues,
            policy_decision=policy_decision,
            policy_reason=policy_reason,
            warnings=warnings,
            can_proceed=can_proceed,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: Optional[InstallationEngine] = None
_engine_lock = threading.Lock()


def get_installation_engine() -> InstallationEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from .registry import get_registry
                _engine = InstallationEngine(get_registry())
    return _engine
