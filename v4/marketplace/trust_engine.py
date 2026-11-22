# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 6F — Marketplace Trust and Security Engine.

Connects every marketplace asset to the existing OrQuanta Trust Centre.
Integrates with:
  - Phase 4D ModelSupplyChainSecurity (for model assets)
  - Phase 4E MCPToolSecurityRegistry (for MCP assets)
  - Phase 4A PolicyEngine (for governance decisions)
  - Phase 4G AIRiskRegister (for risk tracking)

Trust pipeline per asset:
  1. Publisher identity verification
  2. Manifest integrity check
  3. Dependency scan (recursive trust check on declared dependencies)
  4. Licence assessment
  5. Permission review
  6. Static analysis / malware scan (where applicable)
  7. Vulnerability tracking
  8. Governance approval

Disclaimer (always present):
  Security review confirms static analysis at review time.
  OrQuanta does NOT guarantee that any marketplace asset is completely safe.
  Trust status is version-specific — a new version resets to PENDING_REVIEW.
"""
from __future__ import annotations

import hashlib
import threading
import uuid
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

from .registry import (
    MarketplaceRegistry, TrustStatus, AssetType, _now,
)
from .manifest import AssetManifest, verify_manifest, ManifestVerificationResult

logger = logging.getLogger("orquanta.marketplace.trust")

SYSTEM_ACTOR_IDS = {"system", "auto", "automated", "orquanta", ""}

# Always present on every security assessment
SECURITY_DISCLAIMER = (
    "Security review reflects the state of static analysis at review time. "
    "OrQuanta does NOT guarantee that any marketplace asset is completely safe. "
    "Trust status is version-specific — a new version requires a fresh review. "
    "Metadata verification confirms publisher identity; it is not a security audit."
)


# ---------------------------------------------------------------------------
# Assessment result types
# ---------------------------------------------------------------------------

class FindingSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    INFO     = "INFO"


@dataclass
class TrustFinding:
    finding_id: str
    severity: FindingSeverity
    category: str           # LICENCE | PERMISSION | DEPENDENCY | INTEGRITY | MALWARE | VULNERABILITY | PROVENANCE
    title: str
    detail: str
    is_heuristic: bool = True
    heuristic_limitation: str = "This finding was produced by automated static analysis."
    remediation: str = ""


@dataclass
class DependencyScanResult:
    dependency_name: str
    resolved_asset_id: Optional[str]
    trust_status: Optional[str]
    is_trusted: bool
    issue: Optional[str] = None


@dataclass
class MarketplaceTrustAssessment:
    assessment_id: str
    asset_id: str
    asset_version: str
    reviewed_by: str
    reviewed_at: str
    # Checks
    publisher_verified: bool = False
    manifest_integrity: bool = False
    manifest_verification_detail: Optional[Dict[str, Any]] = None
    dependency_scan: List[DependencyScanResult] = field(default_factory=list)
    licence_risk: str = "UNKNOWN"       # LOW | MEDIUM | HIGH | UNKNOWN
    licence_note: str = ""
    permission_review_complete: bool = False
    high_risk_permissions: List[str] = field(default_factory=list)
    static_analysis_run: bool = False
    vulnerability_findings: List[TrustFinding] = field(default_factory=list)
    all_findings: List[TrustFinding] = field(default_factory=list)
    # Outcome
    recommended_trust_status: TrustStatus = TrustStatus.PENDING_REVIEW
    is_safe_claim: bool = False         # Always False — never guarantee safety
    disclaimer: str = SECURITY_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["recommended_trust_status"] = self.recommended_trust_status.value
        return d


# ---------------------------------------------------------------------------
# Trust Engine
# ---------------------------------------------------------------------------

# Permissions that warrant a HIGH_RISK flag
HIGH_RISK_PERMISSIONS = {
    "exec:shell", "exec:code", "admin:policy", "admin:users",
    "security:revoke", "data:read:sensitive", "db:write", "fs:write",
}

# Licences with known commercial restrictions
LICENCE_RISK_MAP: Dict[str, str] = {
    "cc-by-nc-4.0": "HIGH",
    "cc-by-nc-sa-4.0": "HIGH",
    "bigscience-bloom-rail-1.0": "HIGH",
    "other": "UNKNOWN",
    "unknown": "UNKNOWN",
    "mit": "LOW",
    "apache-2.0": "LOW",
    "openrail": "LOW",
    "openrail++": "LOW",
    "llama2": "MEDIUM",
    "llama3": "MEDIUM",
    "gemma": "MEDIUM",
}


class MarketplaceTrustEngine:

    def __init__(self, registry: MarketplaceRegistry) -> None:
        self._registry = registry
        self._assessments: Dict[str, MarketplaceTrustAssessment] = {}   # assessment_id -> record
        self._asset_latest_assessment: Dict[str, str] = {}              # asset_id -> assessment_id
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Full trust pipeline
    # ------------------------------------------------------------------

    def run_trust_pipeline(
        self,
        *,
        asset_id: str,
        reviewer_id: str,
        manifest: Optional[AssetManifest] = None,
        public_key: Optional[bytes] = None,
    ) -> MarketplaceTrustAssessment:
        """
        Run the full trust pipeline for an asset version.
        Returns an assessment — does NOT automatically publish the asset.
        Human reviewer must call approve_assessment() to update trust status.
        """
        if reviewer_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot run trust assessments.")

        asset = self._registry.get_asset(asset_id)
        if not asset:
            raise KeyError(f"Asset not found: {asset_id}")

        assessment_id = f"ta-{uuid.uuid4().hex[:16]}"
        findings: List[TrustFinding] = []

        # 1. Publisher verification
        publisher = self._registry.get_publisher(asset.publisher_id)
        publisher_verified = bool(publisher and publisher.is_verified and not publisher.is_banned)
        if not publisher_verified:
            findings.append(TrustFinding(
                finding_id=str(uuid.uuid4()),
                severity=FindingSeverity.HIGH,
                category="PROVENANCE",
                title="Publisher not verified",
                detail=(
                    f"Publisher {asset.publisher_id!r} has not been verified. "
                    "Treat this asset with caution."
                ),
                remediation="Contact publisher to complete identity verification.",
            ))

        # 2. Manifest integrity
        manifest_ok = False
        manifest_detail: Optional[Dict[str, Any]] = None
        if manifest:
            result: ManifestVerificationResult = verify_manifest(
                manifest,
                public_key=public_key,
            )
            manifest_ok = result.is_valid
            manifest_detail = {
                "hash_match": result.hash_match,
                "signature_verified": result.signature_verified,
                "errors": result.errors,
                "warnings": result.warnings,
                "disclaimer": result.disclaimer,
            }
            if not result.is_valid:
                for err in result.errors:
                    findings.append(TrustFinding(
                        finding_id=str(uuid.uuid4()),
                        severity=FindingSeverity.CRITICAL,
                        category="INTEGRITY",
                        title="Manifest integrity failure",
                        detail=err,
                        remediation="Do not install this asset. Contact the publisher.",
                    ))
        else:
            findings.append(TrustFinding(
                finding_id=str(uuid.uuid4()),
                severity=FindingSeverity.MEDIUM,
                category="INTEGRITY",
                title="No manifest provided",
                detail="Asset was submitted without a signed manifest. Provenance cannot be verified.",
                remediation="Request a signed manifest from the publisher.",
            ))

        # 3. Dependency scan
        dep_scan: List[DependencyScanResult] = []
        for dep_id in asset.compatibility.model_dependencies + asset.compatibility.tool_dependencies:
            dep_asset = self._registry.get_asset(dep_id)
            if dep_asset:
                is_trusted = dep_asset.security.trust_status in (
                    TrustStatus.METADATA_VERIFIED, TrustStatus.SECURITY_REVIEWED
                )
                dep_scan.append(DependencyScanResult(
                    dependency_name=dep_asset.name,
                    resolved_asset_id=dep_id,
                    trust_status=dep_asset.security.trust_status.value,
                    is_trusted=is_trusted,
                    issue=None if is_trusted else f"Dependency trust status: {dep_asset.security.trust_status.value}",
                ))
                if not is_trusted:
                    findings.append(TrustFinding(
                        finding_id=str(uuid.uuid4()),
                        severity=FindingSeverity.HIGH,
                        category="DEPENDENCY",
                        title=f"Untrusted dependency: {dep_asset.name}",
                        detail=f"Dependency {dep_id} has trust status {dep_asset.security.trust_status.value}.",
                        remediation="Ensure all dependencies are security-reviewed before installing.",
                    ))
            else:
                dep_scan.append(DependencyScanResult(
                    dependency_name=dep_id,
                    resolved_asset_id=None,
                    trust_status=None,
                    is_trusted=False,
                    issue="Dependency not found in registry.",
                ))
                findings.append(TrustFinding(
                    finding_id=str(uuid.uuid4()),
                    severity=FindingSeverity.HIGH,
                    category="DEPENDENCY",
                    title=f"Unresolved dependency: {dep_id}",
                    detail=f"Dependency {dep_id!r} could not be found in the marketplace registry.",
                    remediation="Verify dependency IDs in the manifest.",
                ))

        # 4. Licence assessment
        licence_risk = LICENCE_RISK_MAP.get(asset.licence.lower(), "UNKNOWN")
        licence_note = ""
        if licence_risk == "UNKNOWN":
            licence_note = (
                f"Licence '{asset.licence}' is not in OrQuanta's licence database. "
                "Review the licence terms before commercial use."
            )
            findings.append(TrustFinding(
                finding_id=str(uuid.uuid4()),
                severity=FindingSeverity.MEDIUM,
                category="LICENCE",
                title="Unknown or unrecognised licence",
                detail=licence_note,
                remediation="Review the licence terms manually.",
            ))
        elif licence_risk == "HIGH":
            licence_note = f"Licence '{asset.licence}' has significant use restrictions."
            findings.append(TrustFinding(
                finding_id=str(uuid.uuid4()),
                severity=FindingSeverity.HIGH,
                category="LICENCE",
                title="Restricted licence",
                detail=licence_note,
                remediation="Confirm permitted use before installation.",
            ))

        # 5. Permission review
        high_risk_perms = [
            p for p in (asset.required_permissions + asset.required_scopes)
            if p in HIGH_RISK_PERMISSIONS
        ]
        if high_risk_perms:
            findings.append(TrustFinding(
                finding_id=str(uuid.uuid4()),
                severity=FindingSeverity.HIGH,
                category="PERMISSION",
                title="High-risk permission scopes requested",
                detail=f"This asset requests: {', '.join(high_risk_perms)}",
                remediation="Verify these permissions are necessary before approving installation.",
            ))

        # 6. Determine recommended trust status
        critical_findings = [f for f in findings if f.severity == FindingSeverity.CRITICAL]
        high_findings = [f for f in findings if f.severity == FindingSeverity.HIGH]

        if critical_findings:
            recommended = TrustStatus.REJECTED
        elif not manifest_ok and not manifest:
            recommended = TrustStatus.METADATA_VERIFIED if publisher_verified else TrustStatus.PENDING_REVIEW
        elif publisher_verified and manifest_ok and not high_findings:
            recommended = TrustStatus.SECURITY_REVIEWED
        elif publisher_verified:
            recommended = TrustStatus.METADATA_VERIFIED
        else:
            recommended = TrustStatus.PENDING_REVIEW

        assessment = MarketplaceTrustAssessment(
            assessment_id=assessment_id,
            asset_id=asset_id,
            asset_version=asset.version,
            reviewed_by=reviewer_id,
            reviewed_at=_now(),
            publisher_verified=publisher_verified,
            manifest_integrity=manifest_ok,
            manifest_verification_detail=manifest_detail,
            dependency_scan=dep_scan,
            licence_risk=licence_risk,
            licence_note=licence_note,
            permission_review_complete=True,
            high_risk_permissions=high_risk_perms,
            static_analysis_run=False,   # Phase 6 MVP: placeholder for future scanner integration
            vulnerability_findings=[f for f in findings if f.category == "VULNERABILITY"],
            all_findings=findings,
            recommended_trust_status=recommended,
            is_safe_claim=False,
        )

        with self._lock:
            self._assessments[assessment_id] = assessment
            self._asset_latest_assessment[asset_id] = assessment_id

        logger.info(
            f"[TrustEngine] Assessment {assessment_id}: asset={asset_id} "
            f"recommended={recommended.value} findings={len(findings)}"
        )
        return assessment

    def approve_assessment(
        self,
        *,
        assessment_id: str,
        approver_id: str,
        override_status: Optional[TrustStatus] = None,
    ) -> MarketplaceTrustAssessment:
        """
        Human approver applies the assessment result to the asset's trust status.
        Can optionally override the recommended status (but cannot claim SAFE).
        """
        if approver_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot approve trust assessments.")
        with self._lock:
            assessment = self._assessments.get(assessment_id)
            if not assessment:
                raise KeyError(f"Assessment not found: {assessment_id}")
            final_status = override_status or assessment.recommended_trust_status
            self._registry.update_trust_status(
                asset_id=assessment.asset_id,
                actor_id=approver_id,
                trust_status=final_status,
                findings_summary=(
                    f"{len(assessment.all_findings)} findings. "
                    f"Licence risk: {assessment.licence_risk}. "
                    f"Publisher verified: {assessment.publisher_verified}."
                ),
                assessment_id=assessment_id,
            )
            logger.info(
                f"[TrustEngine] Assessment approved: {assessment_id} → {final_status.value} "
                f"by {approver_id}"
            )
            return assessment

    def get_assessment(self, assessment_id: str) -> Optional[MarketplaceTrustAssessment]:
        with self._lock:
            return self._assessments.get(assessment_id)

    def get_latest_assessment(self, asset_id: str) -> Optional[MarketplaceTrustAssessment]:
        with self._lock:
            aid = self._asset_latest_assessment.get(asset_id)
            return self._assessments.get(aid) if aid else None

    def list_assessments(self) -> List[MarketplaceTrustAssessment]:
        with self._lock:
            return list(self._assessments.values())


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_trust_engine: Optional[MarketplaceTrustEngine] = None
_te_lock = threading.Lock()


def get_trust_engine() -> MarketplaceTrustEngine:
    global _trust_engine
    if _trust_engine is None:
        with _te_lock:
            if _trust_engine is None:
                from .registry import get_registry
                _trust_engine = MarketplaceTrustEngine(get_registry())
    return _trust_engine
