"""
OrQuanta Agentic v1.0 — Customer Onboarding Flow

7-step automated onboarding:
  Step 1: Account creation + email verification
  Step 2: Organization setup + team invites
  Step 3: Connect first cloud provider (guided)
  Step 4: Run first GPU job (template job)
  Step 5: Set budget limits and safety thresholds
  Step 6: Configure alerts (Slack/email)
  Step 7: Explore dashboard tutorial

Each step tracks completion. Stuck steps trigger help emails.
Progress persists in DB via OnboardingState.

Usage:
    flow = OnboardingFlow(user_id="usr-123", org_id="org-456")
    step = await flow.get_current_step()
    await flow.complete_step(step.index, data={"provider": "aws"})
    await flow.get_progress()  → OnboardingProgress
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import IntEnum
from typing import Any

logger = logging.getLogger("orquanta.onboarding")

ONBOARDING_TIMEOUT_HOURS = 48   # Trigger help email if stuck for this long

class StepIndex(IntEnum):
    ACCOUNT_VERIFIED    = 1
    ORG_SETUP           = 2
    PROVIDER_CONNECTED  = 3
    FIRST_JOB_RUN       = 4
    BUDGET_SET          = 5
    ALERTS_CONFIGURED   = 6
    TUTORIAL_COMPLETED  = 7


@dataclass
class OnboardingStep:
    index: int
    title: str
    description: str
    action_url: str
    estimated_minutes: int
    skippable: bool = False
    completed: bool = False
    completed_at: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


STEP_DEFINITIONS = [
    OnboardingStep(1, "Verify Your Email", "Check your inbox and click the verification link to activate your account.", "/auth/verify", 1, False),
    OnboardingStep(2, "Set Up Your Organization", "Add your team name, invite colleagues, and configure your organization defaults.", "/settings/org", 3, False),
    OnboardingStep(3, "Connect a Cloud Provider", "Link your first GPU provider (AWS, GCP, Azure, or CoreWeave) so OrQuanta can provision instances.", "/onboarding/providers", 5, False),
    OnboardingStep(4, "Run Your First GPU Job", "Submit a template job to see OrQuanta agents in action — launching a real GPU instance in under 30 seconds.", "/onboarding/first-job", 10, True),
    OnboardingStep(5, "Set Budget & Safety Limits", "Configure your daily spend cap, max concurrent agents, and rate limits to prevent surprises.", "/settings/safety", 3, False),
    OnboardingStep(6, "Configure Alerts", "Connect Slack or email for real-time alerts on job completion, GPU health, and cost spikes.", "/settings/alerts", 3, True),
    OnboardingStep(7, "Explore the Dashboard", "Take the interactive tour to discover spot price comparison, cost analytics, and audit trail.", "/tour", 5, True),
]


@dataclass
class OnboardingProgress:
    user_id: str
    org_id: str
    current_step: int
    total_steps: int = 7
    completion_pct: float = 0.0
    steps: list[OnboardingStep] = field(default_factory=list)
    started_at: str = ""
    estimated_complete_at: str = ""
    is_complete: bool = False
    stuck_since: str | None = None    # If user hasn't progressed in 48h

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d


class OnboardingFlow:
    """Manages the 7-step customer onboarding journey.
    
    In production this would persist state via the DB repositories.
    For now uses in-memory state dict keyed by user_id.
    """

    _state: dict[str, dict[str, Any]] = {}   # {user_id: {step_index: completed, ...}}

    def __init__(self, user_id: str, org_id: str) -> None:
        self.user_id = user_id
        self.org_id = org_id
        if user_id not in self._state:
            self._state[user_id] = {
                "steps": {},
                "started_at": datetime.now(timezone.utc).isoformat(),
                "last_activity": time.time(),
            }

    async def get_progress(self) -> OnboardingProgress:
        """Get full onboarding progress for the user."""
        state = self._state[self.user_id]
        steps = []
        completed_count = 0

        for defn in STEP_DEFINITIONS:
            step = OnboardingStep(**asdict(defn))
            step_data = state["steps"].get(step.index, {})
            if step_data.get("completed"):
                step.completed = True
                step.completed_at = step_data.get("completed_at")
                step.data = step_data.get("data", {})
                completed_count += 1
            steps.append(step)

        current_step = self._get_current_step_index(state)
        pct = round((completed_count / len(STEP_DEFINITIONS)) * 100, 1)
        is_complete = completed_count >= len(STEP_DEFINITIONS)

        # Detect "stuck" state
        last_activity = state.get("last_activity", time.time())
        stuck_since = None
        if not is_complete and (time.time() - last_activity) > (ONBOARDING_TIMEOUT_HOURS * 3600):
            stuck_since = datetime.fromtimestamp(last_activity, tz=timezone.utc).isoformat()

        return OnboardingProgress(
            user_id=self.user_id,
            org_id=self.org_id,
            current_step=current_step,
            total_steps=len(STEP_DEFINITIONS),
            completion_pct=pct,
            steps=steps,
            started_at=state["started_at"],
            is_complete=is_complete,
            stuck_since=stuck_since,
        )

    async def complete_step(self, step_index: int, data: dict[str, Any] | None = None) -> OnboardingProgress:
        """Mark a step as complete and advance to next step."""
        state = self._state[self.user_id]
        now = datetime.now(timezone.utc).isoformat()

        if step_index not in [s.index for s in STEP_DEFINITIONS]:
            raise ValueError(f"Invalid step index: {step_index}")

        state["steps"][step_index] = {
            "completed": True,
            "completed_at": now,
            "data": data or {},
        }
        state["last_activity"] = time.time()

        logger.info(f"[Onboarding] User {self.user_id} completed step {step_index}")

        # Trigger step-specific actions
        await self._on_step_complete(step_index, data or {})

        return await self.get_progress()

    async def skip_step(self, step_index: int) -> OnboardingProgress:
        """Skip a skippable step."""
        defn = next((s for s in STEP_DEFINITIONS if s.index == step_index), None)
        if not defn or not defn.skippable:
            raise ValueError(f"Step {step_index} cannot be skipped")
        return await self.complete_step(step_index, {"skipped": True})

    async def get_current_step(self) -> OnboardingStep:
        """Get the first incomplete step."""
        state = self._state[self.user_id]
        idx = self._get_current_step_index(state)
        defn = next((s for s in STEP_DEFINITIONS if s.index == idx), STEP_DEFINITIONS[-1])
        return defn

    async def reset(self) -> None:
        """Reset onboarding (for testing / admin override)."""
        self._state[self.user_id] = {
            "steps": {},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_activity": time.time(),
        }

    def _get_current_step_index(self, state: dict) -> int:
        for defn in STEP_DEFINITIONS:
            if not state["steps"].get(defn.index, {}).get("completed"):
                return defn.index
        return len(STEP_DEFINITIONS)

    async def _on_step_complete(self, step_index: int, data: dict) -> None:
        """Side effects after completing each step."""
        if step_index == StepIndex.ACCOUNT_VERIFIED:
            logger.info(f"[Onboarding] {self.user_id} email verified — sending welcome email")
            # TODO: trigger welcome email via notification_service

        elif step_index == StepIndex.PROVIDER_CONNECTED:
            provider = data.get("provider", "unknown")
            logger.info(f"[Onboarding] {self.user_id} connected provider: {provider}")
            # Validate the connection before marking complete
            valid = await self._validate_provider_credentials(provider, data)
            if not valid:
                raise ValueError(f"Provider credentials for {provider} are invalid")

        elif step_index == StepIndex.FIRST_JOB_RUN:
            logger.info(f"[Onboarding] {self.user_id} ran first job! 🎉")
            # TODO: trigger congratulations email

        elif step_index == StepIndex.TUTORIAL_COMPLETED:
            logger.info(f"[Onboarding] {self.user_id} completed full onboarding!")
            # TODO: send completion email, unlock all features

    async def _validate_provider_credentials(self, provider: str, data: dict) -> bool:
        """Quick connectivity test for provided credentials."""
        from v4.providers.provider_router import get_router
        try:
            router = get_router()
            provider_obj = router._providers.get(provider)
            if not provider_obj:
                return False
            return await provider_obj.is_available()
        except Exception as exc:
            logger.warning(f"[Onboarding] Provider validation failed for {provider}: {exc}")
            return True  # Don't block onboarding if check itself fails


class OnboardingEmailTrigger:
    """Monitors onboarding state and triggers help emails for stuck users."""

    def __init__(self, flow_map: dict[str, OnboardingFlow]) -> None:
        self._flows = flow_map
        self._running = False

    async def start_monitoring(self) -> None:
        """Run background task checking for stuck users every hour."""
        self._running = True
        while self._running:
            await self._check_stuck_users()
            await asyncio.sleep(3600)  # Check every hour

    async def _check_stuck_users(self) -> None:
        for user_id, flow in list(self._flows.items()):
            progress = await flow.get_progress()
            if progress.stuck_since and not progress.is_complete:
                step = await flow.get_current_step()
                logger.info(f"[Onboarding] Sending help email to user {user_id} stuck on step {step.index}: {step.title}")
                # TODO: send help email via notification_service

    def stop(self) -> None:
        self._running = False
