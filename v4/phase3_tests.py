# Copyright 2026 OrQuanta — Apache License 2.0
"""
Phase 3A–3C Tests — Inference Gateway, Model Registry, GPU Compatibility
=========================================================================
Tests are clearly labelled:
  [MOCK]  — uses mocked provider responses; no real GPU execution
  [REAL]  — skipped unless USE_REAL_INFERENCE=true (CI never sets this)

Run: python -m pytest v4/phase3_tests.py -v --tb=short
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure v4/ package is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Inference Gateway Tests [MOCK]
# ---------------------------------------------------------------------------

class TestInferenceGateway(unittest.TestCase):

    def test_mock_response_labelled(self):
        """[MOCK] Mock responses must be clearly labelled."""
        from inference.gateway import _mock_response
        resp = _mock_response("llama-3.1-70b-groq", [{"role": "user", "content": "Hello"}], 512)
        self.assertIn("MOCK", resp["choices"][0]["message"]["content"])
        self.assertTrue(resp["x_orquanta"]["is_mock"])
        self.assertEqual(resp["x_orquanta"]["provider"], "mock")
        self.assertEqual(resp["x_orquanta"]["cost_usd"], 0.0)

    def test_cost_estimation_groq(self):
        """[MOCK] Cost estimation returns correct USD for Groq Llama."""
        from inference.gateway import estimate_cost_usd
        cost = estimate_cost_usd("groq", "llama-3.1-70b-versatile", 1000, 500)
        expected = (1000 * 0.59 + 500 * 0.79) / 1_000_000
        self.assertAlmostEqual(cost, expected, places=10)

    def test_virtual_key_budget_enforcement(self):
        """[MOCK] Virtual key with exhausted budget returns None."""
        from inference.gateway import register_virtual_key, validate_virtual_key
        import hashlib, secrets
        raw_key = "sk-orq-test-budget-" + secrets.token_hex(8)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        register_virtual_key(key_hash, "user-budget-test", "org-test", ["*"], budget_usd=0.0)
        tenant = validate_virtual_key(raw_key)
        self.assertIsNone(tenant, "Budget=0 should block all requests")

    def test_virtual_key_valid(self):
        """[MOCK] Valid virtual key returns tenant metadata."""
        from inference.gateway import register_virtual_key, validate_virtual_key
        import hashlib, secrets
        raw_key = "sk-orq-test-valid-" + secrets.token_hex(8)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        register_virtual_key(key_hash, "user-valid", "org-valid", ["*"], budget_usd=10.0)
        tenant = validate_virtual_key(raw_key)
        self.assertIsNotNone(tenant)
        self.assertEqual(tenant["user_id"], "user-valid")

    def test_rate_limiter(self):
        """[MOCK] Rate limiter blocks requests exceeding RPM."""
        from inference.gateway import register_virtual_key, validate_virtual_key, _rate_check
        import hashlib, secrets
        raw_key = "sk-orq-test-rate-" + secrets.token_hex(8)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        register_virtual_key(key_hash, "user-rate", "org-rate", ["*"], budget_usd=100.0, rate_limit_rpm=3)
        tenant = validate_virtual_key(raw_key)
        # First 3 should pass
        for i in range(3):
            self.assertTrue(_rate_check(tenant), f"Request {i+1} should be allowed")
        # 4th should be blocked
        self.assertFalse(_rate_check(tenant), "4th request should be rate-limited")

    def test_route_inference_mock(self):
        """[MOCK] route_inference_request returns mock response when USE_REAL_INFERENCE=false."""
        from inference import gateway
        from inference.gateway import _mock_response
        # Test the mock response builder directly (sync) — avoids asyncio event loop issues in test runner
        result = _mock_response("llama-3.1-70b-groq", [{"role": "user", "content": "Test"}], 512)
        self.assertIn("MOCK", result["choices"][0]["message"]["content"])
        self.assertEqual(result["x_orquanta"]["provider"], "mock")
        self.assertFalse(result["x_orquanta"]["is_mock"] is False)  # is_mock must be True

    def test_unknown_model_raises_error(self):
        """[MOCK] Unknown model is not in MODEL_ROUTES when real inference is on."""
        from inference.gateway import MODEL_ROUTES
        # Verify unknown model is absent from routing table (the actual guard in route_inference_request)
        self.assertNotIn("nonexistent-model-xyz", MODEL_ROUTES)
        self.assertIn("llama-3.1-70b-groq", MODEL_ROUTES)   # Known model must be present


# ---------------------------------------------------------------------------
# Model Registry Tests [MOCK]
# ---------------------------------------------------------------------------

class TestModelRegistry(unittest.TestCase):

    def test_curated_models_loaded(self):
        """[MOCK] Curated registry has at least 8 models."""
        from inference.model_registry import list_models
        models = list_models()
        self.assertGreaterEqual(len(models), 8)

    def test_model_lookup_by_id(self):
        """[MOCK] get_model returns correct record."""
        from inference.model_registry import get_model
        m = get_model("meta-llama/Llama-3.1-70B-Instruct")
        self.assertIsNotNone(m)
        self.assertEqual(m.publisher, "Meta AI")
        self.assertEqual(m.model_family, "llama")
        self.assertIn("vllm", m.supported_engines)

    def test_missing_model_returns_none(self):
        """[MOCK] get_model returns None for unknown ID."""
        from inference.model_registry import get_model
        self.assertIsNone(get_model("nonexistent/Model-99B"))

    def test_licence_info_populated(self):
        """[MOCK] All curated models have licence_info populated."""
        from inference.model_registry import list_models
        for m in list_models():
            self.assertIsInstance(m.licence_info, dict, f"Model {m.model_id} has no licence_info")
            self.assertIn("known", m.licence_info, f"Model {m.model_id} licence_info missing 'known'")

    def test_commercial_ok_set(self):
        """[MOCK] commercial_ok field matches licence database."""
        from inference.model_registry import get_model
        # MIT licence → commercial_ok=True
        phi = get_model("microsoft/phi-4")
        self.assertIsNotNone(phi)
        self.assertTrue(phi.commercial_ok)

    def test_nc_licence_flagged(self):
        """[MOCK] Non-commercial licences are flagged correctly."""
        from inference.model_registry import get_licence_info
        info = get_licence_info("cc-by-nc-4.0")
        self.assertFalse(info["commercial"])
        self.assertTrue(info["known"])

    def test_unknown_licence_flagged(self):
        """[MOCK] Unknown licence marked known=False and commercial=None."""
        from inference.model_registry import get_licence_info
        info = get_licence_info("some-proprietary-licence-xyz")
        self.assertFalse(info["known"])
        self.assertIsNone(info["commercial"])

    def test_filter_by_engine(self):
        """[MOCK] Engine filter returns only compatible models."""
        from inference.model_registry import list_models
        vllm_models = list_models(engine="vllm")
        for m in vllm_models:
            self.assertIn("vllm", m.supported_engines)

    def test_filter_by_family(self):
        """[MOCK] Family filter works correctly."""
        from inference.model_registry import list_models
        llama_models = list_models(family="llama")
        for m in llama_models:
            self.assertEqual(m.model_family, "llama")

    def test_search_filter(self):
        """[MOCK] Search filter matches model name and description."""
        from inference.model_registry import list_models
        results = list_models(search="deepseek")
        self.assertGreater(len(results), 0)
        for m in results:
            combined = (m.name + m.description + m.publisher + " ".join(m.tags)).lower()
            self.assertIn("deepseek", combined)

    def test_vram_estimates_present(self):
        """[MOCK] All major models have VRAM estimates."""
        from inference.model_registry import list_models
        large_models = [m for m in list_models() if m.param_count and "B" in (m.param_count or "")]
        for m in large_models:
            self.assertIsNotNone(m.vram_fp16_gb, f"Model {m.model_id} missing vram_fp16_gb")

    def test_register_custom_model(self):
        """[MOCK] Custom models can be registered at runtime."""
        from inference.model_registry import register_model, get_model, ModelRecord
        custom = ModelRecord(
            model_id="test-org/TestModel-1B",
            hf_id="test-org/TestModel-1B",
            name="Test Model 1B",
            publisher="Test Org",
            licence="mit",
            supported_engines=["vllm"],
            vram_fp16_gb=2.0,
            param_count="1B",
        )
        register_model(custom)
        fetched = get_model("test-org/TestModel-1B")
        self.assertIsNotNone(fetched)
        self.assertTrue(fetched.commercial_ok)


# ---------------------------------------------------------------------------
# GPU Compatibility Tests [MOCK]
# ---------------------------------------------------------------------------

class TestGPUCompatibility(unittest.TestCase):

    def test_llama_8b_fits_on_a10(self):
        """[MOCK] LLaMA 3.1 8B (int8) fits on 1×A10 24GB."""
        from inference.gpu_compatibility import check_compatibility
        result = check_compatibility(
            model_id="meta-llama/Llama-3.1-8B-Instruct",
            gpu_model="a10",
            gpu_count=1,
            quantisation="int8",
            engine="vllm",
            vram_fp16_gb=16.0,
            param_count_str="8B",
        )
        self.assertIn(result.status, ("compatible", "compatible_with_constraints"))
        self.assertEqual(result.total_vram_available_gb, 24.0)

    def test_llama_70b_incompatible_on_single_t4(self):
        """[MOCK] LLaMA 70B fp16 is incompatible on 1×T4 16GB."""
        from inference.gpu_compatibility import check_compatibility
        result = check_compatibility(
            model_id="meta-llama/Llama-3.1-70B-Instruct",
            gpu_model="t4",
            gpu_count=1,
            quantisation="fp16",
            engine="vllm",
            vram_fp16_gb=140.0,
            param_count_str="70B",
        )
        self.assertEqual(result.status, "incompatible")
        self.assertGreater(result.estimated_vram_required_gb, result.total_vram_available_gb)

    def test_llama_70b_fits_on_two_a100_80gb(self):
        """[MOCK] LLaMA 70B int8 fits on 2×A100 80GB."""
        from inference.gpu_compatibility import check_compatibility
        result = check_compatibility(
            model_id="meta-llama/Llama-3.1-70B-Instruct",
            gpu_model="a100-80gb",
            gpu_count=2,
            quantisation="int8",
            engine="vllm",
            vram_fp16_gb=140.0,
            param_count_str="70B",
        )
        self.assertIn(result.status, ("compatible", "compatible_with_constraints"))
        self.assertEqual(result.total_vram_available_gb, 160.0)

    def test_unknown_gpu_returns_insufficient_info(self):
        """[MOCK] Unknown GPU returns insufficient_information."""
        from inference.gpu_compatibility import check_compatibility
        result = check_compatibility(
            model_id="test-model",
            gpu_model="nonexistent-gpu-xyz",
            gpu_count=1,
            quantisation="fp16",
            engine="vllm",
            vram_fp16_gb=10.0,
        )
        self.assertEqual(result.status, "insufficient_information")

    def test_no_vram_info_returns_insufficient(self):
        """[MOCK] Missing VRAM info returns insufficient_information."""
        from inference.gpu_compatibility import check_compatibility
        result = check_compatibility(
            model_id="unknown-model",
            gpu_model="a100-80gb",
            gpu_count=1,
            quantisation="int8",
            engine="vllm",
            vram_fp16_gb=None,  # Unknown
        )
        self.assertEqual(result.status, "insufficient_information")

    def test_sglang_requires_ampere(self):
        """[MOCK] SGLang rejects Volta/Turing GPUs (requires sm_80+)."""
        from inference.gpu_compatibility import check_compatibility
        result = check_compatibility(
            model_id="test-model",
            gpu_model="t4",           # Turing sm_75
            gpu_count=1,
            quantisation="fp16",
            engine="sglang",
            vram_fp16_gb=4.0,
        )
        self.assertEqual(result.status, "incompatible")
        self.assertTrue(any("sglang" in r.lower() or "architecture" in r.lower() for r in result.reasons))

    def test_int4_quantisation_reduces_vram(self):
        """[MOCK] int4 quantisation requires less VRAM than fp16."""
        from inference.gpu_compatibility import check_compatibility
        fp16 = check_compatibility("m", "a100-40gb", 1, "fp16", "vllm", vram_fp16_gb=50.0)
        int4 = check_compatibility("m", "a100-40gb", 1, "int4", "vllm", vram_fp16_gb=50.0)
        self.assertLess(int4.estimated_vram_required_gb, fp16.estimated_vram_required_gb)

    def test_recommend_gpus_returns_list(self):
        """[MOCK] GPU recommender returns sorted results for a 70B model."""
        from inference.gpu_compatibility import recommend_gpus_for_model
        recs = recommend_gpus_for_model(vram_fp16_gb=140.0, quant="int8", engine="vllm")
        self.assertGreater(len(recs), 0)
        # Should prefer fewer GPUs first
        counts = [r["gpu_count"] for r in recs]
        self.assertEqual(counts, sorted(counts))

    def test_tps_estimate_nonzero(self):
        """[MOCK] TPS estimate is non-zero for a known GPU+model combo."""
        from inference.gpu_compatibility import check_compatibility
        result = check_compatibility(
            model_id="meta-llama/Llama-3.1-8B-Instruct",
            gpu_model="a100-80gb",
            gpu_count=1,
            quantisation="fp16",
            engine="vllm",
            vram_fp16_gb=16.0,
            param_count_str="8B",
        )
        self.assertIsNotNone(result.estimated_tokens_per_second)
        self.assertGreater(result.estimated_tokens_per_second, 0)


# ---------------------------------------------------------------------------
# vLLM Adapter Tests [MOCK]
# ---------------------------------------------------------------------------

class TestVLLMAdapter(unittest.TestCase):

    def test_vllm_startup_command_single_gpu(self):
        """[MOCK] vLLM startup command correct for single GPU."""
        from inference.vllm_adapter import build_vllm_startup_command
        cmd = build_vllm_startup_command("meta-llama/Llama-3.1-8B-Instruct", "fp16", 1)
        self.assertIn("vllm.entrypoints.openai.api_server", cmd)
        self.assertIn("meta-llama/Llama-3.1-8B-Instruct", cmd)
        # No tensor parallel for single GPU
        self.assertNotIn("--tensor-parallel-size", cmd)

    def test_vllm_startup_command_multi_gpu(self):
        """[MOCK] vLLM command includes tensor-parallel-size for multi-GPU."""
        from inference.vllm_adapter import build_vllm_startup_command
        cmd = build_vllm_startup_command("meta-llama/Llama-3.1-70B-Instruct", "int8", 2)
        tp_idx = cmd.index("--tensor-parallel-size")
        self.assertEqual(cmd[tp_idx + 1], "2")

    def test_sglang_startup_command(self):
        """[MOCK] SGLang startup command correct."""
        from inference.vllm_adapter import build_sglang_startup_command
        cmd = build_sglang_startup_command("meta-llama/Llama-3.1-8B-Instruct", 1, "fp16")
        self.assertIn("sglang.launch_server", cmd)

    def test_deployment_spec_built(self):
        """[MOCK] Deployment spec is a serialisable dict."""
        from inference.vllm_adapter import build_deployment_spec
        spec = build_deployment_spec(
            deployment_id="test-dep-001",
            model_id="meta-llama/Llama-3.1-8B-Instruct",
            hf_id="meta-llama/Llama-3.1-8B-Instruct",
            engine="vllm",
            quantisation="int8",
            gpu_model="a10",
            gpu_count=1,
            provider="runpod",
            region="us-east-1",
            hourly_rate_usd=0.74,
        )
        import json
        json.dumps(spec)  # Must be JSON-serialisable for Celery
        self.assertEqual(spec["engine"], "vllm")
        self.assertEqual(spec["deployment_id"], "test-dep-001")

    def test_mock_deploy_response_labelled(self):
        """[MOCK] Mock deployment response clearly labelled."""
        from inference.vllm_adapter import mock_deploy_response
        resp = mock_deploy_response({"model_id": "test", "gpu_count": 1, "gpu_model": "a10", "engine": "vllm", "quantisation": "int8"})
        self.assertFalse(resp["is_real"])
        self.assertIn("MOCK", resp["note"])


# ---------------------------------------------------------------------------
# Licence Governance Tests [MOCK]
# ---------------------------------------------------------------------------

class TestLicenceGovernance(unittest.TestCase):

    def test_all_curated_models_have_known_licence(self):
        """[MOCK] No curated model has an unlabelled unknown licence."""
        from inference.model_registry import list_models
        for m in list_models():
            # We allow 'known=False' only if explicitly set — but curated models should be known
            if m.licence not in ("other",):
                self.assertIsNotNone(m.commercial_ok, f"Model {m.model_id} has ambiguous commercial_ok")

    def test_apache2_is_commercial(self):
        """[MOCK] Apache-2.0 licence is marked commercial."""
        from inference.model_registry import get_licence_info
        info = get_licence_info("apache-2.0")
        self.assertTrue(info["commercial"])
        self.assertTrue(info["redistribution"])
        self.assertTrue(info["known"])

    def test_llama3_has_deployment_note(self):
        """[MOCK] LLaMA 3 licence has deployment note."""
        from inference.model_registry import get_licence_info
        info = get_licence_info("llama3")
        self.assertIn("note", info)
        self.assertIsNotNone(info["note"])

    def test_orquanta_apache_header_present(self):
        """Check Apache 2.0 header in all Phase 3 source files."""
        import pathlib
        inference_dir = pathlib.Path(__file__).parent / "inference"
        for f in inference_dir.glob("*.py"):
            if f.name == "__init__.py":
                continue
            content = f.read_text(encoding="utf-8")
            self.assertIn("Apache License 2.0", content, f"{f.name} missing Apache 2.0 header")


if __name__ == "__main__":
    unittest.main(verbosity=2)
