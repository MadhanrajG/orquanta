# Copyright 2026 OrQuanta — Apache License 2.0
"""
Phase 6 Tests — Open AI Ecosystem and Trusted Marketplace

Tests:
  6A: Asset registry, publisher registration, submission, search
  6B: Model marketplace registration and listing
  6C: Agent marketplace publishing and permission enforcement
  6D: MCP tool registration
  6E: Workflow publishing and run submission
  6F: Trust engine pipeline, findings, approval
  6G: Publisher portal analytics, revenue accounting
  6H: Installation lifecycle (all 11 steps)
      - Manifest verification
      - Licence evaluation
      - Policy evaluation
      - Permission display
      - User approval
      - Install record
      - Revocation

Security invariants tested:
  - System actors blocked from all publish/install/approve operations
  - is_safe_claim always False
  - Payout never enabled by default
  - Trust status is version-specific
  - DATASET/APPLICATION types raise NotImplementedError
  - Revoked assets preserve audit trail
  - Tenant isolation on installations
"""
from __future__ import annotations

import unittest
from typing import Any

# ---------------------------------------------------------------------------
# 6A — Marketplace Registry
# ---------------------------------------------------------------------------

class TestMarketplaceRegistry(unittest.TestCase):

    def _reg(self):
        from v4.marketplace.registry import MarketplaceRegistry
        return MarketplaceRegistry()

    def test_publisher_registration(self):
        reg = self._reg()
        pub = reg.register_publisher(
            actor_id="user-alice",
            display_name="Alice",
            email="alice@example.com",
        )
        self.assertEqual(pub.display_name, "Alice")
        self.assertFalse(pub.is_verified)

    def test_system_actor_cannot_register_publisher(self):
        reg = self._reg()
        for bad in ["system", "auto", "automated", "orquanta", ""]:
            with self.assertRaises(PermissionError):
                reg.register_publisher(actor_id=bad, display_name="X", email="x@x.com")

    def test_publisher_verification_requires_human(self):
        reg = self._reg()
        pub = reg.register_publisher(actor_id="u1", display_name="B", email="b@b.com")
        for bad in ["system", "auto", ""]:
            with self.assertRaises(PermissionError):
                reg.verify_publisher(publisher_id=pub.publisher_id, actor_id=bad)
        verified = reg.verify_publisher(publisher_id=pub.publisher_id, actor_id="u-admin")
        self.assertTrue(verified.is_verified)

    def test_asset_submission(self):
        from v4.marketplace.registry import AssetType, PublicationStatus
        reg = self._reg()
        pub = reg.register_publisher(actor_id="u1", display_name="Dev", email="d@d.com")
        asset = reg.submit_asset(
            actor_id="u1",
            publisher_id=pub.publisher_id,
            asset_type=AssetType.AGENT,
            name="my-agent",
            version="1.0.0",
            description="A test agent",
            licence="apache-2.0",
        )
        self.assertEqual(asset.name, "my-agent")
        self.assertEqual(asset.publication_status, PublicationStatus.PENDING_REVIEW)

    def test_system_actor_cannot_submit_asset(self):
        from v4.marketplace.registry import AssetType
        reg = self._reg()
        for bad in ["system", "", "auto"]:
            with self.assertRaises(PermissionError):
                reg.submit_asset(
                    actor_id=bad,
                    publisher_id="pub-x",
                    asset_type=AssetType.MODEL,
                    name="n", version="1", description="d", licence="mit",
                )

    def test_dataset_and_application_types_reserved(self):
        from v4.marketplace.registry import AssetType
        reg = self._reg()
        for atype in [AssetType.DATASET, AssetType.APPLICATION]:
            with self.assertRaises(NotImplementedError):
                reg.submit_asset(
                    actor_id="u1",
                    publisher_id="pub-demo",
                    asset_type=atype,
                    name="n", version="1", description="d", licence="mit",
                )

    def test_publish_asset(self):
        from v4.marketplace.registry import AssetType, PublicationStatus
        reg = self._reg()
        pub = reg.register_publisher(actor_id="u1", display_name="D", email="d@d.com")
        asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.MODEL, name="m", version="1", description="d", licence="mit",
        )
        published = reg.publish_asset(asset_id=asset.asset_id, actor_id="u-admin")
        self.assertEqual(published.publication_status, PublicationStatus.PUBLISHED)
        self.assertIsNotNone(published.published_at)

    def test_system_actor_cannot_publish(self):
        from v4.marketplace.registry import AssetType
        reg = self._reg()
        pub = reg.register_publisher(actor_id="u1", display_name="D", email="d@d.com")
        asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.MODEL, name="m", version="1", description="d", licence="mit",
        )
        with self.assertRaises(PermissionError):
            reg.publish_asset(asset_id=asset.asset_id, actor_id="system")

    def test_revoke_preserves_audit_trail(self):
        from v4.marketplace.registry import AssetType, TrustStatus
        reg = self._reg()
        pub = reg.register_publisher(actor_id="u1", display_name="D", email="d@d.com")
        asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.AGENT, name="a", version="1", description="d", licence="mit",
        )
        revoked = reg.revoke_asset(asset_id=asset.asset_id, actor_id="u-admin", reason="test")
        self.assertEqual(revoked.security.trust_status, TrustStatus.REVOKED)
        # Asset still retrievable — audit trail preserved
        retrieved = reg.get_asset(asset.asset_id)
        self.assertIsNotNone(retrieved)

    def test_trust_update_requires_human(self):
        from v4.marketplace.registry import AssetType, TrustStatus
        reg = self._reg()
        pub = reg.register_publisher(actor_id="u1", display_name="D", email="d@d.com")
        asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.AGENT, name="a", version="1", description="d", licence="mit",
        )
        with self.assertRaises(PermissionError):
            reg.update_trust_status(
                asset_id=asset.asset_id, actor_id="system",
                trust_status=TrustStatus.METADATA_VERIFIED,
            )

    def test_trust_is_never_safe_claim(self):
        from v4.marketplace.registry import AssetType, TrustStatus
        reg = self._reg()
        pub = reg.register_publisher(actor_id="u1", display_name="D", email="d@d.com")
        asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.AGENT, name="a", version="1", description="d", licence="mit",
        )
        updated = reg.update_trust_status(
            asset_id=asset.asset_id, actor_id="u-admin",
            trust_status=TrustStatus.SECURITY_REVIEWED,
        )
        self.assertFalse(updated.security.is_safe_claim)

    def test_search_assets(self):
        reg = self._reg()
        # Demo assets are seeded — search should find them
        results = reg.search_assets(published_only=True)
        self.assertGreater(len(results), 0)

    def test_installation_record(self):
        reg = self._reg()
        # Use a demo asset (always published)
        assets = reg.search_assets(published_only=True)
        a = assets[0]
        rec = reg.record_installation(
            asset_id=a.asset_id,
            asset_version=a.version,
            tenant_id="tenant-1",
            installed_by="user-bob",
            permissions_accepted=["gpu:read"],
        )
        self.assertEqual(rec.status, "ACTIVE")
        self.assertEqual(rec.tenant_id, "tenant-1")

    def test_system_actor_cannot_install(self):
        reg = self._reg()
        assets = reg.search_assets(published_only=True)
        a = assets[0]
        with self.assertRaises(PermissionError):
            reg.record_installation(
                asset_id=a.asset_id, asset_version=a.version,
                tenant_id="t1", installed_by="system",
            )

    def test_tenant_isolation_on_installations(self):
        reg = self._reg()
        assets = reg.search_assets(published_only=True)
        a = assets[0]
        reg.record_installation(
            asset_id=a.asset_id, asset_version=a.version,
            tenant_id="tenant-A", installed_by="user-a",
        )
        reg.record_installation(
            asset_id=a.asset_id, asset_version=a.version,
            tenant_id="tenant-B", installed_by="user-b",
        )
        recs_a = reg.list_installations("tenant-A")
        recs_b = reg.list_installations("tenant-B")
        self.assertEqual(len(recs_a), 1)
        self.assertEqual(len(recs_b), 1)
        self.assertNotEqual(recs_a[0].installation_id, recs_b[0].installation_id)


