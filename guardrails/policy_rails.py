"""
OrQuanta NeMo-Style Policy Rails

Reads rails_config.yaml and provides a pre-execution gate for every
autonomous agent action. Integrates with SafetyGovernor.authorize_and_run()
as an additional policy enforcement layer.

Usage::

    from guardrails import get_rails

    rails = get_rails()
    rails.check_action(
        agent="scheduler_agent",
        action="scale_down",
        cost_usd=45.0,
        confidence=0.88,
    )
    # Raises RailsViolation if any policy is breached.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("orquanta.guardrails")

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RailsViolation(Exception):
    """Raised when an agent action violates a guardrail policy."""
    def __init__(self, rail_type: str, message: str) -> None:
        self.rail_type = rail_type
        super().__init__(f"[{rail_type}] {message}")


# ---------------------------------------------------------------------------
# PolicyRails — the guard that wraps every agent action
# ---------------------------------------------------------------------------

class PolicyRails:
    """
    Enforces the guardrail policies defined in rails_config.yaml.

    Every call to `check_action()` runs through:

    1. **Action Rail** — blocked list + confidence check
    2. **Budget Rail** — single-action cost sanity
    3. **Rate Rail**  — per-agent action frequency (delegated to SafetyGovernor)
    4. **Output Rail** — flag suspicious reasoning text

    Call this BEFORE SafetyGovernor.authorize_and_run() for defence-in-depth.
    """

    _CONFIG_PATH = Path(__file__).parent / "rails_config.yaml"

    def __init__(self) -> None:
        self._cfg: dict[str, Any] = {}
        self._load_config()
        logger.info(
            f"PolicyRails loaded from {self._CONFIG_PATH} "
            f"(budget cap: ${self._cfg.get('budget_rails', {}).get('daily_spend_cap_usd', 5000)}, "
            f"blocked actions: {len(self._blocked_actions)})"
        )

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        """Load YAML config — falls back to hard-coded defaults on parse error."""
        try:
            import yaml  # pyyaml
            with open(self._CONFIG_PATH, "r", encoding="utf-8") as f:
                self._cfg = yaml.safe_load(f) or {}
            logger.info("rails_config.yaml loaded successfully.")
        except ImportError:
            logger.warning("pyyaml not installed — using default PolicyRails config.")
            self._cfg = {}
        except FileNotFoundError:
            logger.warning(f"rails_config.yaml not found at {self._CONFIG_PATH}. Using defaults.")
            self._cfg = {}
        except Exception as exc:
            logger.error(f"Error loading rails_config.yaml: {exc}. Using defaults.")
            self._cfg = {}

    @property
    def _budget(self) -> dict:
        return self._cfg.get("budget_rails", {})

    @property
    def _action_cfg(self) -> dict:
        return self._cfg.get("action_rails", {})

    @property
    def _output_cfg(self) -> dict:
        return self._cfg.get("output_rails", {})

    @property
    def _blocked_actions(self) -> list[str]:
        return self._action_cfg.get("blocked_actions", [
            "delete_all_nodes", "terminate_all_jobs", "revoke_all_tokens",
            "drop_database", "wipe_storage",
        ])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_action(
        self,
        agent: str,
        action: str,
        cost_usd: float = 0.0,
        confidence: float = 1.0,
        reasoning: str = "",
        payload: dict | None = None,
    ) -> None:
        """
        Run all policy checks for an agent action.

        Args:
            agent: Name of the calling agent.
            action: Action identifier string.
            cost_usd: Estimated USD cost.
            confidence: Agent's confidence score (0.0–1.0).
            reasoning: Human-readable reasoning text (scanned for flagged phrases).
            payload: Action parameters (logged but not checked by default).

        Raises:
            RailsViolation: If any policy check fails.
        """
        self._check_action_blocked(action)
        self._check_confidence(action, confidence)
        self._check_single_action_cost(action, cost_usd)
        self._check_reasoning_output(agent, action, reasoning)
        logger.debug(
            f"[PolicyRails] ✅ {agent}.{action} passed all rails "
            f"(cost=${cost_usd:.2f}, confidence={confidence:.2%})"
        )

    def check_reasoning_text(self, agent: str, text: str) -> list[str]:
        """
        Scan reasoning text for flagged phrases (output rail).

        Returns:
            List of flagged phrases found (empty if clean).
        """
        flagged_phrases = self._output_cfg.get("flagged_phrases", [
            "bypass guardrail", "ignore policy", "override safety", "disable monitoring",
        ])
        found = [p for p in flagged_phrases if p.lower() in text.lower()]
        if found:
            logger.warning(
                f"[PolicyRails] ⚠️  Output rail triggered for {agent}: "
                f"flagged phrases detected: {found}"
            )
        return found

    def mask_sensitive_fields(self, data: dict) -> dict:
        """
        Redact sensitive field values from a dict (for audit logging).

        Returns:
            A copy of data with sensitive values replaced by '***REDACTED***'.
        """
        sensitive = set(
            f.lower() for f in self._output_cfg.get("sensitive_fields_to_mask", [
                "api_key", "secret", "password", "token", "credit_card",
            ])
        )
        if not isinstance(data, dict):
            return data
        result = {}
        for k, v in data.items():
            if k.lower() in sensitive:
                result[k] = "***REDACTED***"
            elif isinstance(v, dict):
                result[k] = self.mask_sensitive_fields(v)
            else:
                result[k] = v
        return result

    def get_policy_summary(self) -> dict[str, Any]:
        """Return a human-readable summary of current policy settings."""
        return {
            "version": self._cfg.get("version", "1.0"),
            "budget_rails": {
                "auto_approve_threshold_usd": self._budget.get("auto_approve_threshold_usd", 100.0),
                "human_approval_threshold_usd": self._budget.get("human_approval_threshold_usd", 500.0),
                "daily_spend_cap_usd": self._budget.get("daily_spend_cap_usd", 5000.0),
                "single_action_max_usd": self._budget.get("single_action_max_usd", 1000.0),
            },
            "blocked_actions": self._blocked_actions,
            "confidence_requirements": self._action_cfg.get("confidence_requirements", {}),
            "max_scale_down_pct": self._action_cfg.get("max_scale_down_pct", 50),
        }

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    def _check_action_blocked(self, action: str) -> None:
        """Raise if action is on the permanent block list."""
        if action in self._blocked_actions:
            raise RailsViolation(
                "action_rail",
                f"Action '{action}' is permanently blocked by guardrail policy. "
                f"This action requires human operator override.",
            )

    def _check_confidence(self, action: str, confidence: float) -> None:
        """Raise if agent confidence is below the threshold for this action type."""
        thresholds: dict[str, float] = self._action_cfg.get("confidence_requirements", {
            "scale_down": 0.80,
            "migrate_job": 0.75,
            "terminate_job": 0.85,
            "replace_node": 0.90,
        })
        required = thresholds.get(action)
        if required is None:
            return  # No specific requirement for this action
        if confidence < required:
            raise RailsViolation(
                "action_rail",
                f"Action '{action}' requires confidence ≥ {required:.0%} "
                f"but agent reported {confidence:.0%}. Increase confidence before acting.",
            )

    def _check_single_action_cost(self, action: str, cost_usd: float) -> None:
        """Raise if a single action cost exceeds the per-action sanity cap."""
        max_single = float(self._budget.get("single_action_max_usd", 1000.0))
        # Apply env var override
        max_single = float(os.getenv("RAILS_SINGLE_ACTION_MAX_USD", max_single))
        if cost_usd > max_single:
            raise RailsViolation(
                "budget_rail",
                f"Action '{action}' estimated cost ${cost_usd:.2f} exceeds "
                f"single-action cap of ${max_single:.2f}. Split or seek approval.",
            )

    def _check_reasoning_output(self, agent: str, action: str, reasoning: str) -> None:
        """Raise if reasoning text contains policy-violating phrases."""
        found = self.check_reasoning_text(agent, reasoning)
        if found:
            raise RailsViolation(
                "output_rail",
                f"Agent '{agent}' reasoning for action '{action}' contains "
                f"flagged phrases: {found}. Review agent reasoning before proceeding.",
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_rails: PolicyRails | None = None


def get_rails() -> PolicyRails:
    """Return the global PolicyRails singleton."""
    global _rails
    if _rails is None:
        _rails = PolicyRails()
    return _rails
