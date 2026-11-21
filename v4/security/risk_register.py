# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 4G — AI Risk Register and Compliance Evidence.

Risk register for models, agents and AI applications tracking:
- Risk category, severity, likelihood, potential impact
- Affected assets, mitigation, residual risk
- Risk owner, assessment date, review date

Compliance framework mapping to:
- NIST AI RMF (GOVERN, MAP, MEASURE, MANAGE)
- ISO/IEC 42001
- OWASP Top 10 for LLM Applications
- MITRE ATLAS
- EU AI Act requirements (high-level)

IMPORTANT:
- This framework does NOT claim regulatory compliance or certification.
- Technical controls, documented procedures, evidence and independent
  certification are explicitly distinguished.
- Evidence is exportable but does not substitute for formal audit.
"""
from __future__ import annotations

import datetime
import json
import threading
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger("orquanta.security.risk_register")


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _default_review() -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(days=90)).isoformat() + "Z"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RiskCategory(str, Enum):
    SECURITY          = "SECURITY"
    SAFETY            = "SAFETY"
    FAIRNESS          = "FAIRNESS"
    PRIVACY           = "PRIVACY"
    RELIABILITY       = "RELIABILITY"
    ACCOUNTABILITY    = "ACCOUNTABILITY"
    TRANSPARENCY      = "TRANSPARENCY"
    SUPPLY_CHAIN      = "SUPPLY_CHAIN"
    OPERATIONAL       = "OPERATIONAL"
    COMPLIANCE        = "COMPLIANCE"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    INFO     = "INFO"


class Likelihood(str, Enum):
    CERTAIN  = "CERTAIN"
    LIKELY   = "LIKELY"
    POSSIBLE = "POSSIBLE"
    UNLIKELY = "UNLIKELY"
    RARE     = "RARE"


class RiskStatus(str, Enum):
    OPEN        = "OPEN"
    MITIGATED   = "MITIGATED"
    ACCEPTED    = "ACCEPTED"
    TRANSFERRED = "TRANSFERRED"
    CLOSED      = "CLOSED"


# Compliance framework identifiers
class ComplianceFramework(str, Enum):
    NIST_AI_RMF  = "NIST_AI_RMF"
    ISO_42001    = "ISO_IEC_42001"
    OWASP_LLM   = "OWASP_TOP10_LLM"
    MITRE_ATLAS  = "MITRE_ATLAS"
    EU_AI_ACT    = "EU_AI_ACT"


# ---------------------------------------------------------------------------
# Risk Register entry
# ---------------------------------------------------------------------------

@dataclass
class RiskEntry:
    risk_id: str
    asset_type: str             # "model" | "agent" | "application" | "data" | "infrastructure"
    asset_id: str
    tenant_id: str
    category: RiskCategory
    title: str
    description: str
    severity: Severity
    likelihood: Likelihood
    potential_impact: str
    mitigation: str
    residual_risk: Severity
    risk_owner: str
    status: RiskStatus = RiskStatus.OPEN
    affected_assets: List[str] = field(default_factory=list)
    compliance_refs: List[str] = field(default_factory=list)   # e.g. ["NIST:GOVERN-1.1", "OWASP:LLM01"]
    evidence_ids: List[str] = field(default_factory=list)
    assessment_date: str = field(default_factory=lambda: _now())
    review_date: str = field(default_factory=lambda: _default_review())
    closed_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Evidence item
# ---------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    evidence_id: str
    risk_id: str
    control_id: str
    framework: ComplianceFramework
    control_reference: str          # e.g. "GOVERN-1.1" or "LLM01"
    control_title: str
    evidence_type: str              # "technical_control" | "procedure" | "test_result" | "audit_log"
    description: str
    implementation_status: str      # "implemented" | "partial" | "planned" | "not_applicable"
    evidence_data: Dict[str, Any] = field(default_factory=dict)
    collected_at: str = field(default_factory=lambda: _now())
    collected_by: str = "system"
    # Explicit disclaimer: evidence ≠ certification
    disclaimer: str = (
        "This evidence represents technical controls and documented procedures. "
        "It does NOT constitute regulatory compliance certification or independent audit. "
        "Formal certification requires accredited third-party assessment."
    )

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Control catalogue
# ---------------------------------------------------------------------------

CONTROL_CATALOGUE: Dict[str, Dict] = {
    # NIST AI RMF
    "NIST:GOVERN-1.1": {
        "framework": ComplianceFramework.NIST_AI_RMF,
        "reference": "GOVERN-1.1",
        "title": "Policies, processes and procedures are established for AI risk management",
        "category": "GOVERN",
    },
    "NIST:GOVERN-2.1": {
        "framework": ComplianceFramework.NIST_AI_RMF,
        "reference": "GOVERN-2.1",
        "title": "AI risk tolerances are established through organizational risk governance",
        "category": "GOVERN",
    },
    "NIST:MAP-1.1": {
        "framework": ComplianceFramework.NIST_AI_RMF,
        "reference": "MAP-1.1",
        "title": "Context is established and understood",
        "category": "MAP",
    },
    "NIST:MEASURE-2.1": {
        "framework": ComplianceFramework.NIST_AI_RMF,
        "reference": "MEASURE-2.1",
        "title": "AI system risk or impact metrics and information are defined and evaluated",
        "category": "MEASURE",
    },
    "NIST:MANAGE-1.1": {
        "framework": ComplianceFramework.NIST_AI_RMF,
        "reference": "MANAGE-1.1",
        "title": "Identified and prioritised risks are responded to in accordance with organisational risk tolerance",
        "category": "MANAGE",
    },
    # OWASP LLM Top 10
    "OWASP:LLM01": {
        "framework": ComplianceFramework.OWASP_LLM,
        "reference": "LLM01",
        "title": "Prompt Injection",
        "category": "Security",
    },
    "OWASP:LLM02": {
        "framework": ComplianceFramework.OWASP_LLM,
        "reference": "LLM02",
        "title": "Insecure Output Handling",
        "category": "Security",
    },
    "OWASP:LLM03": {
        "framework": ComplianceFramework.OWASP_LLM,
        "reference": "LLM03",
        "title": "Training Data Poisoning",
        "category": "Security",
    },
    "OWASP:LLM06": {
        "framework": ComplianceFramework.OWASP_LLM,
        "reference": "LLM06",
        "title": "Sensitive Information Disclosure",
        "category": "Privacy",
    },
    "OWASP:LLM08": {
        "framework": ComplianceFramework.OWASP_LLM,
        "reference": "LLM08",
        "title": "Excessive Agency",
        "category": "Safety",
    },
    "OWASP:LLM09": {
        "framework": ComplianceFramework.OWASP_LLM,
        "reference": "LLM09",
        "title": "Overreliance",
        "category": "Safety",
    },
    # MITRE ATLAS
    "ATLAS:AML.T0010": {
        "framework": ComplianceFramework.MITRE_ATLAS,
        "reference": "AML.T0010",
        "title": "ML Supply Chain Compromise",
        "category": "Supply Chain",
    },
    "ATLAS:AML.T0048": {
        "framework": ComplianceFramework.MITRE_ATLAS,
        "reference": "AML.T0048",
        "title": "Backdoor ML Model",
        "category": "Security",
    },
    "ATLAS:AML.T0049": {
        "framework": ComplianceFramework.MITRE_ATLAS,
        "reference": "AML.T0049",
        "title": "Exploit Public-Facing ML Model",
        "category": "Security",
    },
    # EU AI Act (high-level)
    "EU_AI:ART13": {
        "framework": ComplianceFramework.EU_AI_ACT,
        "reference": "Article 13",
        "title": "Transparency and provision of information to users",
        "category": "Transparency",
    },
    "EU_AI:ART14": {
        "framework": ComplianceFramework.EU_AI_ACT,
        "reference": "Article 14",
        "title": "Human oversight of high-risk AI systems",
        "category": "Accountability",
    },
    "EU_AI:ART17": {
        "framework": ComplianceFramework.EU_AI_ACT,
        "reference": "Article 17",
        "title": "Quality management system for high-risk AI",
        "category": "Governance",
    },
}


# ---------------------------------------------------------------------------
# Risk Register
# ---------------------------------------------------------------------------

class AIRiskRegister:

    def __init__(self):
        self._lock = threading.Lock()
        self._risks: Dict[str, RiskEntry] = {}
        self._evidence: Dict[str, EvidenceItem] = {}
        self._load_seed_risks()

    def _load_seed_risks(self):
        """Pre-populate with common AI platform risks."""
        seeds = [
            RiskEntry(
                risk_id="risk-prompt-injection",
                asset_type="application",
                asset_id="orquanta-inference-api",
                tenant_id="platform",
                category=RiskCategory.SECURITY,
                title="Prompt Injection via User Inputs",
                description=(
                    "Malicious prompts may attempt to override system instructions, "
                    "exfiltrate data or cause the model to perform unintended actions. "
                    "OWASP LLM01."
                ),
                severity=Severity.HIGH,
                likelihood=Likelihood.LIKELY,
                potential_impact="Data exfiltration, instruction override, reputational damage.",
                mitigation=(
                    "Multi-signal heuristic assessment (not keyword-only), input isolation, "
                    "output validation, audit logging of all inference requests."
                ),
                residual_risk=Severity.MEDIUM,
                risk_owner="platform-security",
                compliance_refs=["OWASP:LLM01", "NIST:MANAGE-1.1"],
            ),
            RiskEntry(
                risk_id="risk-supply-chain",
                asset_type="model",
                asset_id="*",
                tenant_id="platform",
                category=RiskCategory.SUPPLY_CHAIN,
                title="Model Supply Chain Compromise",
                description=(
                    "Models from external repositories may contain backdoors, malicious "
                    "pickle code, or tampered weights. MITRE ATLAS AML.T0010."
                ),
                severity=Severity.CRITICAL,
                likelihood=Likelihood.POSSIBLE,
                potential_impact="Arbitrary code execution, model backdoor, data poisoning.",
                mitigation=(
                    "Revision hash verification, format risk assessment (safetensors preferred), "
                    "custom code detection, human reviewer clearance required before deployment."
                ),
                residual_risk=Severity.MEDIUM,
                risk_owner="platform-security",
                compliance_refs=["ATLAS:AML.T0010", "ATLAS:AML.T0048", "NIST:MAP-1.1"],
            ),
            RiskEntry(
                risk_id="risk-agent-excessive-agency",
                asset_type="agent",
                asset_id="*",
                tenant_id="platform",
                category=RiskCategory.SAFETY,
                title="Excessive Agent Autonomy",
                description=(
                    "Autonomous agents may take high-impact actions beyond their intended scope, "
                    "including tool execution with side effects. OWASP LLM08."
                ),
                severity=Severity.HIGH,
                likelihood=Likelihood.POSSIBLE,
                potential_impact="Unintended resource consumption, data modification, financial loss.",
                mitigation=(
                    "Explicit tool permission boundaries, spend limits, execution time limits, "
                    "human approval gate for high-impact operations, session-scoped permissions."
                ),
                residual_risk=Severity.LOW,
                risk_owner="platform-security",
                compliance_refs=["OWASP:LLM08", "EU_AI:ART14", "NIST:GOVERN-1.1"],
            ),
            RiskEntry(
                risk_id="risk-sensitive-data-disclosure",
                asset_type="application",
                asset_id="orquanta-inference-api",
                tenant_id="platform",
                category=RiskCategory.PRIVACY,
                title="Sensitive Information Disclosure via Model Output",
                description=(
                    "Models may inadvertently include PII, credentials or sensitive data in outputs. "
                    "OWASP LLM06."
                ),
                severity=Severity.HIGH,
                likelihood=Likelihood.POSSIBLE,
                potential_impact="PII exposure, credential leakage, compliance violations.",
                mitigation=(
                    "Output validation and redaction for known patterns (API keys, emails, cards). "
                    "Pattern-based redaction with explicit limitation disclaimer."
                ),
                residual_risk=Severity.MEDIUM,
                risk_owner="platform-security",
                compliance_refs=["OWASP:LLM06", "EU_AI:ART13"],
            ),
        ]
        for r in seeds:
            self._risks[r.risk_id] = r

    # -- Risk management -----------------------------------------------------

    def add_risk(
        self,
        asset_type: str,
        asset_id: str,
        tenant_id: str,
        category: RiskCategory,
        title: str,
        description: str,
        severity: Severity,
        likelihood: Likelihood,
        potential_impact: str,
        mitigation: str,
        residual_risk: Severity,
        risk_owner: str,
        compliance_refs: Optional[List[str]] = None,
    ) -> RiskEntry:
        entry = RiskEntry(
            risk_id=str(uuid.uuid4()),
            asset_type=asset_type,
            asset_id=asset_id,
            tenant_id=tenant_id,
            category=category,
            title=title,
            description=description,
            severity=severity,
            likelihood=likelihood,
            potential_impact=potential_impact,
            mitigation=mitigation,
            residual_risk=residual_risk,
            risk_owner=risk_owner,
            compliance_refs=compliance_refs or [],
        )
        with self._lock:
            self._risks[entry.risk_id] = entry
        logger.info("[risk_register] Added risk %s: %s", entry.risk_id, title[:60])
        return entry

    def update_risk_status(self, risk_id: str, status: RiskStatus, notes: str = "") -> Optional[RiskEntry]:
        entry = self._risks.get(risk_id)
        if not entry:
            return None
        entry.status = status
        entry.notes = notes
        if status == RiskStatus.CLOSED:
            entry.closed_at = _now()
        return entry

    def list_risks(
        self,
        tenant_id: Optional[str] = None,
        category: Optional[RiskCategory] = None,
        severity: Optional[Severity] = None,
        status: Optional[RiskStatus] = None,
    ) -> List[Dict]:
        with self._lock:
            risks = list(self._risks.values())
        if tenant_id:
            risks = [r for r in risks if r.tenant_id in (tenant_id, "platform")]
        if category:
            risks = [r for r in risks if r.category == category]
        if severity:
            risks = [r for r in risks if r.severity == severity]
        if status:
            risks = [r for r in risks if r.status == status]
        return [r.to_dict() for r in risks]

    # -- Evidence collection -------------------------------------------------

    def add_evidence(
        self,
        risk_id: str,
        control_id: str,
        evidence_type: str,
        description: str,
        implementation_status: str,
        evidence_data: Optional[Dict] = None,
        collected_by: str = "system",
    ) -> Optional[EvidenceItem]:
        control = CONTROL_CATALOGUE.get(control_id)
        if not control:
            logger.warning("[risk_register] Unknown control_id: %s", control_id)
            return None

        risk = self._risks.get(risk_id)
        if not risk:
            return None

        evidence = EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            risk_id=risk_id,
            control_id=control_id,
            framework=control["framework"],
            control_reference=control["reference"],
            control_title=control["title"],
            evidence_type=evidence_type,
            description=description,
            implementation_status=implementation_status,
            evidence_data=evidence_data or {},
            collected_by=collected_by,
        )
        with self._lock:
            self._evidence[evidence.evidence_id] = evidence
            if evidence.evidence_id not in risk.evidence_ids:
                risk.evidence_ids.append(evidence.evidence_id)

        return evidence

    def list_evidence(
        self,
        risk_id: Optional[str] = None,
        framework: Optional[ComplianceFramework] = None,
    ) -> List[Dict]:
        with self._lock:
            items = list(self._evidence.values())
        if risk_id:
            items = [e for e in items if e.risk_id == risk_id]
        if framework:
            items = [e for e in items if e.framework == framework]
        return [e.to_dict() for e in items]

    # -- Reporting -----------------------------------------------------------

    def generate_risk_report(self, tenant_id: str) -> Dict:
        """Generate an exportable risk summary report."""
        risks = self.list_risks(tenant_id=tenant_id)
        evidence = self.list_evidence()

        severity_counts: Dict[str, int] = {}
        category_counts: Dict[str, int] = {}
        for r in risks:
            sev = r.get("severity", "UNKNOWN")
            cat = r.get("category", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "report_id": str(uuid.uuid4()),
            "generated_at": _now(),
            "tenant_id": tenant_id,
            "total_risks": len(risks),
            "severity_breakdown": severity_counts,
            "category_breakdown": category_counts,
            "open_risks": sum(1 for r in risks if r.get("status") == "OPEN"),
            "evidence_count": len(evidence),
            "disclaimer": (
                "This report reflects automated technical risk tracking only. "
                "It does NOT represent regulatory compliance, legal advice, or independent audit. "
                "Formal compliance assessment requires accredited third-party review."
            ),
            "risks": risks,
            "evidence_summary": [
                {
                    "evidence_id": e.get("evidence_id"),
                    "control_id": e.get("control_id"),
                    "framework": e.get("framework"),
                    "implementation_status": e.get("implementation_status"),
                }
                for e in evidence
            ],
        }

    def export_evidence_json(self, tenant_id: str) -> str:
        """Export all evidence as JSON string for external audit use."""
        report = self.generate_risk_report(tenant_id)
        return json.dumps(report, indent=2, default=str)


_RISK_REGISTER = AIRiskRegister()


def get_risk_register() -> AIRiskRegister:
    return _RISK_REGISTER