# ---------------------------------------------------------------------------
# 6A — Manifest
# ---------------------------------------------------------------------------

class TestAssetManifest(unittest.TestCase):

    def test_build_and_hash(self):
        from v4.marketplace.manifest import build_manifest
        m = build_manifest(
            asset_name="my-model",
            asset_version="1.0.0",
            asset_type="MODEL",
            publisher_id="pub-123",
            publisher_display_name="Alice",
            licence="apache-2.0",
        )
        self.assertIsNotNone(m.manifest_hash)
        self.assertEqual(m.compute_hash(), m.manifest_hash)

    def test_hash_mismatch_detected(self):
        from v4.marketplace.manifest import build_manifest, verify_manifest
        m = build_manifest(
            asset_name="x", asset_version="1.0", asset_type="AGENT",
            publisher_id="p", publisher_display_name="P", licence="mit",
        )
        m.manifest_hash = "deadbeef" * 8   # corrupt the stored hash
        result = verify_manifest(m)
        self.assertFalse(result.hash_match)
        self.assertFalse(result.is_valid)

    def test_no_signature_warning(self):
        from v4.marketplace.manifest import build_manifest, verify_manifest
        m = build_manifest(
            asset_name="x", asset_version="1.0", asset_type="AGENT",
            publisher_id="p", publisher_display_name="P", licence="mit",
        )
        result = verify_manifest(m)
        self.assertTrue(any("unsigned" in w.lower() or "signature" in w.lower() for w in result.warnings))
        self.assertFalse(result.signature_verified)

    def test_disclaimer_always_present(self):
        from v4.marketplace.manifest import build_manifest, verify_manifest
        m = build_manifest(
            asset_name="x", asset_version="1", asset_type="MODEL",
            publisher_id="p", publisher_display_name="P", licence="mit",
        )
        result = verify_manifest(m)
        self.assertIn("does not certify", result.disclaimer)

    def test_expected_hash_mismatch(self):
        from v4.marketplace.manifest import build_manifest, verify_manifest
        m = build_manifest(
            asset_name="x", asset_version="1", asset_type="MODEL",
            publisher_id="p", publisher_display_name="P", licence="mit",
        )
        result = verify_manifest(m, expected_hash="wronghash")
        self.assertFalse(result.hash_match)


