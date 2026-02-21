"""
OrQuanta Agentic v1.0 — Prometheus Metrics Exporter

Exposes platform metrics for Grafana dashboards:

  orquanta_jobs_total              — Jobs submitted/completed/failed
  orquanta_gpu_hours_total         — Total GPU-hours consumed
  orquanta_spend_usd_total         — Total $ spent under management
  orquanta_savings_usd_total       — $ saved vs on-demand pricing
  orquanta_agents_heartbeat        — Per-agent liveness (0/1)
  orquanta_api_latency_seconds     — Histogram: API response time
  orquanta_provisioning_seconds    — Histogram: time to GPU ready
  orquanta_active_instances        — Gauge: live GPU instances
  orquanta_spot_price_usd          — Gauge: current spot price by GPU/provider
  orquanta_rate_limit_blocks_total — Rate limit hits per endpoint

Exposes /metrics endpoint in Prometheus text format.
Scraped every 15s by Prometheus → Grafana dashboard.

Usage:
    from v4.monitoring.metrics_exporter import get_metrics_collector
    metrics = get_metrics_collector()
    metrics.record_job_completed(job_id, provider, gpu_type, cost_usd, duration_s, saved_usd)
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

PROMETHEUS_AVAILABLE = False
try:
    from prometheus_client import (
        Counter, Gauge, Histogram, Summary, CollectorRegistry,
        generate_latest, CONTENT_TYPE_LATEST, push_to_gateway
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    pass

PUSHGATEWAY_URL = os.getenv("PROMETHEUS_PUSHGATEWAY_URL", "")
METRICS_PREFIX = "orquanta"

# Histogram buckets for latency (seconds)
API_LATENCY_BUCKETS = (.005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0)
PROVISION_BUCKETS = (5.0, 10.0, 20.0, 30.0, 60.0, 120.0, 300.0)


class BomaxMetricsCollector:
    """
    Prometheus metrics collector for the full OrQuanta platform.
    
    Falls back to in-memory counters if prometheus_client isn't installed.
    Supports push gateway for ephemeral containers (ECS Fargate).
    """

    def __init__(self) -> None:
        self._prom = PROMETHEUS_AVAILABLE
        self._in_memory: dict[str, float] = defaultdict(float)
        
        if self._prom:
            self._setup_prometheus_metrics()

    def _setup_prometheus_metrics(self) -> None:
        """Initialize all Prometheus metric objects."""
        p = METRICS_PREFIX

        # ─── Counters (always increase) ──────────────────────────
        self.jobs_submitted = Counter(f"{p}_jobs_submitted_total", "Total jobs submitted",
                                      ["org_id", "plan"])
        self.jobs_completed = Counter(f"{p}_jobs_completed_total", "Jobs completed successfully",
                                      ["provider", "gpu_type"])
        self.jobs_failed = Counter(f"{p}_jobs_failed_total", "Jobs that failed",
                                   ["provider", "gpu_type", "failure_reason"])
        
        self.gpu_hours = Counter(f"{p}_gpu_hours_total", "Total GPU-hours consumed",
                                 ["provider", "gpu_type"])
        self.spend_usd = Counter(f"{p}_spend_usd_total", "Total USD spent under management",
                                 ["provider", "gpu_type", "org_id"])
        self.savings_usd = Counter(f"{p}_savings_usd_total", "USD saved vs on-demand",
                                   ["provider", "gpu_type"])
        
        self.agent_decisions = Counter(f"{p}_agent_decisions_total", "Total agent decisions made",
                                       ["agent_name", "decision_type"])
        self.healing_events = Counter(f"{p}_healing_events_total", "Self-healing events triggered",
                                      ["trigger_type", "action_taken"])
        self.provider_switches = Counter(f"{p}_provider_switches_total", "Provider switches for cost optimization",
                                         ["from_provider", "to_provider"])
        self.rate_limit_blocks = Counter(f"{p}_rate_limit_blocks_total", "Requests blocked by rate limiter",
                                          ["endpoint", "reason"])
        self.websocket_connections = Counter(f"{p}_websocket_connections_total", "WebSocket connections opened",
                                              ["org_id"])

        # ─── Gauges (can go up or down) ──────────────────────────
        self.active_instances = Gauge(f"{p}_active_instances", "Currently running GPU instances",
                                      ["provider", "gpu_type"])
        self.active_jobs = Gauge(f"{p}_active_jobs", "Jobs currently executing",
                                  ["org_id"])
        self.agent_heartbeat = Gauge(f"{p}_agent_heartbeat", "Agent liveness (1=alive, 0=dead)",
                                      ["agent_name"])
        self.spot_price_usd = Gauge(f"{p}_spot_price_usd_per_hour", "Current spot price USD/hr",
                                     ["provider", "gpu_type", "region"])
        self.queue_depth = Gauge(f"{p}_job_queue_depth", "Jobs waiting in queue",
                                  ["priority"])
        self.api_error_rate = Gauge(f"{p}_api_error_rate_1m", "API error rate (1 minute window)")
        self.mrr_usd = Gauge(f"{p}_mrr_usd", "Monthly recurring revenue in USD")
        self.active_customers = Gauge(f"{p}_active_customers", "Active paying customers")

        # ─── Histograms (distribution of values) ─────────────────
        self.api_latency = Histogram(f"{p}_api_latency_seconds", "API endpoint response time",
                                      ["endpoint", "method", "status_code"],
                                      buckets=API_LATENCY_BUCKETS)
        self.provision_duration = Histogram(f"{p}_provisioning_seconds", "Time from job submit to GPU ready",
                                             ["provider", "gpu_type"],
                                             buckets=PROVISION_BUCKETS)
        self.job_duration = Histogram(f"{p}_job_duration_seconds", "Job execution duration",
                                       ["provider", "gpu_type"],
                                       buckets=(60, 300, 900, 1800, 3600, 7200, 21600))
        self.goal_to_instance = Histogram(f"{p}_goal_to_instance_seconds", "NL goal to running instance",
                                           buckets=(5, 10, 20, 30, 45, 60, 90, 120))

    def record_job_submitted(self, org_id: str = "", plan: str = "pro") -> None:
        if self._prom:
            self.jobs_submitted.labels(org_id=org_id, plan=plan).inc()
        self._in_memory["jobs_submitted"] += 1

    def record_job_completed(
        self, job_id: str, provider: str, gpu_type: str,
        cost_usd: float, duration_s: float, saved_usd: float,
        gpu_hours: float | None = None,
    ) -> None:
        if gpu_hours is None:
            gpu_hours = duration_s / 3600.0

        if self._prom:
            self.jobs_completed.labels(provider=provider, gpu_type=gpu_type).inc()
            self.gpu_hours.labels(provider=provider, gpu_type=gpu_type).inc(gpu_hours)
            self.spend_usd.labels(provider=provider, gpu_type=gpu_type, org_id="").inc(cost_usd)
            self.savings_usd.labels(provider=provider, gpu_type=gpu_type).inc(saved_usd)
            self.job_duration.labels(provider=provider, gpu_type=gpu_type).observe(duration_s)

        self._in_memory["jobs_completed"] += 1
        self._in_memory["gpu_hours_total"] += gpu_hours
        self._in_memory["spend_usd_total"] += cost_usd
        self._in_memory["savings_usd_total"] += saved_usd

    def record_job_failed(self, provider: str, gpu_type: str, reason: str) -> None:
        if self._prom:
            self.jobs_failed.labels(provider=provider, gpu_type=gpu_type, failure_reason=reason).inc()
        self._in_memory["jobs_failed"] += 1

    def record_provisioning(self, provider: str, gpu_type: str, duration_s: float) -> None:
        if self._prom:
            self.provision_duration.labels(provider=provider, gpu_type=gpu_type).observe(duration_s)
        self._in_memory[f"provision_{provider}_{gpu_type}_last_s"] = duration_s

    def record_api_request(self, endpoint: str, method: str, status_code: int, duration_s: float) -> None:
        if self._prom:
            self.api_latency.labels(endpoint=endpoint, method=method,
                                     status_code=str(status_code)).observe(duration_s)

    def record_healing_event(self, trigger: str, action: str) -> None:
        if self._prom:
            self.healing_events.labels(trigger_type=trigger, action_taken=action).inc()
        self._in_memory["healing_events"] += 1

    def record_provider_switch(self, from_provider: str, to_provider: str) -> None:
        if self._prom:
            self.provider_switches.labels(from_provider=from_provider, to_provider=to_provider).inc()
        self._in_memory["provider_switches"] += 1

    def record_agent_decision(self, agent_name: str, decision_type: str) -> None:
        if self._prom:
            self.agent_decisions.labels(agent_name=agent_name, decision_type=decision_type).inc()

    def set_agent_heartbeat(self, agent_name: str, alive: bool) -> None:
        if self._prom:
            self.agent_heartbeat.labels(agent_name=agent_name).set(1.0 if alive else 0.0)

    def set_spot_price(self, provider: str, gpu_type: str, region: str, price_usd_hr: float) -> None:
        if self._prom:
            self.spot_price_usd.labels(provider=provider, gpu_type=gpu_type, region=region).set(price_usd_hr)

    def set_active_instances(self, provider: str, gpu_type: str, count: int) -> None:
        if self._prom:
            self.active_instances.labels(provider=provider, gpu_type=gpu_type).set(count)
        self._in_memory["active_instances"] = count

    def set_queue_depth(self, priority: str, depth: int) -> None:
        if self._prom:
            self.queue_depth.labels(priority=priority).set(depth)

    def set_mrr(self, mrr_usd: float, active_customers: int) -> None:
        if self._prom:
            self.mrr_usd.set(mrr_usd)
            self.active_customers.set(active_customers)

    def get_stats_dict(self) -> dict[str, Any]:
        """Return in-memory stats as a dict (for /metrics/platform endpoint)."""
        return {
            "jobs_submitted": self._in_memory.get("jobs_submitted", 0),
            "jobs_completed": self._in_memory.get("jobs_completed", 0),
            "jobs_failed": self._in_memory.get("jobs_failed", 0),
            "gpu_hours_total": round(self._in_memory.get("gpu_hours_total", 0), 2),
            "spend_usd_total": round(self._in_memory.get("spend_usd_total", 0), 2),
            "savings_usd_total": round(self._in_memory.get("savings_usd_total", 0), 2),
            "healing_events": self._in_memory.get("healing_events", 0),
            "provider_switches": self._in_memory.get("provider_switches", 0),
            "active_instances": self._in_memory.get("active_instances", 0),
            "prometheus_enabled": self._prom,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    def push_to_gateway(self, job_name: str = "orquanta_api") -> None:
        """Push metrics to Prometheus Pushgateway (for ephemeral ECS tasks)."""
        if not self._prom or not PUSHGATEWAY_URL:
            return
        try:
            push_to_gateway(PUSHGATEWAY_URL, job=job_name, registry=None)
        except Exception as exc:
            pass  # Non-critical — metrics push failure never crashes the app

    def prometheus_output(self) -> tuple[bytes, str]:
        """Generate Prometheus text format output for /metrics endpoint."""
        if self._prom:
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
            return generate_latest(), CONTENT_TYPE_LATEST
        # Fallback: emit simple text format
        lines = [
            f"# OrQuanta in-memory metrics (prometheus_client not installed)",
            f"orquanta_jobs_completed_total {self._in_memory.get('jobs_completed', 0)}",
            f"orquanta_gpu_hours_total {self._in_memory.get('gpu_hours_total', 0)}",
            f"orquanta_spend_usd_total {self._in_memory.get('spend_usd_total', 0)}",
            f"orquanta_savings_usd_total {self._in_memory.get('savings_usd_total', 0)}",
        ]
        return ("\n".join(lines) + "\n").encode(), "text/plain"


# ─── Singleton ────────────────────────────────────────────────────────────────

_collector: BomaxMetricsCollector | None = None

def get_metrics_collector() -> BomaxMetricsCollector:
    global _collector
    if _collector is None:
        _collector = BomaxMetricsCollector()
    return _collector
