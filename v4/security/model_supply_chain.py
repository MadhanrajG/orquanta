# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 4D — Model Security and Supply Chain.

Creates a model security service that:
- Tracks model provenance, publisher identity, revision, file integrity
- Checks licence information and commercial permissions
- Flags unsafe model formats (pickle, arbitrary code)
- Detects untrusted custom code in model configs
- Maintains a model risk record and security assessment history

IMPORTANT:
- A model is NEVER marked safe solely because it comes from a popular repository.
- Supply-chain checks are technical controls, not certifications.
- All results carry explicit limitation disclaimers.
"""
from __future__ import annotations

import datetime
import hashlib
import threading
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger("orquanta.security.model_supply_chain")


# ---------------------------------------------------------------------------
# Risk and format enums
# ---------------------------------------------------------------------------

class ModelRiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    UNKNOWN  = "UNKNOWN"


class FormatRisk(str, Enum):
    """Model serialisation format risk classification."""
    SAFE       = "SAFE"       # safetensors, GGUF
    CAUTION    = "CAUTION"    # ONNX (depends on custom ops)
    UNSAFE     = "UNSAFE"     # pickle-based: .pt, .bin without safetensors
    UNKNOWN    = "UNKNOWN"


FORMAT_RISK_MAP: Dict[str, FormatRisk] = {
    ".safetensors": FormatRisk.SAFE,
    ".gguf":        FormatRisk.SAFE,
    ".onnx":        FormatRisk.CAUTION,
    ".pt":          FormatRisk.UNSAFE,
    ".pth":         FormatRisk.UNSAFE,
    ".bin":         FormatRisk.UNSAFE,     # Often pickle
    ".pkl":         FormatRisk.UNSAFE,
    ".pickle":      FormatRisk.UNSAFE,
}

# Licence risk (commercial context)
LICENCE_COMMERCIAL_RISK: Dict[str, ModelRiskLevel] = {
    "apache-2.0":    ModelRiskLevel.LOW,
    "mit":           ModelRiskLevel.LOW,
    "bsd-2-clause":  ModelRiskLevel.LOW,
    "bsd-3-clause":  ModelRiskLevel.LOW,
    "cc-by-4.0":     ModelRiskLevel.LOW,
    "cc-by-sa-4.0":  ModelRiskLevel.MEDIUM,
    "llama2":        ModelRiskLevel.MEDIUM,   # Meta commercial terms
    "llama3":        ModelRiskLevel.MEDIUM,
    "gemma":         ModelRiskLevel.MEDIUM,
    "cc-by-nc-4.0":  ModelRiskLevel.HIGH,     # Non-commercial
    "cc-by-nc-sa-4.0": ModelRiskLevel.HIGH,
    "openrail":      ModelRiskLevel.MEDIUM,
    "openrail++":    ModelRiskLevel.MEDIUM,
    "bigscience-bloom-rail-1.0": ModelRiskLevel.MEDIUM,
    "other":         ModelRiskLevel.UNKNOWN,
    "proprietary":   ModelRiskLevel.HIGH,
    "unknown":       ModelRiskLevel.UNKNOWN,
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ModelSecurityFinding:
    finding_id: str
    category: str           # "format" | "licence" | "provenance" | "config" | "dependency"
    severity: ModelRiskLevel
    title: str
    description: str
    recommendation: str
    cve_ids: List[str] = field(default_factory=list)
    mitre_atlas: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: _now())


@dataclass
class ModelSecurityAssessment:
    assessment_id: str
    model_id: str
    model_revision: str
    publisher: str
    source_url: str
    overall_risk: ModelRiskLevel
    format_risk: FormatRisk
    licence: str
    licence_risk: ModelRiskLevel
    commercial_use: Optional[bool]      # None = unknown
    provenance_verified: bool
    revision_hash_verified: bool
    custom_code_detected: bool
    findings: List[ModelSecurityFinding] = field(default_factory=list)
    assessed_by: str = "orquanta-supply-chain-v1"
    assessed_at: str = field(default_factory=lambda: _now())
    limitation: str = (
        "This assessment reflects automated technical checks only. "
        "It is NOT a security certification. A model from a popular repository "
        "is not automatically safe. Manual review and independent audit are recommended "
        "for production deployments."
    )
    is_cleared_for_deployment: bool = False    # Must be explicitly set by human reviewer

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d


@dataclass
class ModelRiskRecord:
    """Persistent risk record for a model across all assessments."""
    record_id: str
    model_id: str
    current_risk: ModelRiskLevel
    assessments: List[str]          # assessment_ids
    risk_owner: str
    assessment_date: str
    review_date: str
    mitigation: str = ""
    residual_risk: ModelRiskLevel = ModelRiskLevel.UNKNOWN
    notes: str = ""
    is_approved_for_production: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _default_review_date() -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(days=90)).isoformat() + "Z"


# ---------------------------------------------------------------------------
# Supply chain security engine
# ---------------------------------------------------------------------------

class ModelSupplyChainSecurity:

    def __init__(self):
        self._lock = threading.Lock()
        self._assessments: Dict[str, ModelSecurityAssessment] = {}
        self._risk_records: Dict[str, ModelRiskRecord] = {}  # model_id → record

    def assess_model(
        self,
        model_id: str,
        publisher: str,
        source_url: str,
        revision: str,
        expected_revision: Optional[str],
        file_extensions: List[str],     # e.g. [".safetensors", ".json"]
        licence: str,
        commercial_use: Optional[bool],
        config_files: Optional[List[str]] = None,
        expected_checksum: Optional[str] = None,
        actual_checksum: Optional[str] = None,
    ) -> ModelSecurityAssessment:
        """
        Run a security assessment of a model's supply chain.
        Never marks a model as safe solely due to popularity.
        """
        findings: List[ModelSecurityFinding] = []

        # 1. Provenance check
        provenance_verified = bool(publisher and source_url)
        if not publisher:
            findings.append(ModelSecurityFinding(
                finding_id=str(uuid.uuid4()),
                category="provenance",
                severity=ModelRiskLevel.HIGH,
                title="Unknown model publisher",
                description="No publisher identity provided. Model provenance cannot be verified.",
                recommendation="Obtain publisher identity and verify model source URL.",
                mitre_atlas=["AML.T0010"],
            ))

        # 2. Revision integrity check
        revision_ok = True
        if expected_revision and revision != expected_revision:
            revision_ok = False
            findings.append(ModelSecurityFinding(
                finding_id=str(uuid.uuid4()),
                category="provenance",
                severity=ModelRiskLevel.CRITICAL,
                title="Model revision mismatch",
                description=f"Expected revision '{expected_revision}', got '{revision}'. Model may have been tampered with.",
                recommendation="Do not deploy. Re-download from authoritative source and verify.",
                mitre_atlas=["AML.T0010", "AML.T0049"],
            ))

        # 3. Checksum integrity
        checksum_ok = True
        if expected_checksum and actual_checksum:
            if expected_checksum != actual_checksum:
                checksum_ok = False
                findings.append(ModelSecurityFinding(
                    finding_id=str(uuid.uuid4()),
                    category="provenance",
                    severity=ModelRiskLevel.CRITICAL,
                    title="File integrity check failed",
                    description="Checksum mismatch: model files may have been modified.",
                    recommendation="Do not deploy. Download from authoritative source.",
                    mitre_atlas=["AML.T0010"],
                ))

        # 4. Format risk assessment
        format_risks = [FORMAT_RISK_MAP.get(ext, FormatRisk.UNKNOWN) for ext in file_extensions]
        worst_format_risk = FormatRisk.SAFE
        for fr in format_risks:
            if fr == FormatRisk.UNSAFE:
                worst_format_risk = FormatRisk.UNSAFE
                break
            if fr == FormatRisk.CAUTION:
                worst_format_risk = FormatRisk.CAUTION
            if fr == FormatRisk.UNKNOWN and worst_format_risk != FormatRisk.CAUTION:
                worst_format_risk = FormatRisk.UNKNOWN

        if worst_format_risk == FormatRisk.UNSAFE:
            findings.append(ModelSecurityFinding(
                finding_id=str(uuid.uuid4()),
                category="format",
                severity=ModelRiskLevel.HIGH,
                title="Unsafe model serialisation format",
                description=(
                    "Model uses pickle-based serialisation (.pt, .pth, .bin, .pkl). "
                    "Pickle files can execute arbitrary code on deserialisation."
                ),
                recommendation=(
                    "Convert to safetensors format. Never load untrusted pickle files. "
                    "Use trust_remote_code=False."
                ),
                mitre_atlas=["AML.T0049"],
            ))

        # 5. Licence risk
        licence_key = licence.lower().strip()
        licence_risk = LICENCE_COMMERCIAL_RISK.get(licence_key, ModelRiskLevel.UNKNOWN)
        if licence_risk in (ModelRiskLevel.UNKNOWN, ModelRiskLevel.HIGH, ModelRiskLevel.CRITICAL):
            findings.append(ModelSecurityFinding(
                finding_id=str(uuid.uuid4()),
                category="licence",
                severity=licence_risk,
                title=f"Licence risk: {licence}",
                description=(
                    f"Licence '{licence}' has risk level {licence_risk.value}. "
                    "Commercial use may be restricted. Legal review required."
                ),
                recommendation="Obtain legal review before commercial deployment.",
            ))

        if commercial_use is False and licence_key in ("cc-by-nc-4.0", "cc-by-nc-sa-4.0"):
            findings.append(ModelSecurityFinding(
                finding_id=str(uuid.uuid4()),
                category="licence",
                severity=ModelRiskLevel.CRITICAL,
                title="Non-commercial licence for commercial use",
                description="Model licence explicitly prohibits commercial use.",
                recommendation="Do not deploy commercially without explicit permission.",
            ))

        # 6. Custom code detection
        custom_code = False
        dangerous_config_keys = ["auto_map", "trust_remote_code", "custom_pipelines"]
        if config_files:
            for cfg_content in config_files:
                if any(key in cfg_content for key in dangerous_config_keys):
                    custom_code = True
                    findings.append(ModelSecurityFinding(
                        finding_id=str(uuid.uuid4()),
                        category="config",
                        severity=ModelRiskLevel.HIGH,
                        title="Custom code or trust_remote_code detected",
                        description=(
                            "Model configuration contains 'trust_remote_code', 'auto_map', "
                            "or 'custom_pipelines'. This allows arbitrary code execution."
                        ),
                        recommendation=(
                            "Review all custom model code before execution. "
                            "Only run with trust_remote_code=True in isolated environments."
                        ),
                        mitre_atlas=["AML.T0049", "AML.T0048"],
                    ))
                    break

        # 7. Overall risk aggregation
        severity_rank = {
            ModelRiskLevel.CRITICAL: 4,
            ModelRiskLevel.HIGH: 3,
            ModelRiskLevel.MEDIUM: 2,
            ModelRiskLevel.LOW: 1,
            ModelRiskLevel.UNKNOWN: 2,
        }
        if findings:
            worst = max(findings, key=lambda f: severity_rank.get(f.severity, 0))
            overall_risk = worst.severity
        else:
            overall_risk = ModelRiskLevel.LOW

        assessment = ModelSecurityAssessment(
            assessment_id=str(uuid.uuid4()),
            model_id=model_id,
            model_revision=revision,
            publisher=publisher,
            source_url=source_url,
            overall_risk=overall_risk,
            format_risk=worst_format_risk,
            licence=licence,
            licence_risk=licence_risk,
            commercial_use=commercial_use,
            provenance_verified=provenance_verified,
            revision_hash_verified=revision_ok and checksum_ok,
            custom_code_detected=custom_code,
            findings=findings,
            # Never auto-clear for deployment — requires human reviewer
            is_cleared_for_deployment=False,
        )

        with self._lock:
            self._assessments[assessment.assessment_id] = assessment

        # Update or create risk record
        self._update_risk_record(model_id, assessment)

        logger.info(
            "[supply_chain] Assessed model=%s revision=%s overall_risk=%s findings=%d cleared=%s",
            model_id, revision, overall_risk.value, len(findings), False,
        )
        return assessment

    def _update_risk_record(self, model_id: str, assessment: ModelSecurityAssessment):
        with self._lock:
            existing = self._risk_records.get(model_id)
            if existing:
                existing.current_risk = assessment.overall_risk
                existing.assessments.append(assessment.assessment_id)
                existing.assessment_date = _now()
                existing.review_date = _default_review_date()
            else:
                self._risk_records[model_id] = ModelRiskRecord(
                    record_id=str(uuid.uuid4()),
                    model_id=model_id,
                    current_risk=assessment.overall_risk,
                    assessments=[assessment.assessment_id],
                    risk_owner="unassigned",
                    assessment_date=_now(),
                    review_date=_default_review_date(),
                )

    def clear_for_deployment(
        self,
        assessment_id: str,
        reviewer_id: str,
        notes: str = "",
    ) -> ModelSecurityAssessment:
        """
        A human reviewer must explicitly clear a model for deployment.
        No automated process may set is_cleared_for_deployment=True.
        """
        if reviewer_id in ("system", "auto", ""):
            raise PermissionError(
                "Only a named human reviewer may clear a model for deployment. "
                "System actors are not permitted."
            )
        assessment = self._assessments.get(assessment_id)
        if not assessment:
            raise ValueError(f"Assessment {assessment_id} not found")
        if assessment.overall_risk == ModelRiskLevel.CRITICAL:
            raise PermissionError(
                "Critical-risk models require escalated approval before clearance."
            )
        assessment.is_cleared_for_deployment = True
        logger.info(
            "[supply_chain] Model %s cleared for deployment by %s",
            assessment.model_id, reviewer_id,
        )
        return assessment

    def get_assessment(self, assessment_id: str) -> Optional[ModelSecurityAssessment]:
        return self._assessments.get(assessment_id)

    def get_risk_record(self, model_id: str) -> Optional[ModelRiskRecord]:
        return self._risk_records.get(model_id)

    def list_assessments(self, model_id: Optional[str] = None) -> List[Dict]:
        with self._lock:
            assessments = list(self._assessments.values())
        if model_id:
            assessments = [a for a in assessments if a.model_id == model_id]
        return [a.to_dict() for a in assessments]

    def list_risk_records(self) -> List[Dict]:
        with self._lock:
            return [r.to_dict() for r in self._risk_records.values()]


_SUPPLY_CHAIN = ModelSupplyChainSecurity()


def get_supply_chain_security() -> ModelSupplyChainSecurity:
    return _SUPPLY_CHAIN