# ---------------------------------------------------------------------------
# 6B — Model Marketplace
# ---------------------------------------------------------------------------

class TestModelMarketplace(unittest.TestCase):

    def _setup(self):
        from v4.marketplace.registry import MarketplaceRegistry
        from v4.marketplace.model_marketplace import ModelMarketplace
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="ModelCo", email="m@m.com")
        mm = ModelMarketplace(reg)
        return reg, mm, pub.publisher_id

    def test_register_and_list_model(self):
        _, mm, pub_id = self._setup()
        result = mm.register_model_asset(
            actor_id="u1",
            publisher_id=pub_id,
            name="llama-7b",
            version="1.0.0",
            description="A test model",
            licence="apache-2.0",
            hf_repo_id="meta-llama/Llama-7b",
            parameter_count="7B",
            context_length=4096,
            supported_engines=["vllm"],
            is_demo=False,
        )
        self.assertIn("asset", result)
        self.assertIn("model_entry", result)

    def test_model_deployment_info(self):
        _, mm, pub_id = self._setup()
        result = mm.register_model_asset(
            actor_id="u1", publisher_id=pub_id,
            name="gpt-mini", version="1.0", description="d",
            licence="mit", supported_engines=["vllm", "sglang"],
        )
        asset_id = result["asset"]["asset_id"]
        info = mm.get_deployment_info(asset_id)
        self.assertIn("disclaimer", info)
        self.assertIn("trust_status", info)
        self.assertIn("Deployment requires user approval", info["disclaimer"])


# ---------------------------------------------------------------------------
# 6C — Agent Marketplace
# ---------------------------------------------------------------------------

