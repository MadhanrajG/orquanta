# Copyright 2026 OrQuanta — Apache License 2.0
"""
Phase 5 — AI Observability and Intelligence Centre: test suite.
All tests synchronous. Run: python -m pytest phase5_tests.py -v --tb=short -p no:asyncio
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5A — OpenTelemetry Telemetry
# ─────────────────────────────────────────────────────────────────────────────
from observability.telemetry import (
    get_telemetry_status,
    redact_sensitive,
    traced_operation,
    get_tracer,
    get_meter,
    get_current_trace_id,
    inject_trace_headers,
    celery_task_start_span,
    celery_task_end_span,
    TraceCorrelationFilter,
    install_trace_log_filter,
    _NoOpTracer,
    _NoOpMeter,
)


class TestTelemetry(unittest.TestCase):

    def test_telemetry_status_returns_dict(self):
        status = get_telemetry_status()
        self.assertIsInstance(status, dict)
        self.assertIn("otel_available", status)
        self.assertIn("limitation", status)

    def test_redact_api_key(self):
        result = redact_sensitive("my key is sk-abc123def456ghi789jkl012")
        self.assertNotIn("sk-abc123def456ghi789jkl012", result)
        self.assertIn("[API_KEY_REDACTED]", result)

    def test_redact_bearer_token(self):
        result = redact_sensitive("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9.payload.sig", result)

    def test_redact_email(self):
        result = redact_sensitive("Contact alice@orquanta.com for access")
        self.assertNotIn("alice@orquanta.com", result)

    def test_redact_password(self):
        result = redact_sensitive("password=mysecret123")
        self.assertNotIn("mysecret123", result)

    def test_redact_safe_text_unchanged(self):
        text = "Normal status message: inference complete"
        result = redact_sensitive(text)
        self.assertEqual(result, text)

    def test_traced_operation_executes(self):
        # Must not raise even without OTLP configured
        result = []
        with traced_operation("test.operation", tenant_id="t1") as span:
            result.append("executed")
        self.assertEqual(result, ["executed"])

    def test_traced_operation_reraises_on_error(self):
        with self.assertRaises(ValueError):
            with traced_operation("test.error"):
                raise ValueError("test error")

    def test_get_tracer_returns_object(self):
        tracer = get_tracer()
        self.assertIsNotNone(tracer)

    def test_get_meter_returns_object(self):
        meter = get_meter()
        self.assertIsNotNone(meter)

    def test_get_current_trace_id_string(self):
        tid = get_current_trace_id()
        self.assertIsInstance(tid, str)

    def test_inject_trace_headers_safe(self):
        headers = {"Content-Type": "application/json"}
        result = inject_trace_headers(headers)
        # Must return a dict (possibly enriched with trace context)
        self.assertIsInstance(result, dict)

    def test_celery_task_span_lifecycle(self):
        span = celery_task_start_span("tasks.execute_gpu_job", "task-123", tenant_id="t1")
        self.assertIsNotNone(span)
        # Must not raise
        celery_task_end_span(span, success=True)
        celery_task_end_span(span, success=False, error="timeout")

    def test_trace_correlation_filter(self):
        import logging
        flt = TraceCorrelationFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", [], None)
        result = flt.filter(record)
        self.assertTrue(result)
        self.assertTrue(hasattr(record, "trace_id"))
        self.assertTrue(hasattr(record, "span_id"))

    def test_no_op_tracer_safe(self):
        tracer = _NoOpTracer()
        with tracer.start_as_current_span("test") as span:
            span.set_attribute("key", "value")

    def test_no_op_meter_safe(self):
        meter = _NoOpMeter()
        counter = meter.create_counter("test_counter")
        counter.add(1)

    def test_limitation_disclaimer_in_status(self):
        status = get_telemetry_status()
        self.assertIn("limitation", status)
        self.assertGreater(len(status["limitation"]), 10)

    def test_telemetry_failure_no_crash(self):
        """Telemetry setup failure must not crash the application."""
        from observability.telemetry import setup_telemetry
        # Second call is idempotent — must not raise
        setup_telemetry(app=None)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5B — LLM Observability
# ─────────────────────────────────────────────────────────────────────────────
from observability.llm_observability import (
    LLMObservabilityService,
    estimate_token_cost,
    get_llm_obs,
    _hash_content,
    LLM_CAPTURE_CONTENT,
)


class TestLLMObservability(unittest.TestCase):

    def setUp(self):
        self.svc = LLMObservabilityService()

    def _record(self, **kwargs):
        defaults = dict(
            tenant_id="t1",
            actor_id="user1",
            model="gpt-4o-mini",
            provider="openai",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=500.0,
        )
        defaults.update(kwargs)
        return self.svc.record_llm_call(**defaults)

    def test_record_llm_call_creates_record(self):
        record = self._record()
        self.assertIsNotNone(record.record_id)
        self.assertEqual(record.model, "gpt-4o-mini")

    def test_token_cost_estimation(self):
        cost = estimate_token_cost("gpt-4o-mini", 1000, 500)
        self.assertGreater(cost, 0.0)
        # Should be < $1 for 1500 tokens on gpt-4o-mini
        self.assertLess(cost, 1.0)

    def test_cost_estimation_disclaimer(self):
        summary = self.svc.get_llm_summary()
        self.assertIn("disclaimer", summary)
        self.assertIn("estimate", summary["disclaimer"].lower())

    def test_no_raw_prompt_stored_by_default(self):
        # Content capture is off by default
        self.assertFalse(LLM_CAPTURE_CONTENT)
        record = self._record(prompt_text="sensitive customer data")
        # Prompt hash is stored (safe), but raw prompt is not in record dict
        d = record.to_dict()
        self.assertNotIn("sensitive customer data", str(d))
        # Hash should be present
        self.assertIsNotNone(record.prompt_hash)

    def test_prompt_hash_different_inputs(self):
        h1 = _hash_content("prompt A")
        h2 = _hash_content("prompt B")
        self.assertNotEqual(h1, h2)

    def test_failed_call_recorded(self):
        record = self._record(success=False, error_type="timeout")
        summary = self.svc.get_llm_summary(tenant_id="t1")
        self.assertGreater(summary["failed_calls"], 0)

    def test_tokens_per_second_calculated(self):
        record = self._record(completion_tokens=100, latency_ms=1000.0)
        self.assertAlmostEqual(record.tokens_per_second, 100.0, places=0)

    def test_by_model_aggregation(self):
        self._record(model="gpt-4o")
        self._record(model="llama-3-70b")
        summary = self.svc.get_llm_summary(tenant_id="t1")
        self.assertIn("by_model", summary)

    def test_agent_execution_summary(self):
        self.svc.record_agent_execution(
            agent_id="a1", agent_name="CostAgent", tenant_id="t1",
            task="analyze costs", duration_ms=2000.0, success=True,
            tool_calls=3, llm_calls=2, total_tokens=500, total_cost_usd=0.001,
        )
        summary = self.svc.get_agent_summary(tenant_id="t1")
        self.assertGreater(summary["total_executions"], 0)
        self.assertIn("completion_rate_pct", summary)

    def test_singleton_accessor(self):
        obs = get_llm_obs()
        self.assertIsNotNone(obs)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5C — Security Intelligence
# ─────────────────────────────────────────────────────────────────────────────
from observability.security_intelligence import (
    SecurityIntelligenceService,
    SecurityEventCategory,
    SecurityEventSeverity,
    SecurityEventStatus,
    get_security_intel,
)


class TestSecurityIntelligence(unittest.TestCase):

    def setUp(self):
        self.svc = SecurityIntelligenceService()

    def test_auth_failure_creates_event(self):
        event = self.svc.ingest_auth_failure("t1", "user1", "api/endpoint", "invalid_token")
        self.assertIsNotNone(event.event_id)
        self.assertEqual(event.category, SecurityEventCategory.AUTH_FAILURE)
        self.assertTrue(event.is_heuristic)

    def test_cross_tenant_event_high_severity(self):
        event = self.svc.ingest_cross_tenant_attempt("tA", "tB", "user1", "model")
        self.assertEqual(event.severity, SecurityEventSeverity.HIGH)
        self.assertEqual(event.category, SecurityEventCategory.CROSS_TENANT)

    def test_policy_denial_recorded(self):
        event = self.svc.ingest_policy_denial("t1", "user1", "model", "deploy", "HighRiskPolicy")
        self.assertEqual(event.category, SecurityEventCategory.POLICY_DENIAL)

    def test_injection_below_threshold_returns_none(self):
        result = self.svc.ingest_injection_attempt("t1", "user1", "model_output", 0.1, [])
        self.assertIsNone(result)

    def test_injection_above_threshold_creates_event(self):
        event = self.svc.ingest_injection_attempt(
            "t1", "user1", "model_output", 0.75, ["untrusted_source", "instruction_override"]
        )
        self.assertIsNotNone(event)
        self.assertTrue(event.is_heuristic)

    def test_heuristic_flag_always_true(self):
        event = self.svc.ingest_auth_failure("t1", "u1", "res", "reason")
        self.assertTrue(event.is_heuristic)

    def test_limitation_disclaimer_present(self):
        event = self.svc.ingest_auth_failure("t1", "u1", "res", "reason")
        self.assertIn("heuristic", event.limitation.lower())
        self.assertIn("NOT", event.limitation)

    def test_investigation_note_system_raises(self):
        event = self.svc.ingest_auth_failure("t1", "u1", "res", "reason")
        with self.assertRaises(PermissionError):
            self.svc.add_investigation_note(event.event_id, "system", "auto note")

    def test_investigation_note_human_ok(self):
        event = self.svc.ingest_auth_failure("t1", "u1", "res", "reason")
        updated = self.svc.add_investigation_note(event.event_id, "alice@orquanta.com", "Investigating")
        self.assertIsNotNone(updated)
        self.assertTrue(any("alice@orquanta.com" in n for n in updated.investigation_notes))

    def test_resolve_system_raises(self):
        event = self.svc.ingest_auth_failure("t1", "u1", "res", "reason")
        with self.assertRaises(PermissionError):
            self.svc.resolve_event(event.event_id, "system", "auto-resolved")

    def test_resolve_human_ok(self):
        event = self.svc.ingest_auth_failure("t1", "u1", "res", "reason")
        updated = self.svc.resolve_event(
            event.event_id, "alice@orquanta.com", "False positive",
            status=SecurityEventStatus.FALSE_POSITIVE,
        )
        self.assertEqual(updated.status, SecurityEventStatus.FALSE_POSITIVE)

    def test_spend_anomaly_critical_at_10x(self):
        event = self.svc.ingest_spend_anomaly("t1", "u1", 1000.0, 50.0)
        self.assertEqual(event.severity, SecurityEventSeverity.CRITICAL)

    def test_summary_has_disclaimer(self):
        summary = self.svc.get_summary()
        self.assertIn("limitation", summary)

    def test_list_events_tenant_isolation(self):
        self.svc.ingest_auth_failure("tA", "uA", "res", "reason")
        self.svc.ingest_auth_failure("tB", "uB", "res", "reason")
        events_A = self.svc.list_events(tenant_id="tA")
        events_B = self.svc.list_events(tenant_id="tB")
        self.assertTrue(all(e["tenant_id"] == "tA" for e in events_A))
        self.assertTrue(all(e["tenant_id"] == "tB" for e in events_B))

    def test_rate_window_increases_severity(self):
        # 6 failures in rapid succession should increase severity to HIGH
        for _ in range(6):
            event = self.svc.ingest_auth_failure("t-rate", "u1", "res", "fail")
        self.assertEqual(event.severity, SecurityEventSeverity.HIGH)

    def test_singleton_accessor(self):
        intel = get_security_intel()
        self.assertIsNotNone(intel)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5D — Agent Intelligence
# ─────────────────────────────────────────────────────────────────────────────
from observability.intelligence import (
    AgentIntelligenceService,
    GPUPerformanceService,
    CostIntelligenceEngine,
    GovernanceReportingService,
    get_agent_intel,
    get_gpu_perf,
    get_cost_engine,
    get_gov_reporting,
)


class TestAgentIntelligence(unittest.TestCase):

    def setUp(self):
        self.svc = AgentIntelligenceService()

    def test_record_event_stores(self):
        event = self.svc.record_event(
            agent_id="a1", agent_name="CostAgent",
            event_type="llm_call", description="GPT-4o call",
            duration_ms=500.0, tokens_used=200,
        )
        self.assertIsNotNone(event.event_id)

    def test_get_agent_timeline_filters(self):
        self.svc.record_event("a1", "CostAgent", "llm_call", "call 1")
        self.svc.record_event("a2", "HealingAgent", "tool_call", "heal 1")
        timeline = self.svc.get_agent_timeline("a1")
        self.assertTrue(all(e["agent_id"] == "a1" for e in timeline))

    def test_workflow_trace_complete(self):
        self.svc.record_event("a1", "CostAgent", "llm_call", "step1",
                               workflow_id="wf-1", tokens_used=100, cost_usd=0.001)
        self.svc.record_event("a1", "CostAgent", "tool_call", "step2",
                               workflow_id="wf-1")
        trace = self.svc.get_workflow_trace("wf-1")
        self.assertIn("timeline", trace)
        self.assertIn("disclaimer", trace)
        self.assertGreater(trace["event_count"], 0)

    def test_analytics_by_agent(self):
        self.svc.record_event("a1", "ForecastAgent", "llm_call", "call", tokens_used=50)
        summary = self.svc.get_analytics_summary()
        self.assertIn("by_agent", summary)
        self.assertIn("ForecastAgent", summary["by_agent"])

    def test_singleton(self):
        self.assertIsNotNone(get_agent_intel())


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5E — GPU and Model Performance
# ─────────────────────────────────────────────────────────────────────────────

class TestGPUPerformance(unittest.TestCase):

    def setUp(self):
        self.svc = GPUPerformanceService()

    def test_record_snapshot_real(self):
        snap = self.svc.record_snapshot(
            provider="runpod", instance_id="inst-1", model_id="llama-3-70b",
            gpu_util_pct=85.0, vram_used_gb=60.0, vram_total_gb=80.0,
            inference_latency_ms=250.0,
            is_real_measurement=True, data_source="vllm_metrics_api",
        )
        self.assertTrue(snap.is_real_measurement)
        self.assertFalse(snap.is_estimated)
        self.assertAlmostEqual(snap.vram_utilization_pct, 75.0, places=1)

    def test_record_snapshot_estimated(self):
        snap = self.svc.record_snapshot(
            provider="groq", instance_id="hosted", model_id="mixtral-8x7b",
            is_real_measurement=False, data_source="api_estimate",
        )
        self.assertFalse(snap.is_real_measurement)
        self.assertTrue(snap.is_estimated)

    def test_data_labels_always_set(self):
        snap = self.svc.record_snapshot(
            provider="p", instance_id="i", model_id="m",
            is_real_measurement=True, data_source="test",
        )
        d = snap.to_dict()
        self.assertIn("is_real_measurement", d)
        self.assertIn("is_estimated", d)
        self.assertIn("is_demo_data", d)
        self.assertIn("limitation", d)

    def test_vram_utilization_calculated(self):
        snap = self.svc.record_snapshot(
            provider="p", instance_id="i", model_id="m",
            vram_used_gb=40.0, vram_total_gb=80.0,
            is_real_measurement=True, data_source="test",
        )
        self.assertAlmostEqual(snap.vram_utilization_pct, 50.0, places=1)

    def test_summary_has_disclaimer(self):
        summary = self.svc.get_performance_summary()
        self.assertIn("disclaimer", summary)

    def test_singleton(self):
        self.assertIsNotNone(get_gpu_perf())


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5F — Cost Intelligence
# ─────────────────────────────────────────────────────────────────────────────

class TestCostIntelligence(unittest.TestCase):

    def setUp(self):
        self.engine = CostIntelligenceEngine()

    def test_record_cost_stores_record(self):
        rec = self.engine.record_cost("t1", "gpu_execution", 5.0, provider="runpod")
        self.assertIsNotNone(rec.record_id)
        self.assertTrue(rec.is_estimated)

    def test_cost_always_estimated(self):
        rec = self.engine.record_cost("t1", "inference_token", 0.01)
        self.assertTrue(rec.is_estimated)
        self.assertFalse(rec.is_actual_billing)

    def test_disclaimer_present(self):
        result = self.engine.get_cost_by_tenant("t1")
        self.assertIn("disclaimer", result)
        self.assertIn("estimate", result["disclaimer"].lower())

    def test_cost_by_tenant_filters(self):
        self.engine.record_cost("tA", "gpu_execution", 10.0)
        self.engine.record_cost("tB", "inference_token", 2.0)
        result = self.engine.get_cost_by_tenant("tA")
        self.assertGreater(result["total_estimated_usd"], 0)

    def test_budget_forecast_no_history(self):
        forecast = self.engine.get_budget_forecast("new-tenant")
        self.assertFalse(forecast["forecast_available"])
        self.assertIn("disclaimer", forecast)

    def test_budget_forecast_with_history(self):
        from datetime import date, timedelta
        # Inject history directly
        self.engine._daily_history["t-hist"] = {}
        for i in range(1, 8):
            d = (date.today() - timedelta(days=i)).isoformat()
            self.engine._daily_history["t-hist"][d] = 50.0
        forecast = self.engine.get_budget_forecast("t-hist")
        self.assertTrue(forecast["forecast_available"])
        self.assertAlmostEqual(forecast["avg_daily_spend_usd"], 50.0, places=0)

    def test_budget_alert_triggered(self):
        self.engine.set_budget_limit("t-alert", 5.0)
        self.engine.record_cost("t-alert", "gpu_execution", 10.0)  # exceeds limit
        alerts = self.engine.get_alerts(tenant_id="t-alert")
        self.assertGreater(len(alerts), 0)
        self.assertTrue(any("BUDGET" in a["alert_type"] for a in alerts))

    def test_optimization_recommendations_heuristic(self):
        recs = self.engine.get_optimization_recommendations("t1")
        for r in recs:
            self.assertTrue(r["is_heuristic"])
            self.assertIn("disclaimer", r)

    def test_singleton(self):
        self.assertIsNotNone(get_cost_engine())


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5G — Governance Reporting
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceReporting(unittest.TestCase):

    def setUp(self):
        self.svc = GovernanceReportingService()

    def test_security_report_has_disclaimer(self):
        report = self.svc.generate_security_report("t1", {"total_events": 5})
        self.assertIn("disclaimer", report)
        self.assertIn("NOT", report["disclaimer"])

    def test_model_usage_report_created(self):
        report = self.svc.generate_model_usage_report("t1", {"calls": 10}, {"snapshots": 5})
        self.assertEqual(report["report_type"], "MODEL_USAGE")
        self.assertIn("disclaimer", report)

    def test_policy_enforcement_report(self):
        decisions = [
            {"decision": "DENY", "policy_id": "p1"},
            {"decision": "ALLOW", "policy_id": "p2"},
            {"decision": "REQUIRE_APPROVAL", "policy_id": "p3"},
        ]
        report = self.svc.generate_policy_enforcement_report("t1", decisions, [])
        self.assertEqual(report["total_decisions"], 3)
        self.assertEqual(report["decisions_denied"], 1)
        self.assertEqual(report["decisions_requiring_approval"], 1)
        self.assertIn("disclaimer", report)

    def test_report_not_compliance_cert(self):
        report = self.svc.generate_security_report("t1", {})
        self.assertIn("does NOT", report["disclaimer"])

    def test_audit_export_has_disclaimer(self):
        export = self.svc.export_audit_evidence("t1", [{"event_id": "e1"}])
        self.assertIn("disclaimer", export)
        self.assertIn("limitation", export)

    def test_risk_summary_report(self):
        report = self.svc.generate_risk_summary_report("t1", {"risks": []}, 5)
        self.assertIn("frameworks_referenced", report)
        self.assertIn("NIST AI RMF", report["frameworks_referenced"])

    def test_list_reports(self):
        self.svc.generate_security_report("t1", {})
        self.svc.generate_model_usage_report("t1", {}, {})
        reports = self.svc.list_reports(tenant_id="t1")
        self.assertGreaterEqual(len(reports), 2)
        for r in reports:
            self.assertIn("report_id", r)
            self.assertIn("report_type", r)

    def test_singleton(self):
        self.assertIsNotNone(get_gov_reporting())


# ─────────────────────────────────────────────────────────────────────────────
# Cross-cutting: Telemetry outage behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestTelemetryOutageBehaviour(unittest.TestCase):

    def test_telemetry_failure_no_impact_on_security_policy(self):
        """
        Verifying that security policy enforcement is independent of telemetry.
        PolicyEngine must work even when telemetry is broken.
        """
        from security.policy_engine import PolicyEngine, Decision
        pe = PolicyEngine()
        # Force simulate telemetry unavailability by breaking the tracer temporarily
        from observability import telemetry as tel_module
        original_tracer = tel_module._tracer
        tel_module._tracer = None  # Simulate outage
        try:
            result = pe.evaluate(
                actor_id="u1", actor_type="human", tenant_id="t1",
                resource_type="model", resource_id="m1", action="infer",
                resource_tenant_id="t1",
            )
            # Policy must still work
            self.assertIsNotNone(result)
            self.assertIsNotNone(result.decision)
        finally:
            tel_module._tracer = original_tracer  # Restore

    def test_no_secrets_in_redacted_telemetry(self):
        """API keys must never appear in telemetry output."""
        from observability.telemetry import redact_sensitive
        # Standard sk- key (no hyphens in the key body — matches regex)
        secret = "sk-abcdefghijklmnopqrstuvwxyz12345"
        redacted = redact_sensitive(f"Request with key {secret}")
        self.assertNotIn(secret, redacted)

    def test_apache_header_in_telemetry(self):
        import pathlib
        src = pathlib.Path(__file__).parent / "observability" / "telemetry.py"
        first_line = src.read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("Apache", first_line)

    def test_apache_header_in_phase5_tests(self):
        import pathlib
        src = pathlib.Path(__file__)
        first_line = src.read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("Apache", first_line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
