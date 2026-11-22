# Copyright 2026 OrQuanta — Apache License 2.0
"""
Phase 5D — Agent Intelligence Analytics
Phase 5E — GPU and Model Performance Monitoring
Phase 5F — Cost Intelligence Engine
Phase 5G — Governance Reporting

Combined module for infrastructure observability.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orquanta.observability.intelligence")


# ═════════════════════════════════════════════════════════════════════════════
# Phase 5D — Agent Intelligence
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class AgentTimelineEvent:
    """A single event in an agent's execution timeline."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    agent_name: str = ""
    event_type: str = ""   # llm_call | tool_call | permission_check | error | spawn_child | complete
    description: str = ""
    duration_ms: float = 0.0
    tokens_used: int = 0
    cost_usd: float = 0.0
    success: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "event_type": self.event_type,
            "description": self.description[:200],
            "duration_ms": round(self.duration_ms, 2),
            "tokens_used": self.tokens_used,
            "cost_usd": round(self.cost_usd, 6),
            "success": self.success,
            "timestamp": self.timestamp,
        }


class AgentIntelligenceService:
    """
    Tracks agent execution timelines, permission decisions, tool usage,
    cost attribution and retry behaviour.
    """

    _TIMELINE_LIMIT = 100_000

    def __init__(self) -> None:
        self._timelines: List[AgentTimelineEvent] = []
        # workflow_id → list of AgentTimelineEvent
        self._workflows: Dict[str, List[str]] = {}  # workflow_id → event_ids

    def record_event(
        self,
        agent_id: str,
        agent_name: str,
        event_type: str,
        description: str,
        duration_ms: float = 0.0,
        tokens_used: int = 0,
        cost_usd: float = 0.0,
        success: bool = True,
        workflow_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentTimelineEvent:
        event = AgentTimelineEvent(
            agent_id=agent_id,
            agent_name=agent_name,
            event_type=event_type,
            description=description,
            duration_ms=duration_ms,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            success=success,
            metadata=metadata or {},
        )
        self._timelines.append(event)
        if len(self._timelines) > self._TIMELINE_LIMIT:
            self._timelines = self._timelines[-self._TIMELINE_LIMIT:]
        if workflow_id:
            self._workflows.setdefault(workflow_id, []).append(event.event_id)
        return event

    def get_agent_timeline(
        self,
        agent_id: str,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        events = [e for e in reversed(self._timelines) if e.agent_id == agent_id]
        return [e.to_dict() for e in events[:limit]]

    def get_workflow_trace(self, workflow_id: str) -> Dict[str, Any]:
        """Return explainable trace for a workflow."""
        event_ids = set(self._workflows.get(workflow_id, []))
        events = [e for e in self._timelines if e.event_id in event_ids]
        events.sort(key=lambda e: e.timestamp)

        total_cost = sum(e.cost_usd for e in events)
        total_tokens = sum(e.tokens_used for e in events)
        total_duration = sum(e.duration_ms for e in events)
        failures = [e for e in events if not e.success]

        return {
            "workflow_id": workflow_id,
            "event_count": len(events),
            "total_duration_ms": round(total_duration, 2),
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(total_cost, 6),
            "failure_count": len(failures),
            "timeline": [e.to_dict() for e in events],
            "disclaimer": (
                "Agent execution trace is best-effort. "
                "Cost figures are estimates, not actual billing."
            ),
        }

    def get_analytics_summary(self, tenant_id: str = "") -> Dict[str, Any]:
        """Return aggregate agent intelligence analytics."""
        events = list(self._timelines)

        by_agent: Dict[str, Dict] = {}
        for e in events:
            if e.agent_name not in by_agent:
                by_agent[e.agent_name] = {
                    "events": 0, "failures": 0, "tokens": 0,
                    "cost_usd": 0.0, "tool_calls": 0, "llm_calls": 0,
                }
            by_agent[e.agent_name]["events"] += 1
            if not e.success:
                by_agent[e.agent_name]["failures"] += 1
            by_agent[e.agent_name]["tokens"] += e.tokens_used
            by_agent[e.agent_name]["cost_usd"] = round(
                by_agent[e.agent_name]["cost_usd"] + e.cost_usd, 6
            )
            if e.event_type == "tool_call":
                by_agent[e.agent_name]["tool_calls"] += 1
            elif e.event_type == "llm_call":
                by_agent[e.agent_name]["llm_calls"] += 1

        return {
            "total_events": len(events),
            "by_agent": by_agent,
            "disclaimer": "Cost figures are estimates only.",
        }


# ═════════════════════════════════════════════════════════════════════════════
# Phase 5E — GPU and Model Performance
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class GPUPerformanceSnapshot:
    """A point-in-time GPU performance measurement."""
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    provider: str = ""
    instance_id: str = ""
    model_id: str = ""
    # GPU metrics
    gpu_utilization_pct: Optional[float] = None
    vram_used_gb: Optional[float] = None
    vram_total_gb: Optional[float] = None
    vram_utilization_pct: Optional[float] = None
    gpu_temp_celsius: Optional[float] = None
    power_draw_w: Optional[float] = None
    # Inference metrics
    model_load_time_s: Optional[float] = None
    inference_latency_ms: Optional[float] = None
    throughput_tokens_per_s: Optional[float] = None
    queue_depth: int = 0
    # Data quality labels — ALWAYS set
    is_real_measurement: bool = False
    is_estimated: bool = True
    is_demo_data: bool = False
    data_source: str = "unknown"
    limitation: str = (
        "Metrics labelled is_estimated=True are computed from job parameters, "
        "not direct GPU sensor readings. For real measurements, connect a running "
        "vLLM/SGLang instance with VLLM_INSTANCE_URL configured."
    )
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "provider": self.provider,
            "instance_id": self.instance_id,
            "model_id": self.model_id,
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "vram_used_gb": self.vram_used_gb,
            "vram_total_gb": self.vram_total_gb,
            "vram_utilization_pct": self.vram_utilization_pct,
            "gpu_temp_celsius": self.gpu_temp_celsius,
            "power_draw_w": self.power_draw_w,
            "model_load_time_s": self.model_load_time_s,
            "inference_latency_ms": self.inference_latency_ms,
            "throughput_tokens_per_s": self.throughput_tokens_per_s,
            "queue_depth": self.queue_depth,
            "is_real_measurement": self.is_real_measurement,
            "is_estimated": self.is_estimated,
            "is_demo_data": self.is_demo_data,
            "data_source": self.data_source,
            "limitation": self.limitation,
            "timestamp": self.timestamp,
        }


class GPUPerformanceService:
    """
    Collects GPU and model performance metrics.
    Always distinguishes real measurements from estimates or demo data.
    """

    _SNAPSHOT_LIMIT = 20_000

    def __init__(self) -> None:
        self._snapshots: List[GPUPerformanceSnapshot] = []

    def record_snapshot(
        self,
        provider: str,
        instance_id: str,
        model_id: str,
        gpu_util_pct: Optional[float] = None,
        vram_used_gb: Optional[float] = None,
        vram_total_gb: Optional[float] = None,
        gpu_temp_celsius: Optional[float] = None,
        power_draw_w: Optional[float] = None,
        inference_latency_ms: Optional[float] = None,
        throughput_tokens_per_s: Optional[float] = None,
        queue_depth: int = 0,
        model_load_time_s: Optional[float] = None,
        is_real_measurement: bool = False,
        data_source: str = "api_estimate",
    ) -> GPUPerformanceSnapshot:
        """Record a GPU performance snapshot. Must explicitly label data quality."""
        vram_util = None
        if vram_used_gb is not None and vram_total_gb and vram_total_gb > 0:
            vram_util = round(vram_used_gb / vram_total_gb * 100, 1)

        snapshot = GPUPerformanceSnapshot(
            provider=provider,
            instance_id=instance_id,
            model_id=model_id,
            gpu_utilization_pct=gpu_util_pct,
            vram_used_gb=vram_used_gb,
            vram_total_gb=vram_total_gb,
            vram_utilization_pct=vram_util,
            gpu_temp_celsius=gpu_temp_celsius,
            power_draw_w=power_draw_w,
            inference_latency_ms=inference_latency_ms,
            throughput_tokens_per_s=throughput_tokens_per_s,
            queue_depth=queue_depth,
            model_load_time_s=model_load_time_s,
            is_real_measurement=is_real_measurement,
            is_estimated=not is_real_measurement,
            data_source=data_source,
        )
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._SNAPSHOT_LIMIT:
            self._snapshots = self._snapshots[-self._SNAPSHOT_LIMIT:]
        return snapshot

    def get_latest(
        self,
        provider: Optional[str] = None,
        model_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        snaps = list(reversed(self._snapshots[-limit * 2:]))
        if provider:
            snaps = [s for s in snaps if s.provider == provider]
        if model_id:
            snaps = [s for s in snaps if s.model_id == model_id]
        return [s.to_dict() for s in snaps[:limit]]

    def get_performance_summary(
        self,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        snaps = self._snapshots
        if model_id:
            snaps = [s for s in snaps if s.model_id == model_id]
        real = [s for s in snaps if s.is_real_measurement]
        estimated = [s for s in snaps if s.is_estimated]

        def avg(lst, key):
            vals = [getattr(s, key) for s in lst if getattr(s, key) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        return {
            "total_snapshots": len(snaps),
            "real_measurements": len(real),
            "estimated_measurements": len(estimated),
            "avg_gpu_utilization_pct": avg(snaps, "gpu_utilization_pct"),
            "avg_vram_utilization_pct": avg(snaps, "vram_utilization_pct"),
            "avg_inference_latency_ms": avg(snaps, "inference_latency_ms"),
            "avg_throughput_tokens_per_s": avg(snaps, "throughput_tokens_per_s"),
            "avg_power_draw_w": avg(snaps, "power_draw_w"),
            "disclaimer": (
                "Averages include both real sensor readings and API estimates. "
                "Filter by is_real_measurement=true for validated metrics."
            ),
        }


# ═════════════════════════════════════════════════════════════════════════════
# Phase 5F — Cost Intelligence Engine
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class CostIntelligenceRecord:
    """A unified cost event across all cost types."""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    cost_type: str = ""   # gpu_execution | inference_token | storage | provider_charge | other
    model_id: str = ""
    provider: str = ""
    job_id: str = ""
    agent_id: str = ""
    cost_usd: float = 0.0
    # Always label as estimate unless actual billing data
    is_actual_billing: bool = False
    is_estimated: bool = True
    billing_period: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CostIntelligenceEngine:
    """
    Unified cost tracking across GPU execution, hosted inference, tokens, storage.
    Implements budget forecasting, anomaly detection and optimization recommendations.

    DISCLAIMER: Estimated costs are NOT actual provider billing.
    Actual billing is determined by the provider and may differ significantly.
    """

    _RECORD_LIMIT = 100_000
    _DISCLAIMER = (
        "All cost figures are internal estimates for resource planning purposes. "
        "They do NOT represent actual provider billing. "
        "Refer to your provider invoices for authoritative billing data."
    )

    def __init__(self) -> None:
        self._records: List[CostIntelligenceRecord] = []
        # Tenant daily spend history: tenant_id → {date_str: cost}
        self._daily_history: Dict[str, Dict[str, float]] = {}
        # Budget alerts: tenant_id → alert_threshold_usd
        self._budget_limits: Dict[str, float] = {}
        self._spend_alerts: List[Dict[str, Any]] = []

    def record_cost(
        self,
        tenant_id: str,
        cost_type: str,
        cost_usd: float,
        provider: str = "",
        model_id: str = "",
        job_id: str = "",
        agent_id: str = "",
        is_actual_billing: bool = False,
        billing_period: str = "",
    ) -> CostIntelligenceRecord:
        """Record a cost event."""
        record = CostIntelligenceRecord(
            tenant_id=tenant_id,
            cost_type=cost_type,
            cost_usd=round(cost_usd, 6),
            provider=provider,
            model_id=model_id,
            job_id=job_id,
            agent_id=agent_id,
            is_actual_billing=is_actual_billing,
            is_estimated=not is_actual_billing,
            billing_period=billing_period or date.today().isoformat(),
        )
        self._records.append(record)
        if len(self._records) > self._RECORD_LIMIT:
            self._records = self._records[-self._RECORD_LIMIT:]

        # Update daily history
        today = date.today().isoformat()
        self._daily_history.setdefault(tenant_id, {})
        self._daily_history[tenant_id][today] = (
            self._daily_history[tenant_id].get(today, 0.0) + cost_usd
        )

        # Budget anomaly check
        self._check_budget_anomaly(tenant_id, cost_usd)
        return record

    def set_budget_limit(self, tenant_id: str, daily_limit_usd: float) -> None:
        """Set a daily spending alert threshold for a tenant."""
        self._budget_limits[tenant_id] = daily_limit_usd

    def _check_budget_anomaly(self, tenant_id: str, new_cost: float) -> None:
        """Check if daily spend exceeds budget or anomaly threshold."""
        today = date.today().isoformat()
        today_total = self._daily_history.get(tenant_id, {}).get(today, 0.0)
        limit = self._budget_limits.get(tenant_id, 0.0)

        if limit > 0 and today_total > limit:
            alert = {
                "tenant_id": tenant_id,
                "alert_type": "BUDGET_EXCEEDED",
                "today_spend_usd": round(today_total, 2),
                "budget_usd": limit,
                "pct_used": round(today_total / limit * 100, 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "is_estimated": True,
                "disclaimer": self._DISCLAIMER,
            }
            self._spend_alerts.append(alert)
            logger.warning(f"[CostIntel] Budget alert: {tenant_id} spent ${today_total:.2f} vs ${limit:.2f} limit")

        # Anomaly: >3x the 7-day average
        history = self._daily_history.get(tenant_id, {})
        past_7 = []
        for i in range(1, 8):
            d = (date.today() - timedelta(days=i)).isoformat()
            if d in history:
                past_7.append(history[d])
        if past_7:
            avg = sum(past_7) / len(past_7)
            if avg > 0 and today_total > avg * 3:
                alert = {
                    "tenant_id": tenant_id,
                    "alert_type": "SPEND_ANOMALY",
                    "today_spend_usd": round(today_total, 2),
                    "7day_avg_usd": round(avg, 2),
                    "multiplier": round(today_total / avg, 1),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "is_estimated": True,
                    "disclaimer": self._DISCLAIMER,
                }
                self._spend_alerts.append(alert)

    def get_cost_by_tenant(
        self,
        tenant_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Return cost breakdown for a tenant over the last N days."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        records = [
            r for r in self._records
            if r.tenant_id == tenant_id and r.billing_period >= cutoff
        ]

        by_type: Dict[str, float] = {}
        by_model: Dict[str, float] = {}
        by_provider: Dict[str, float] = {}
        by_job: Dict[str, float] = {}
        total = 0.0

        for r in records:
            total += r.cost_usd
            by_type[r.cost_type] = round(by_type.get(r.cost_type, 0.0) + r.cost_usd, 6)
            if r.model_id:
                by_model[r.model_id] = round(by_model.get(r.model_id, 0.0) + r.cost_usd, 6)
            if r.provider:
                by_provider[r.provider] = round(by_provider.get(r.provider, 0.0) + r.cost_usd, 6)
            if r.job_id:
                by_job[r.job_id] = round(by_job.get(r.job_id, 0.0) + r.cost_usd, 6)

        # Top 5 jobs by cost
        top_jobs = sorted(by_job.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_estimated_usd": round(total, 4),
            "by_cost_type": by_type,
            "by_model": by_model,
            "by_provider": by_provider,
            "top_jobs_by_cost": [{"job_id": j, "cost_usd": c} for j, c in top_jobs],
            "record_count": len(records),
            "is_estimated": True,
            "disclaimer": self._DISCLAIMER,
        }

    def get_budget_forecast(
        self,
        tenant_id: str,
        forecast_days: int = 7,
    ) -> Dict[str, Any]:
        """Simple linear budget forecast based on recent spend trend."""
        history = self._daily_history.get(tenant_id, {})
        past_7 = []
        for i in range(1, 8):
            d = (date.today() - timedelta(days=i)).isoformat()
            past_7.append(history.get(d, 0.0))

        if not any(past_7):
            return {
                "tenant_id": tenant_id,
                "forecast_available": False,
                "reason": "Insufficient spending history",
                "disclaimer": self._DISCLAIMER,
            }

        daily_avg = sum(past_7) / len(past_7)
        # Simple linear forecast
        forecast = {
            (date.today() + timedelta(days=i)).isoformat(): round(daily_avg, 4)
            for i in range(1, forecast_days + 1)
        }
        limit = self._budget_limits.get(tenant_id, 0.0)

        return {
            "tenant_id": tenant_id,
            "forecast_available": True,
            "avg_daily_spend_usd": round(daily_avg, 4),
            "forecast_period_days": forecast_days,
            "forecast_by_day": forecast,
            "projected_total_usd": round(daily_avg * forecast_days, 4),
            "budget_daily_usd": limit,
            "forecast_method": "7-day simple moving average",
            "is_estimated": True,
            "disclaimer": (
                self._DISCLAIMER + " Forecasts are projections based on historical patterns "
                "and may not reflect future usage."
            ),
        }

    def get_optimization_recommendations(
        self,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Return workload optimization recommendations.
        All recommendations are heuristic suggestions, not guaranteed savings.
        """
        recs = []
        history = self._daily_history.get(tenant_id, {})
        past_7 = [v for v in history.values()]
        avg = sum(past_7) / max(len(past_7), 1) if past_7 else 0

        # Check high-cost models
        records = [r for r in self._records if r.tenant_id == tenant_id and r.cost_type == "inference_token"]
        by_model: Dict[str, float] = {}
        for r in records:
            by_model[r.model_id] = by_model.get(r.model_id, 0.0) + r.cost_usd
        if by_model:
            top = max(by_model, key=by_model.get)
            recs.append({
                "recommendation": f"High spend on model '{top}' (${by_model[top]:.2f} estimated). "
                                   "Consider using a smaller model for lower-complexity tasks.",
                "category": "model_optimization",
                "is_heuristic": True,
                "disclaimer": "This is a heuristic suggestion based on estimated spend patterns.",
            })

        if avg > 0:
            recs.append({
                "recommendation": f"Average daily estimated spend: ${avg:.2f}. "
                                   "Review job scheduling to shift batch workloads to off-peak hours.",
                "category": "scheduling",
                "is_heuristic": True,
                "disclaimer": "Scheduling recommendations are based on estimated costs only.",
            })

        recs.append({
            "recommendation": "Review idle GPU instances in provider dashboards. "
                               "Terminate any instances not running active jobs.",
            "category": "resource_cleanup",
            "is_heuristic": True,
            "disclaimer": "Actual idle instance detection requires provider API integration.",
        })

        return recs

    def get_alerts(self, tenant_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        alerts = list(reversed(self._spend_alerts[-limit * 2:]))
        if tenant_id:
            alerts = [a for a in alerts if a.get("tenant_id") == tenant_id]
        return alerts[:limit]


# ═════════════════════════════════════════════════════════════════════════════
# Phase 5G — Governance Reporting
# ═════════════════════════════════════════════════════════════════════════════

class GovernanceReportingService:
    """
    Extends the Phase 4 governance platform with reporting, audit exports
    and compliance evidence generation.

    DISCLAIMER: Automated reports do NOT constitute regulatory certification.
    """

    _DISCLAIMER = (
        "This report is generated from automated platform data. "
        "It does NOT constitute regulatory certification, compliance attestation, "
        "or independent audit evidence. Formal compliance requires accredited third-party assessment."
    )

    def __init__(self) -> None:
        self._report_history: List[Dict[str, Any]] = []

    def generate_model_usage_report(
        self,
        tenant_id: str,
        llm_summary: Dict[str, Any],
        gpu_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        report = {
            "report_type": "MODEL_USAGE",
            "report_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "llm_summary": llm_summary,
            "gpu_summary": gpu_summary,
            "disclaimer": self._DISCLAIMER,
        }
        self._report_history.append(report)
        return report

    def generate_security_report(
        self,
        tenant_id: str,
        security_summary: Dict[str, Any],
        policy_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        report = {
            "report_type": "SECURITY_INCIDENT",
            "report_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "security_summary": security_summary,
            "policy_summary": policy_summary or {},
            "limitation": (
                "Security event counts are heuristic. "
                "This report does NOT confirm that security incidents occurred."
            ),
            "disclaimer": self._DISCLAIMER,
        }
        self._report_history.append(report)
        return report

    def generate_policy_enforcement_report(
        self,
        tenant_id: str,
        policy_decisions: List[Dict[str, Any]],
        approval_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        total = len(policy_decisions)
        denials = sum(1 for d in policy_decisions if d.get("decision") == "DENY")
        approvals_required = sum(1 for d in policy_decisions if d.get("decision") == "REQUIRE_APPROVAL")

        report = {
            "report_type": "POLICY_ENFORCEMENT",
            "report_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_decisions": total,
            "decisions_allowed": total - denials - approvals_required,
            "decisions_denied": denials,
            "decisions_requiring_approval": approvals_required,
            "approval_history": approval_history[:100],
            "traceability": "All decisions reference policy_id from PolicyEngine Phase 4A",
            "disclaimer": self._DISCLAIMER,
        }
        self._report_history.append(report)
        return report

    def generate_risk_summary_report(
        self,
        tenant_id: str,
        risk_report: Dict[str, Any],
        evidence_count: int,
    ) -> Dict[str, Any]:
        report = {
            "report_type": "RISK_SUMMARY",
            "report_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "risk_data": risk_report,
            "evidence_items": evidence_count,
            "frameworks_referenced": [
                "NIST AI RMF", "OWASP LLM Top 10",
                "MITRE ATLAS", "ISO 42001", "EU AI Act"
            ],
            "disclaimer": self._DISCLAIMER,
        }
        self._report_history.append(report)
        return report

    def export_audit_evidence(
        self,
        tenant_id: str,
        audit_events: List[Dict[str, Any]],
        format: str = "json",
    ) -> Dict[str, Any]:
        """Export audit evidence in structured format."""
        return {
            "export_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "format": format,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "event_count": len(audit_events),
            "events": audit_events,
            "disclaimer": self._DISCLAIMER,
            "limitation": (
                "Audit exports represent platform-recorded events only. "
                "Chain of custody for formal legal purposes requires additional controls."
            ),
        }

    def list_reports(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        reports = list(reversed(self._report_history))
        if tenant_id:
            reports = [r for r in reports if r.get("tenant_id") == tenant_id]
        # Return metadata only, not full report content
        return [
            {
                "report_id": r["report_id"],
                "report_type": r["report_type"],
                "tenant_id": r["tenant_id"],
                "generated_at": r["generated_at"],
            }
            for r in reports[:100]
        ]


# ── Singletons ────────────────────────────────────────────────────────────────
_agent_intel: Optional[AgentIntelligenceService] = None
_gpu_perf: Optional[GPUPerformanceService] = None
_cost_engine: Optional[CostIntelligenceEngine] = None
_gov_reporting: Optional[GovernanceReportingService] = None


def get_agent_intel() -> AgentIntelligenceService:
    global _agent_intel
    if _agent_intel is None:
        _agent_intel = AgentIntelligenceService()
    return _agent_intel


def get_gpu_perf() -> GPUPerformanceService:
    global _gpu_perf
    if _gpu_perf is None:
        _gpu_perf = GPUPerformanceService()
    return _gpu_perf


def get_cost_engine() -> CostIntelligenceEngine:
    global _cost_engine
    if _cost_engine is None:
        _cost_engine = CostIntelligenceEngine()
    return _cost_engine


def get_gov_reporting() -> GovernanceReportingService:
    global _gov_reporting
    if _gov_reporting is None:
        _gov_reporting = GovernanceReportingService()
    return _gov_reporting