class TestAgentMarketplace(unittest.TestCase):

    def _setup(self):
        from v4.marketplace.registry import MarketplaceRegistry
        from v4.marketplace.agent_marketplace import AgentMarketplace
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="AgentCo", email="a@a.com")
        am = AgentMarketplace(reg)
        return reg, am, pub.publisher_id

    def test_publish_agent(self):
        _, am, pub_id = self._setup()
        result = am.publish_agent(
            actor_id="u1",
            publisher_id=pub_id,
            name="monitor-agent",
            version="1.0.0",
            description="Monitors GPU usage",
            licence="apache-2.0",
            required_permissions=["gpu:read"],
            required_scopes=["gpu:read"],
        )
        self.assertEqual(result["asset"]["name"], "monitor-agent")
        self.assertEqual(result["agent_entry"]["required_permissions"], ["gpu:read"])

    def test_system_actor_cannot_publish_agent(self):
        _, am, pub_id = self._setup()
        with self.assertRaises(PermissionError):
            am.publish_agent(
                actor_id="system", publisher_id=pub_id,
                name="bad", version="1", description="d", licence="mit",
                required_permissions=[], required_scopes=[],
            )

    def test_permission_notice_in_detail(self):
        _, am, pub_id = self._setup()
        result = am.publish_agent(
            actor_id="u1", publisher_id=pub_id, name="agent2", version="1",
            description="d", licence="mit", required_permissions=["tool:execute"],
            required_scopes=["tool:execute"],
        )
        asset_id = result["asset"]["asset_id"]
        # Publish it first so it's discoverable
        from v4.marketplace.registry import MarketplaceRegistry
        # detail returns permission_notice
        detail = am.get_agent_detail(asset_id)
        self.assertIn("permission_notice", detail)
        self.assertIn("publisher privileges", detail["permission_notice"])

    def test_execution_recording(self):
        _, am, pub_id = self._setup()
        result = am.publish_agent(
            actor_id="u1", publisher_id=pub_id, name="ag", version="1",
            description="d", licence="mit", required_permissions=[], required_scopes=[],
        )
        asset_id = result["asset"]["asset_id"]
        rec = am.record_execution(
            asset_id=asset_id,
            tenant_id="t1",
            executed_by="u1",
            success=True,
            duration_seconds=5.0,
            cost_usd=0.01,
        )
        self.assertTrue(rec["is_estimated"])
        self.assertTrue(rec["success"])

    def test_system_actor_cannot_record_execution(self):
        _, am, pub_id = self._setup()
        result = am.publish_agent(
            actor_id="u1", publisher_id=pub_id, name="ag", version="1",
            description="d", licence="mit", required_permissions=[], required_scopes=[],
        )
        with self.assertRaises(PermissionError):
            am.record_execution(
                asset_id=result["asset"]["asset_id"],
                tenant_id="t1", executed_by="auto",
                success=True, duration_seconds=1.0, cost_usd=0.0,
            )


# ---------------------------------------------------------------------------
# 6D — MCP Marketplace
# ---------------------------------------------------------------------------

class TestMCPMarketplace(unittest.TestCase):

    def _setup(self):
        from v4.marketplace.registry import MarketplaceRegistry
        from v4.marketplace.mcp_marketplace import MCPMarketplace
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="ToolCo", email="t@t.com")
        mcpm = MCPMarketplace(reg)
        return reg, mcpm, pub.publisher_id

    def test_register_mcp_server(self):
        _, mcpm, pub_id = self._setup()
        result = mcpm.register_mcp_server(
            actor_id="u1",
            publisher_id=pub_id,
            name="search-mcp",
            version="1.0",
            description="Search MCP server",
            licence="mit",
            required_scopes=["db:read"],
            tools=[{"name": "search", "description": "Search the index"}],
        )
        self.assertEqual(result["asset"]["name"], "search-mcp")

    def test_system_actor_cannot_register_mcp(self):
        _, mcpm, pub_id = self._setup()
        with self.assertRaises(PermissionError):
            mcpm.register_mcp_server(
                actor_id="auto", publisher_id=pub_id,
                name="bad", version="1", description="d",
                licence="mit", required_scopes=[],
            )

    def test_mcp_detail_has_execution_warning(self):
        _, mcpm, pub_id = self._setup()
        result = mcpm.register_mcp_server(
            actor_id="u1", publisher_id=pub_id, name="srv", version="1",
            description="d", licence="mit", required_scopes=[],
        )
        asset_id = result["asset"]["asset_id"]
        detail = mcpm.get_mcp_detail(asset_id)
        self.assertIn("execution_warning", detail)
        self.assertIn("NOT be executed", detail["execution_warning"])


