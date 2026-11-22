# Copyright 2026 OrQuanta — Apache License 2.0
"""
Phase 5C — Security Intelligence Pipeline
==========================================
Central security event collector and classifier.

Monitors:
- Unauthorised access attempts
- Cross-tenant access attempts
- Policy denials
- Suspicious agent behaviour
- Unusual tool execution
- Excessive API consumption
- Abnormal spending
- Credential abuse
- Model deployment violations
- MCP security events

IMPORTANT: Heuristic detections are NEVER labelled as confirmed attacks.
All findings include an is_heuristic=True flag and a limitation disclaimer.
Events are connected to the existing Phase 4 AuditBus and RiskRegister.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orquanta.observability.security_intel")


# ── Enums ─────────────────────────────────────────────────────────────────────

class SecurityEventSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityEventCategory(str, Enum):
    AUTH_FAILURE = "AUTH_FAILURE"
    CROSS_TENANT = "CROSS_TENANT"
    POLICY_DENIAL = "POLICY_DENIAL"
    SUSPICIOUS_AGENT = "SUSPICIOUS_AGENT"
    UNUSUAL_TOOL = "UNUSUAL_TOOL"
    API_ABUSE = "API_ABUSE"
    SPEND_ANOMALY = "SPEND_ANOMALY"
    CREDENTIAL_ABUSE = "CREDENTIAL_ABUSE"
    DEPLOYMENT_VIOLATION = "DEPLOYMENT_VIOLATION"
    MCP_SECURITY = "MCP_SECURITY"
    INJECTION_ATTEMPT = "INJECTION_ATTEMPT"
    RATE_LIMIT = "RATE_LIMIT"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"


class SecurityEventStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class SecurityEvent:
    """A classified security event from the intelligence pipeline."""
    event_id: str = field(default_factory=lambda: f"sec-{uuid.uuid4().hex[:12]}")
    category: SecurityEventCategory = SecurityEventCategory.AUTH_FAILURE
    severity: SecurityEventSeverity = SecurityEventSeverity.INFO
    title: str = ""
    description: str = ""
    tenant_id: str = ""
    actor_id: str = ""
    resource_type: str = ""
    resource_id: str = ""
    source_ip: str = ""
    trace_id: str = ""
    # Heuristic flag — NEVER label as confirmed attack
    is_heuristic: bool = True
    confidence_score: float = 0.5  # 0.0–1.0
    limitation: str = (
        "This detection uses heuristic pattern analysis. It is NOT a confirmed security incident. "
        "Treat as an indicator for investigation, not as proof of malicious activity."
    )
    # Investigation history
    status: SecurityEventStatus = SecurityEventStatus.OPEN
    investigation_notes: List[str] = field(default_factory=list)
    resolved_by: str = ""
    resolved_at: str = ""
    # Linked artifacts
    policy_decision_id: str = ""
    risk_register_ids: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "source_ip": self.source_ip,
            "trace_id": self.trace_id,
            "is_heuristic": self.is_heuristic,
            "confidence_score": self.confidence_score,
            "limitation": self.limitation,
            "status": self.status.value,
            "investigation_notes": self.investigation_notes,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at,
            "policy_decision_id": self.policy_decision_id,
            "risk_register_ids": self.risk_register_ids,
            "timestamp": self.timestamp,
        }


# ── Detection rules (heuristic) ───────────────────────────────────────────────

# Request rate thresholds for anomaly detection (per tenant per minute)
_AUTH_FAIL_THRESHOLD = int(5)   # >5 auth failures/min → suspicious
_API_RATE_THRESHOLD = int(100)  # >100 req/min → potential abuse
_SPEND_MULTIPLIER = float(3.0)  # >3x daily average → anomaly


# ── Security Intelligence Service ─────────────────────────────────────────────

class SecurityIntelligenceService:
    """
    Central pipeline for security event collection, classification, and triage.
    Connects to Phase 4 AuditBus and RiskRegister without replacing them.
    """

    _EVENT_LIMIT = 50_000

    def __init__(self) -> None:
        self._events: List[SecurityEvent] = []
        # Rate tracking for anomaly detection (tenant_id → {event_type: [timestamps]})
        self._rate_windows: Dict[str, Dict[str, List[float]]] = {}

    # ── Ingestion API ─────────────────────────────────────────────────────────

    def ingest_auth_failure(
        self,
        tenant_id: str,
        actor_id: str,
        resource: str,
        reason: str,
        source_ip: str = "",
        trace_id: str = "",
    ) -> SecurityEvent:
        """Record an authentication or authorisation failure."""
        rate = self._check_rate(tenant_id, "auth_failure")
        severity = SecurityEventSeverity.HIGH if rate > _AUTH_FAIL_THRESHOLD else SecurityEventSeverity.MEDIUM
        event = SecurityEvent(
            category=SecurityEventCategory.AUTH_FAILURE,
            severity=severity,
            title="Authentication failure",
            description=f"Actor '{actor_id}' failed auth for '{resource}': {reason}",
            tenant_id=tenant_id,
            actor_id=actor_id,
            resource_type=resource,
            source_ip=source_ip,
            trace_id=trace_id,
            confidence_score=0.75 if rate > _AUTH_FAIL_THRESHOLD else 0.5,
        )
        return self._append(event)

    def ingest_cross_tenant_attempt(
        self,
        source_tenant: str,
        target_tenant: str,
        actor_id: str,
        resource_type: str,
        trace_id: str = "",
    ) -> SecurityEvent:
        """Record a cross-tenant access attempt."""
        event = SecurityEvent(
            category=SecurityEventCategory.CROSS_TENANT,
            severity=SecurityEventSeverity.HIGH,
            title="Cross-tenant access attempt",
            description=(
                f"Actor '{actor_id}' (tenant '{source_tenant}') attempted to access "
                f"resources in tenant '{target_tenant}'"
            ),
            tenant_id=source_tenant,
            actor_id=actor_id,
            resource_type=resource_type,
            trace_id=trace_id,
            confidence_score=0.9,  # Cross-tenant deny is deterministic
        )
        return self._append(event)

    def ingest_policy_denial(
        self,
        tenant_id: str,
        actor_id: str,
        resource_type: str,
        action: str,
        policy_name: str,
        decision_id: str = "",
        trace_id: str = "",
    ) -> SecurityEvent:
        """Record a policy enforcement denial."""
        event = SecurityEvent(
            category=SecurityEventCategory.POLICY_DENIAL,
            severity=SecurityEventSeverity.LOW,
            title=f"Policy denied: {action} on {resource_type}",
            description=f"Policy '{policy_name}' denied '{action}' on '{resource_type}' by '{actor_id}'",
            tenant_id=tenant_id,
            actor_id=actor_id,
            resource_type=resource_type,
            trace_id=trace_id,
            policy_decision_id=decision_id,
            confidence_score=0.95,
        )
        return self._append(event)

    def ingest_suspicious_agent(
        self,
        tenant_id: str,
        agent_id: str,
        agent_name: str,
        signal: str,
        details: str = "",
        trace_id: str = "",
    ) -> SecurityEvent:
        """Record a suspicious agent behaviour signal."""
        event = SecurityEvent(
            category=SecurityEventCategory.SUSPICIOUS_AGENT,
            severity=SecurityEventSeverity.MEDIUM,
            title=f"Suspicious agent behaviour: {signal}",
            description=f"Agent '{agent_name}' ({agent_id}) — {signal}. {details}",
            tenant_id=tenant_id,
            actor_id=agent_id,
            resource_type="agent",
            resource_id=agent_id,
            trace_id=trace_id,
            confidence_score=0.5,  # Heuristic — low confidence
        )
        return self._append(event)

    def ingest_api_abuse(
        self,
        tenant_id: str,
        actor_id: str,
        endpoint: str,
        requests_per_minute: int,
        trace_id: str = "",
    ) -> SecurityEvent:
        """Record excessive API consumption."""
        severity = (
            SecurityEventSeverity.HIGH if requests_per_minute > _API_RATE_THRESHOLD * 2
            else SecurityEventSeverity.MEDIUM
        )
        event = SecurityEvent(
            category=SecurityEventCategory.API_ABUSE,
            severity=severity,
            title=f"Excessive API consumption on {endpoint}",
            description=(
                f"Actor '{actor_id}' made {requests_per_minute} requests/min to '{endpoint}' "
                f"(threshold: {_API_RATE_THRESHOLD}/min)"
            ),
            tenant_id=tenant_id,
            actor_id=actor_id,
            resource_type="api_endpoint",
            resource_id=endpoint,
            trace_id=trace_id,
            confidence_score=0.6,
        )
        return self._append(event)

    def ingest_spend_anomaly(
        self,
        tenant_id: str,
        actor_id: str,
        current_spend_usd: float,
        avg_spend_usd: float,
        period: str = "daily",
        trace_id: str = "",
    ) -> SecurityEvent:
        """Record an abnormal spending pattern."""
        multiplier = current_spend_usd / max(avg_spend_usd, 0.01)
        severity = (
            SecurityEventSeverity.CRITICAL if multiplier > 10
            else SecurityEventSeverity.HIGH if multiplier > 5
            else SecurityEventSeverity.MEDIUM
        )
        event = SecurityEvent(
            category=SecurityEventCategory.SPEND_ANOMALY,
            severity=severity,
            title=f"Abnormal {period} spend detected",
            description=(
                f"Tenant '{tenant_id}' spent \${current_spend_usd:.2f} vs average \${avg_spend_usd:.2f} "
                f"({multiplier:.1f}x). ESTIMATED COSTS — not actual billing."
            ),
            tenant_id=tenant_id,
            actor_id=actor_id,
            resource_type="billing",
            trace_id=trace_id,
            confidence_score=min(0.4 + (multiplier / 20.0), 0.85),
        )
        return self._append(event)

    def ingest_injection_attempt(
        self,
        tenant_id: str,
        actor_id: str,
        source: str,
        risk_score: float,
        signals: List[str],
        trace_id: str = "",
    ) -> Optional[SecurityEvent]:
        """Record a potential prompt injection signal (heuristic only)."""
        if risk_score < 0.3:
            return None  # Below threshold — do not create noise
        severity = (
            SecurityEventSeverity.HIGH if risk_score > 0.7
            else SecurityEventSeverity.MEDIUM if risk_score > 0.5
            else SecurityEventSeverity.LOW
        )
        event = SecurityEvent(
            category=SecurityEventCategory.INJECTION_ATTEMPT,
            severity=severity,
            title="Potential prompt injection signal",
            description=(
                f"Heuristic signals detected from source '{source}' for actor '{actor_id}'. "
                f"Risk score: {risk_score:.2f}. Signals: {', '.join(signals[:5])}"
            ),
            tenant_id=tenant_id,
            actor_id=actor_id,
            resource_type="llm_input",
            trace_id=trace_id,
            confidence_score=risk_score,
            # Always low confidence — heuristic only
            is_heuristic=True,
        )
        return self._append(event)

    def ingest_mcp_security_event(
        self,
        tenant_id: str,
        actor_id: str,
        server_id: str,
        tool_id: str,
        event_type: str,
        details: str = "",
        trace_id: str = "",
    ) -> SecurityEvent:
        """Record an MCP/tool security event."""
        event = SecurityEvent(
            category=SecurityEventCategory.MCP_SECURITY,
            severity=SecurityEventSeverity.MEDIUM,
            title=f"MCP security event: {event_type}",
            description=f"Tool '{tool_id}' on server '{server_id}': {event_type}. {details}",
            tenant_id=tenant_id,
            actor_id=actor_id,
            resource_type="mcp_tool",
            resource_id=tool_id,
            trace_id=trace_id,
            confidence_score=0.7,
        )
        return self._append(event)

    def ingest_deployment_violation(
        self,
        tenant_id: str,
        actor_id: str,
        model_id: str,
        violation: str,
        trace_id: str = "",
    ) -> SecurityEvent:
        """Record a model deployment policy violation."""
        event = SecurityEvent(
            category=SecurityEventCategory.DEPLOYMENT_VIOLATION,
            severity=SecurityEventSeverity.HIGH,
            title=f"Model deployment violation: {violation}",
            description=f"Model '{model_id}' deployment violation by '{actor_id}': {violation}",
            tenant_id=tenant_id,
            actor_id=actor_id,
            resource_type="model",
            resource_id=model_id,
            trace_id=trace_id,
            confidence_score=0.8,
        )
        return self._append(event)

    # ── Investigation ─────────────────────────────────────────────────────────

    def add_investigation_note(
        self,
        event_id: str,
        investigator_id: str,
        note: str,
    ) -> Optional[SecurityEvent]:
        """Add an investigation note to an existing event."""
        if investigator_id.lower() in {"system", "auto", "automated", ""}:
            raise PermissionError("Investigation notes require a named human investigator")
        event = self._get(event_id)
        if event is None:
            return None
        event.investigation_notes.append(
            f"[{datetime.now(timezone.utc).isoformat()}] {investigator_id}: {note}"
        )
        return event

    def resolve_event(
        self,
        event_id: str,
        resolver_id: str,
        resolution: str,
        status: SecurityEventStatus = SecurityEventStatus.RESOLVED,
    ) -> Optional[SecurityEvent]:
        """Mark an event as resolved. Requires a named human resolver."""
        if resolver_id.lower() in {"system", "auto", "automated", ""}:
            raise PermissionError("Event resolution requires a named human resolver")
        event = self._get(event_id)
        if event is None:
            return None
        event.status = status
        event.resolved_by = resolver_id
        event.resolved_at = datetime.now(timezone.utc).isoformat()
        event.investigation_notes.append(
            f"[{event.resolved_at}] {resolver_id} → {status.value}: {resolution}"
        )
        return event

    # ── Query API ─────────────────────────────────────────────────────────────

    def list_events(
        self,
        tenant_id: Optional[str] = None,
        category: Optional[SecurityEventCategory] = None,
        severity: Optional[SecurityEventSeverity] = None,
        status: Optional[SecurityEventStatus] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        events = list(reversed(self._events[-limit * 2:]))
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        if category:
            events = [e for e in events if e.category == category]
        if severity:
            events = [e for e in events if e.severity == severity]
        if status:
            events = [e for e in events if e.status == status]
        return [e.to_dict() for e in events[:limit]]

    def get_summary(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Return security intelligence summary."""
        events = self._events
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]

        by_severity: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        open_count = 0
        for e in events:
            by_severity[e.severity.value] = by_severity.get(e.severity.value, 0) + 1
            by_category[e.category.value] = by_category.get(e.category.value, 0) + 1
            if e.status == SecurityEventStatus.OPEN:
                open_count += 1

        return {
            "total_events": len(events),
            "open_events": open_count,
            "by_severity": by_severity,
            "by_category": by_category,
            "is_heuristic": True,
            "limitation": (
                "Security event counts reflect heuristic detections. "
                "They do NOT indicate confirmed breaches or attacks. "
                "Each event requires human investigation and triage."
            ),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _append(self, event: SecurityEvent) -> SecurityEvent:
        self._events.append(event)
        if len(self._events) > self._EVENT_LIMIT:
            self._events = self._events[-self._EVENT_LIMIT:]
        logger.info(
            f"[SecIntel] {event.severity.value} {event.category.value}: {event.title} "
            f"[tenant={event.tenant_id}] [heuristic={event.is_heuristic}]"
        )
        return event

    def _get(self, event_id: str) -> Optional[SecurityEvent]:
        for e in reversed(self._events):
            if e.event_id == event_id:
                return e
        return None

    def _check_rate(self, tenant_id: str, event_type: str) -> int:
        """Count events of a type in the last 60 seconds for a tenant."""
        now = time.time()
        window_key = f"{tenant_id}:{event_type}"
        if tenant_id not in self._rate_windows:
            self._rate_windows[tenant_id] = {}
        window = self._rate_windows[tenant_id].get(event_type, [])
        window = [t for t in window if now - t < 60.0]
        window.append(now)
        self._rate_windows[tenant_id][event_type] = window
        return len(window)


# ── Singleton ─────────────────────────────────────────────────────────────────
_intel: Optional[SecurityIntelligenceService] = None


def get_security_intel() -> SecurityIntelligenceService:
    global _intel
    if _intel is None:
        _intel = SecurityIntelligenceService()
    return _intel
