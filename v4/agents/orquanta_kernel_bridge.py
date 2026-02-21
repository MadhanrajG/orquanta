"""
OrQuanta Agentic v1.0 — Bomax Kernel Bridge

Compatibility shim that wraps orquanta_kernel_final.py (v3.8) as a callable
tool for v4.0 agents. This provides:
- Backward compatibility: The proven OrMind policy engine continues 
  to run and learn while v4.0 agents are layered on top.
- Data translation: Converts between v4.0 job schemas and v3.8 API format.
- Gradual migration path: Once v4.0 agents accumulate equivalent history,
  this bridge can be disabled via LEGACY_BRIDGE_ENABLED=false.

Architecture decision: Rather than forklift-replace the v3.8 kernel,
we treat it as a "veteran advisor" — its policy decisions feed into
the v4.0 CostOptimizerAgent as one signal among many.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("orquanta.bridge")

# Add parent directory to path so we can import the v3.8 kernel
_PARENT_DIR = str(Path(__file__).parent.parent.parent)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

BRIDGE_ENABLED = os.getenv("LEGACY_BRIDGE_ENABLED", "true").lower() == "true"


class BomaxKernelBridge:
    """Wraps the OrQuanta v3.8 OrMind kernel as a v4.0-compatible tool.
    
    The v3.8 kernel maintains its own policy state (orquanta_policy_prod.json)
    and continues to evolve based on job outcomes. The bridge exposes its
    key decisions (hardware recommendation, policy version) to v4.0 agents.
    
    Usage::
    
        bridge = BomaxKernelBridge()
        
        # Get v3.8 hardware recommendation
        advice = await bridge.get_legacy_recommendation(required_vram_gb=80)
        print(advice["decision"])        # e.g., "H100"
        print(advice["policy_version"])  # e.g., 7
        
        # Submit job through legacy kernel (for A/B comparison)
        result = await bridge.submit_legacy_job("Train LLaMA", required_vram=80)
    """

    def __init__(self) -> None:
        self._kernel_loaded = False
        self._policy = None
        self._jobs_db: dict = {}
        self._load_kernel()

    def _load_kernel(self) -> None:
        """Import and initialise the v3.8 kernel components."""
        if not BRIDGE_ENABLED:
            logger.info("Legacy bridge disabled (LEGACY_BRIDGE_ENABLED=false).")
            return

        try:
            from orquanta_kernel_final import SovereignPolicy, HARDWARE, physics_loop  # type: ignore
            self._policy = SovereignPolicy()
            self._hardware = HARDWARE
            self._physics_loop_fn = physics_loop
            self._kernel_loaded = True
            logger.info(
                f"v3.8 kernel bridge active — policy v{self._policy.version} loaded."
            )
        except ImportError as exc:
            logger.warning(
                f"Could not import orquanta_kernel_final.py: {exc}. "
                f"Legacy bridge will return stub responses."
            )
            self._kernel_loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_legacy_recommendation(
        self, required_vram_gb: int, intent: str = ""
    ) -> dict[str, Any]:
        """Ask the v3.8 OrMind for a hardware recommendation.
        
        Args:
            required_vram_gb: VRAM requirement for the job.
            intent: Natural language description (informational only for v3.8).
            
        Returns:
            dict with decision, scores, policy_version, source.
        """
        if not self._kernel_loaded or self._policy is None:
            return self._stub_recommendation(required_vram_gb)

        try:
            eval_result = self._policy.evaluate(required_vram_gb)
            return {
                "decision": eval_result["decision"],
                "scores": eval_result["scores"],
                "policy_version": eval_result["policy_v"],
                "policy_weights": self._policy.weights.copy(),
                "source": "orquanta_v3.8_or_mind",
                "bridge_enabled": True,
            }
        except Exception as exc:
            logger.error(f"Bridge recommendation failed: {exc}")
            return self._stub_recommendation(required_vram_gb)

    async def submit_legacy_job(
        self, intent: str, required_vram: int
    ) -> dict[str, Any]:
        """Submit a job through the v3.8 kernel for A/B comparison.
        
        The v3.8 kernel's physics loop will run and may trigger policy
        mutations if the job fails (e.g., OOM). This keeps the v3.8
        policy in sync with real-world outcomes.
        
        Returns:
            dict with job_id, decision, policy_version.
        """
        if not self._kernel_loaded or self._policy is None:
            return {"error": "bridge_unavailable", "stub": True}

        try:
            import secrets as sec_mod
            eval_result = self._policy.evaluate(required_vram)
            jid = f"LEGACY-{sec_mod.token_hex(2).upper()}"
            self._jobs_db[jid] = {
                "id": jid,
                "status": "pending",
                "decision": eval_result["decision"],
                "req_vram": required_vram,
                "policy_v": self._policy.version,
            }

            # Run physics loop (OOM detection + policy mutation)
            asyncio.create_task(self._run_physics(jid))

            return {
                "job_id": jid,
                "decision": eval_result["decision"],
                "policy_version": self._policy.version,
                "source": "orquanta_v3.8",
            }
        except Exception as exc:
            logger.error(f"Bridge job submission failed: {exc}")
            return {"error": str(exc)}

    async def get_legacy_policy(self) -> dict[str, Any]:
        """Return the current v3.8 policy state.
        
        Returns:
            dict with version, weights, history_length.
        """
        if not self._kernel_loaded or self._policy is None:
            return {"version": 0, "weights": {}, "source": "stub"}

        return {
            "version": self._policy.version,
            "weights": self._policy.weights.copy(),
            "history_length": len(self._policy.history),
            "source": "orquanta_v3.8_or_mind",
        }

    async def rollback_legacy_policy(self, target_version: int) -> dict[str, Any]:
        """Roll back the v3.8 policy to a specific version.
        
        Returns:
            dict with success, version.
        """
        if not self._kernel_loaded or self._policy is None:
            return {"success": False, "error": "bridge_unavailable"}

        success = self._policy.rollback(target_version)
        return {
            "success": success,
            "version": self._policy.version,
            "source": "orquanta_v3.8",
        }

    def get_bridge_status(self) -> dict[str, Any]:
        """Return bridge health and migration progress.
        
        Returns:
            dict with enabled, kernel_loaded, policy_version, migration_pct.
        """
        status = {
            "bridge_enabled": BRIDGE_ENABLED,
            "kernel_loaded": self._kernel_loaded,
            "deprecation_version": "4.2",
            "migration_recommendation": (
                "Keep bridge active until v4.0 agents have processed 1000+ jobs."
            ),
        }

        if self._kernel_loaded and self._policy:
            status["policy_version"] = self._policy.version
            status["policy_weights"] = self._policy.weights

        return status

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_physics(self, jid: str) -> None:
        """Replicate the v3.8 physics loop for legacy jobs."""
        if not self._kernel_loaded:
            return

        await asyncio.sleep(0.5)
        try:
            job = self._jobs_db.get(jid)
            if not job:
                return

            hw_name = job["decision"]
            hw = self._hardware.get(hw_name)
            if hw is None:
                return

            if hw.vram_gb < job["req_vram"]:
                job["status"] = "failed"
                job["error"] = "OOM_ERROR"
                evt = self._policy.mutate(
                    f"BRIDGE OOM on {jid}",
                    {"risk": 0.8, "perf": 0.4, "cost": -0.8},
                )
                job["mutation"] = evt
                logger.info(f"Bridge: v3.8 policy mutated to v{self._policy.version} after OOM on {jid}")
            else:
                job["status"] = "completed"
                logger.info(f"Bridge: legacy job {jid} completed successfully.")
        except Exception as exc:
            logger.error(f"Bridge physics loop error on {jid}: {exc}")

    def _stub_recommendation(self, required_vram_gb: int) -> dict[str, Any]:
        """Fallback recommendation when kernel is unavailable."""
        # Simple rule: pick H100 for >40GB, A100 for >16GB, T4 otherwise
        if required_vram_gb > 40:
            decision = "H100"
        elif required_vram_gb > 16:
            decision = "A100"
        else:
            decision = "T4"

        return {
            "decision": decision,
            "scores": {},
            "policy_version": 0,
            "source": "bridge_stub_fallback",
            "bridge_enabled": False,
        }