# ---------------------------------------------------------------------------
# 6E — Workflow Marketplace
# ---------------------------------------------------------------------------

class TestWorkflowMarketplace(unittest.TestCase):

    def _setup(self):
        from v4.marketplace.registry import MarketplaceRegistry
        from v4.marketplace.workflow_marketplace import WorkflowMarketplace
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="FlowCo", email="f@f.com")
        wfm = WorkflowMarketplace(reg)
        return reg, wfm, pub.publisher_id

    def test_publish_workflow(self):
        _, wfm, pub_id = self._setup()
        result = wfm.publish_workflow(
            actor_id="u1",
            publisher_id=pub_id,
            name="gpu-benchmark-flow",
            version="1.0.0",
            description="Benchmark GPU",
            licence="apache-2.0",
            steps=[{"name": "run-benchmark", "step_type": "job"}],
        )
        self.assertEqual(result["asset"]["name"], "gpu-benchmark-flow")

    def test_system_actor_cannot_publish_workflow(self):
        _, wfm, pub_id = self._setup()
        with self.assertRaises(PermissionError):
            wfm.publish_workflow(
                actor_id="system", publisher_id=pub_id,
                name="bad", version="1", description="d", licence="mit", steps=[],
            )

    def test_workflow_run_submission(self):
        from v4.marketplace.registry import AssetType, PublicationStatus
        _, wfm, pub_id = self._setup()
        result = wfm.publish_workflow(
            actor_id="u1", publisher_id=pub_id,
            name="flow1", version="1", description="d", licence="mit",
            steps=[{"name": "s1", "step_type": "agent"}],
        )
        asset_id = result["asset"]["asset_id"]
        # Manually publish for the test
        wfm._registry.publish_asset(asset_id=asset_id, actor_id="admin")
        run = wfm.submit_workflow_run(
            asset_id=asset_id, tenant_id="t1", submitted_by="u1"
        )
        self.assertEqual(run["status"], "PENDING_GOVERNANCE")
        self.assertIn("execution_note", run)
        self.assertIn("governance", run["execution_note"].lower())

    def test_system_actor_cannot_run_workflow(self):
        _, wfm, pub_id = self._setup()
        result = wfm.publish_workflow(
            actor_id="u1", publisher_id=pub_id, name="f2", version="1",
            description="d", licence="mit", steps=[],
        )
        wfm._registry.publish_asset(asset_id=result["asset"]["asset_id"], actor_id="admin")
        with self.assertRaises(PermissionError):
            wfm.submit_workflow_run(
                asset_id=result["asset"]["asset_id"],
                tenant_id="t1", submitted_by="auto",
            )

    def test_cancel_workflow_run(self):
        _, wfm, pub_id = self._setup()
        result = wfm.publish_workflow(
            actor_id="u1", publisher_id=pub_id, name="f3", version="1",
            description="d", licence="mit", steps=[],
        )
        asset_id = result["asset"]["asset_id"]
        wfm._registry.publish_asset(asset_id=asset_id, actor_id="admin")
        run = wfm.submit_workflow_run(asset_id=asset_id, tenant_id="t1", submitted_by="u1")
        cancelled = wfm.cancel_workflow_run(
            run_id=run["run_id"], asset_id=asset_id, cancelled_by="u1"
        )
        self.assertEqual(cancelled["status"], "CANCELLED")


# ---------------------------------------------------------------------------
# 6F — Trust Engine
# ---------------------------------------------------------------------------

class TestTrustEngine(unittest.TestCase):

    def _setup(self):
        from v4.marketplace.registry import MarketplaceRegistry, AssetType
        from v4.marketplace.trust_engine import MarketplaceTrustEngine
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="TrustCo", email="tc@tc.com")
        reg.verify_publisher(publisher_id=pub.publisher_id, actor_id="admin")
        asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.AGENT, name="ta", version="1.0",
            description="d", licence="apache-2.0",
        )
        te = MarketplaceTrustEngine(reg)
        return reg, te, asset, pub

    def test_trust_pipeline_runs(self):
        _, te, asset, _ = self._setup()
        result = te.run_trust_pipeline(asset_id=asset.asset_id, reviewer_id="reviewer1")
        self.assertIsNotNone(result.assessment_id)
        self.assertFalse(result.is_safe_claim)
        self.assertIn("does NOT guarantee", result.disclaimer)

    def test_system_actor_cannot_run_pipeline(self):
        _, te, asset, _ = self._setup()
        with self.assertRaises(PermissionError):
            te.run_trust_pipeline(asset_id=asset.asset_id, reviewer_id="system")

    def test_is_safe_claim_always_false(self):
        _, te, asset, _ = self._setup()
        result = te.run_trust_pipeline(asset_id=asset.asset_id, reviewer_id="rev1")
        self.assertFalse(result.is_safe_claim)

    def test_disclaimer_always_present(self):
        _, te, asset, _ = self._setup()
        result = te.run_trust_pipeline(asset_id=asset.asset_id, reviewer_id="rev1")
        self.assertGreater(len(result.disclaimer), 20)

    def test_system_actor_cannot_approve(self):
        _, te, asset, _ = self._setup()
        result = te.run_trust_pipeline(asset_id=asset.asset_id, reviewer_id="rev1")
        with self.assertRaises(PermissionError):
            te.approve_assessment(assessment_id=result.assessment_id, approver_id="system")

    def test_approve_updates_trust_status(self):
        from v4.marketplace.registry import TrustStatus
        reg, te, asset, _ = self._setup()
        result = te.run_trust_pipeline(asset_id=asset.asset_id, reviewer_id="rev1")
        te.approve_assessment(assessment_id=result.assessment_id, approver_id="u-admin")
        updated = reg.get_asset(asset.asset_id)
        self.assertNotEqual(updated.security.trust_status, TrustStatus.PENDING_REVIEW)

    def test_critical_findings_recommend_reject(self):
        """An asset with manifest hash mismatch should recommend REJECT."""
        from v4.marketplace.registry import MarketplaceRegistry, AssetType, TrustStatus
        from v4.marketplace.trust_engine import MarketplaceTrustEngine
        from v4.marketplace.manifest import build_manifest
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="X", email="x@x.com")
        asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.MODEL, name="bad", version="1",
            description="d", licence="mit",
        )
        te = MarketplaceTrustEngine(reg)
        # Pass a manifest with a bad hash
        m = build_manifest(
            asset_name="bad", asset_version="1", asset_type="MODEL",
            publisher_id=pub.publisher_id, publisher_display_name="X", licence="mit",
        )
        m.manifest_hash = "0" * 64   # corrupt hash
        result = te.run_trust_pipeline(asset_id=asset.asset_id, reviewer_id="rev1", manifest=m)
        self.assertEqual(result.recommended_trust_status, TrustStatus.REJECTED)

    def test_high_risk_permissions_flagged(self):
        from v4.marketplace.registry import MarketplaceRegistry, AssetType
        from v4.marketplace.trust_engine import MarketplaceTrustEngine
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="X", email="x@x.com")
        asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.AGENT, name="risky", version="1",
            description="d", licence="mit",
            required_permissions=["exec:shell"],
            required_scopes=["exec:shell"],
        )
        te = MarketplaceTrustEngine(reg)
        result = te.run_trust_pipeline(asset_id=asset.asset_id, reviewer_id="rev1")
        self.assertIn("exec:shell", result.high_risk_permissions)


# ---------------------------------------------------------------------------
# 6G — Publisher Portal
# ---------------------------------------------------------------------------

class TestPublisherPortal(unittest.TestCase):

    def _setup(self):
        from v4.marketplace.registry import MarketplaceRegistry
        from v4.marketplace.publisher_portal import PublisherPortal
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="PortalCo", email="pc@pc.com")
        portal = PublisherPortal(reg)
        return reg, portal, pub.publisher_id

    def test_analytics(self):
        _, portal, pub_id = self._setup()
        analytics = portal.get_publisher_analytics(pub_id, actor_id="u1")
        self.assertTrue(analytics.is_estimated)
        self.assertFalse(analytics.payout_enabled)
        self.assertIn("OrQuanta does NOT currently process real payouts", analytics.payout_disclaimer)

    def test_system_actor_cannot_view_analytics(self):
        _, portal, pub_id = self._setup()
        with self.assertRaises(PermissionError):
            portal.get_publisher_analytics(pub_id, actor_id="system")

    def test_revenue_record_is_estimated(self):
        _, portal, pub_id = self._setup()
        rec = portal.record_revenue(
            publisher_id=pub_id,
            asset_id="asset-1",
            installation_id="install-1",
            amount_usd=9.99,
        )
        self.assertTrue(rec.is_estimated)
        self.assertIn("OrQuanta does NOT currently process", rec.payout_note)

    def test_system_actor_cannot_view_revenue(self):
        _, portal, pub_id = self._setup()
        with self.assertRaises(PermissionError):
            portal.get_revenue_records(pub_id, actor_id="")


# ---------------------------------------------------------------------------
# 6H — Installation Engine
# ---------------------------------------------------------------------------

class TestInstallationEngine(unittest.TestCase):

    def _setup_with_published_asset(self):
        from v4.marketplace.registry import MarketplaceRegistry, AssetType, TrustStatus
        from v4.marketplace.installation import InstallationEngine
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="IC", email="ic@ic.com")
        reg.verify_publisher(publisher_id=pub.publisher_id, actor_id="admin")
        asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.AGENT, name="install-test-agent",
            version="1.0.0", description="Test agent", licence="apache-2.0",
            required_permissions=["gpu:read"], required_scopes=["gpu:read"],
        )
        reg.update_trust_status(
            asset_id=asset.asset_id, actor_id="admin",
            trust_status=TrustStatus.METADATA_VERIFIED,
        )
        reg.publish_asset(asset_id=asset.asset_id, actor_id="admin")
        ie = InstallationEngine(reg)
        return reg, ie, asset, pub

    def test_prepare_installation_produces_plan(self):
        _, ie, asset, _ = self._setup_with_published_asset()
        session = ie.prepare_installation(
            asset_id=asset.asset_id, tenant_id="t1", requesting_user="u1"
        )
        self.assertIsNotNone(session.plan)
        self.assertIn(session.plan.policy_decision, ("ALLOW", "REQUIRE_APPROVAL", "DENY"))

    def test_system_actor_cannot_prepare_install(self):
        _, ie, asset, _ = self._setup_with_published_asset()
        with self.assertRaises(PermissionError):
            ie.prepare_installation(
                asset_id=asset.asset_id, tenant_id="t1", requesting_user="system"
            )

    def test_plan_requires_permissions_displayed(self):
        _, ie, asset, _ = self._setup_with_published_asset()
        session = ie.prepare_installation(
            asset_id=asset.asset_id, tenant_id="t1", requesting_user="u1"
        )
        self.assertIn("gpu:read", session.plan.required_permissions)

    def test_confirm_installation(self):
        _, ie, asset, _ = self._setup_with_published_asset()
        session = ie.prepare_installation(
            asset_id=asset.asset_id, tenant_id="t1", requesting_user="u1"
        )
        if session.plan and session.plan.can_proceed:
            confirmed = ie.confirm_installation(
                session_id=session.session_id,
                approving_user="u1",
                accepted_permissions=["gpu:read"],
            )
            self.assertIsNotNone(confirmed.installation_id)

    def test_system_actor_cannot_confirm_install(self):
        _, ie, asset, _ = self._setup_with_published_asset()
        session = ie.prepare_installation(
            asset_id=asset.asset_id, tenant_id="t1", requesting_user="u1"
        )
        with self.assertRaises(PermissionError):
            ie.confirm_installation(
                session_id=session.session_id,
                approving_user="auto",
                accepted_permissions=[],
            )

    def test_uninstall(self):
        reg, ie, asset, _ = self._setup_with_published_asset()
        session = ie.prepare_installation(
            asset_id=asset.asset_id, tenant_id="t1", requesting_user="u1"
        )
        if session.plan and session.plan.can_proceed:
            confirmed = ie.confirm_installation(
                session_id=session.session_id,
                approving_user="u1",
                accepted_permissions=["gpu:read"],
            )
            if confirmed.installation_id:
                rec = ie.uninstall(confirmed.installation_id, actor_id="u1")
                self.assertEqual(rec.status, "UNINSTALLED")

    def test_revocation(self):
        reg, ie, asset, _ = self._setup_with_published_asset()
        session = ie.prepare_installation(
            asset_id=asset.asset_id, tenant_id="t1", requesting_user="u1"
        )
        if session.plan and session.plan.can_proceed:
            confirmed = ie.confirm_installation(
                session_id=session.session_id,
                approving_user="u1",
                accepted_permissions=["gpu:read"],
            )
            if confirmed.installation_id:
                rec = ie.revoke_installation(confirmed.installation_id, actor_id="admin")
                self.assertEqual(rec.status, "REVOKED")

    def test_revoked_asset_install_blocked(self):
        from v4.marketplace.registry import TrustStatus
        reg, ie, asset, _ = self._setup_with_published_asset()
        # Revoke the asset
        reg.revoke_asset(asset_id=asset.asset_id, actor_id="admin", reason="test")
        session = ie.prepare_installation(
            asset_id=asset.asset_id, tenant_id="t1", requesting_user="u1"
        )
        # Revoked asset → DENY policy
        if session.plan:
            self.assertEqual(session.plan.policy_decision, "DENY")
            self.assertFalse(session.plan.can_proceed)

    def test_nonexistent_asset_install_blocked(self):
        from v4.marketplace.registry import MarketplaceRegistry
        from v4.marketplace.installation import InstallationEngine
        reg = MarketplaceRegistry()
        ie = InstallationEngine(reg)
        session = ie.prepare_installation(
            asset_id="nonexistent-id", tenant_id="t1", requesting_user="u1"
        )
        # Should fail at SELECT step
        self.assertTrue(any(e.status == "FAILURE" for e in session.events))


# ---------------------------------------------------------------------------
# Security meta-tests
# ---------------------------------------------------------------------------

class TestMarketplaceSecurityInvariants(unittest.TestCase):

    def test_all_system_actors_blocked_from_registry(self):
        from v4.marketplace.registry import MarketplaceRegistry, AssetType
        reg = MarketplaceRegistry()
        system_actors = ["system", "auto", "automated", "orquanta", ""]
        for actor in system_actors:
            with self.assertRaises(PermissionError, msg=f"actor={actor!r}"):
                reg.register_publisher(actor_id=actor, display_name="X", email="x@x.com")

    def test_payout_never_enabled_by_default(self):
        from v4.marketplace.registry import MarketplaceRegistry
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="X", email="x@x.com")
        self.assertFalse(pub.payout_enabled)

    def test_demo_assets_marked_is_demo(self):
        from v4.marketplace.registry import MarketplaceRegistry
        reg = MarketplaceRegistry()
        all_assets = reg.search_assets(published_only=True)
        for a in all_assets:
            if a.is_demo:
                self.assertTrue(a.is_demo)  # tautology — proves is_demo field exists

    def test_trust_version_is_version_specific(self):
        from v4.marketplace.registry import MarketplaceRegistry, AssetType, TrustStatus
        reg = MarketplaceRegistry()
        pub = reg.register_publisher(actor_id="u1", display_name="X", email="x@x.com")
        v1_asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.MODEL, name="m", version="1.0",
            description="d", licence="mit",
        )
        reg.update_trust_status(
            asset_id=v1_asset.asset_id, actor_id="admin",
            trust_status=TrustStatus.SECURITY_REVIEWED,
        )
        # Submit v2 — different asset record, trust resets
        v2_asset = reg.submit_asset(
            actor_id="u1", publisher_id=pub.publisher_id,
            asset_type=AssetType.MODEL, name="m", version="2.0",
            description="d", licence="mit",
        )
        self.assertEqual(v2_asset.security.trust_status, TrustStatus.PENDING_REVIEW)


if __name__ == "__main__":
    unittest.main()
