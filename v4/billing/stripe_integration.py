"""
OrQuanta Agentic v1.0 — Stripe Billing Integration

Handles:
- Subscription creation (Starter/Pro/Enterprise)
- Usage-based metering (GPU-hours managed per month)
- Webhook processing (payment events, trial expiry)
- Invoice generation
- Trial period management (14 days free)

Plans:
  Starter  — $99/mo  — up to $5K/mo GPU spend managed, 2 agents
  Pro      — $499/mo — up to $30K/mo GPU spend managed, 10 agents
  Enterprise — Custom  — unlimited, dedicated support, SLA

Requires env vars:
  STRIPE_SECRET_KEY
  STRIPE_WEBHOOK_SECRET
  STRIPE_STARTER_PRICE_ID
  STRIPE_PRO_PRICE_ID
  STRIPE_USAGE_METER_ID
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("orquanta.billing.stripe")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_STARTER_PRICE_ID = os.getenv("STRIPE_STARTER_PRICE_ID", "")
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "")
STRIPE_USAGE_METER_ID = os.getenv("STRIPE_USAGE_METER_ID", "")
STRIPE_API_BASE = "https://api.stripe.com/v1"
TRIAL_DAYS = 14

PLANS = {
    "starter": {
        "name": "Starter",
        "price_usd_mo": 99,
        "gpu_spend_limit_usd_mo": 5000,
        "max_agents": 2,
        "price_id": STRIPE_STARTER_PRICE_ID,
        "features": [
            "Up to $5K/mo GPU spend automated",
            "2 concurrent agents",
            "AWS + GCP providers",
            "Email alerts",
            "14-day free trial",
        ],
    },
    "pro": {
        "name": "Pro",
        "price_usd_mo": 499,
        "gpu_spend_limit_usd_mo": 30000,
        "max_agents": 10,
        "price_id": STRIPE_PRO_PRICE_ID,
        "features": [
            "Up to $30K/mo GPU spend automated",
            "10 concurrent agents",
            "All 4 cloud providers",
            "Slack + PagerDuty alerts",
            "Cost analytics dashboard",
            "Priority support",
            "14-day free trial",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "price_usd_mo": None,  # Custom pricing
        "gpu_spend_limit_usd_mo": None,
        "max_agents": None,
        "features": [
            "Unlimited GPU spend management",
            "Unlimited agents",
            "All providers + CoreWeave",
            "SAML SSO",
            "99.9% SLA",
            "Dedicated Slack channel",
            "Custom integrations",
        ],
    },
}


@dataclass
class SubscriptionInfo:
    """Active subscription details for an organization."""
    org_id: str
    stripe_customer_id: str
    stripe_subscription_id: str
    plan: str
    status: str               # active / trialing / past_due / canceled
    trial_end: str | None
    current_period_end: str
    cancel_at_period_end: bool = False
    gpu_spend_managed_usd: float = 0.0  # This billing period
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "org_id": self.org_id,
            "plan": self.plan,
            "status": self.status,
            "trial_end": self.trial_end,
            "current_period_end": self.current_period_end,
            "cancel_at_period_end": self.cancel_at_period_end,
            "gpu_spend_managed_usd": round(self.gpu_spend_managed_usd, 2),
        }


class StripeClient:
    """Async Stripe API client using httpx."""

    def __init__(self) -> None:
        if not STRIPE_SECRET_KEY:
            logger.warning("[Stripe] STRIPE_SECRET_KEY not configured — billing disabled")
        self._key = STRIPE_SECRET_KEY

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "Stripe-Version": "2024-11-20",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    async def _post(self, path: str, data: dict) -> dict[str, Any]:
        """POST to Stripe API."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{STRIPE_API_BASE}{path}",
                data=data,
                headers=self._headers(),
            )
            body = resp.json()
            if resp.status_code >= 400:
                raise StripeError(f"Stripe API error {resp.status_code}: {body.get('error', {}).get('message', body)}")
            return body

    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """GET from Stripe API."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{STRIPE_API_BASE}{path}",
                params=params or {},
                headers=self._headers(),
            )
            body = resp.json()
            if resp.status_code >= 400:
                raise StripeError(f"Stripe API error {resp.status_code}: {body.get('error', {}).get('message', body)}")
            return body

    async def _delete(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(f"{STRIPE_API_BASE}{path}", headers=self._headers())
            return resp.json()


class StripeBilling:
    """High-level billing operations for OrQuanta.

    Usage:
        billing = StripeBilling()
        customer_id, sub_id = await billing.create_subscription("org-123", "ops@acme.com", "pro")
        await billing.record_gpu_usage("org-123", customer_id, gpu_hours=12.5)
    """

    def __init__(self) -> None:
        self._client = StripeClient()
        # In-memory subscription cache (replace with DB in production)
        self._subscriptions: dict[str, SubscriptionInfo] = {}

    async def create_customer(self, org_id: str, email: str, org_name: str) -> str:
        """Create or retrieve a Stripe customer. Returns customer_id."""
        if not STRIPE_SECRET_KEY:
            return f"cus_mock_{org_id}"

        try:
            # Check if customer already exists
            result = await self._client._get("/customers/search", {
                "query": f"metadata['org_id']:'{org_id}'"
            })
            customers = result.get("data", [])
            if customers:
                cid = customers[0]["id"]
                logger.info(f"[Stripe] Found existing customer {cid} for org {org_id}")
                return cid

            # Create new customer
            customer = await self._client._post("/customers", {
                "email": email,
                "name": org_name,
                "metadata[org_id]": org_id,
                "metadata[platform]": "orquanta-v4",
            })
            cid = customer["id"]
            logger.info(f"[Stripe] Created customer {cid} for org {org_id}")
            return cid
        except StripeError as exc:
            logger.error(f"[Stripe] Create customer failed: {exc}")
            return f"cus_mock_{org_id}"

    async def create_subscription(
        self,
        org_id: str,
        customer_id: str,
        plan: str,
    ) -> tuple[str, str]:
        """Create a subscription with trial. Returns (customer_id, subscription_id)."""
        if not STRIPE_SECRET_KEY:
            sub_id = f"sub_mock_{org_id}"
            self._subscriptions[org_id] = SubscriptionInfo(
                org_id=org_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                plan=plan,
                status="trialing",
                trial_end=None,
                current_period_end="",
            )
            logger.info(f"[Stripe] Mock subscription {sub_id} for org {org_id} ({plan})")
            return customer_id, sub_id

        plan_info = PLANS.get(plan)
        if not plan_info or not plan_info.get("price_id"):
            raise ValueError(f"Unknown or unconfigured plan: {plan}")

        try:
            sub = await self._client._post("/subscriptions", {
                "customer": customer_id,
                f"items[0][price]": plan_info["price_id"],
                "trial_period_days": TRIAL_DAYS,
                "metadata[org_id]": org_id,
                "metadata[plan]": plan,
                "payment_behavior": "default_incomplete",
                "expand[]": "latest_invoice.payment_intent",
            })

            sub_id = sub["id"]
            trial_end = sub.get("trial_end")
            period_end = sub.get("current_period_end", "")

            info = SubscriptionInfo(
                org_id=org_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                plan=plan,
                status=sub.get("status", "trialing"),
                trial_end=datetime.fromtimestamp(trial_end, tz=timezone.utc).isoformat() if trial_end else None,
                current_period_end=datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat() if period_end else "",
            )
            self._subscriptions[org_id] = info

            logger.info(f"[Stripe] Created subscription {sub_id} for org {org_id} — plan={plan}")
            return customer_id, sub_id

        except StripeError as exc:
            logger.error(f"[Stripe] Create subscription failed: {exc}")
            raise

    async def record_gpu_usage(
        self,
        org_id: str,
        customer_id: str,
        gpu_hours: float,
        description: str = "",
    ) -> None:
        """Report GPU hours usage to Stripe metered billing.
        
        This lets us add usage-based charges on top of the base subscription
        if the customer exceeds their plan's GPU spend allowance.
        """
        if not STRIPE_SECRET_KEY or not STRIPE_USAGE_METER_ID:
            logger.debug(f"[Stripe] Mock usage record: {gpu_hours:.2f} GPU-hours for org {org_id}")
            return

        try:
            await self._client._post("/billing/meter_events", {
                "event_name": "gpu_hours",
                "payload[stripe_customer_id]": customer_id,
                "payload[value]": str(int(gpu_hours * 100)),  # in centi-hours for precision
                "payload[org_id]": org_id,
                "timestamp": str(int(time.time())),
                "identifier": f"usage-{org_id}-{int(time.time())}",
            })
            logger.info(f"[Stripe] Recorded {gpu_hours:.2f} GPU-hours for {org_id}")
        except StripeError as exc:
            logger.error(f"[Stripe] Usage record failed: {exc}")

    async def cancel_subscription(self, org_id: str, at_period_end: bool = True) -> bool:
        """Cancel a subscription (immediately or at period end)."""
        info = self._subscriptions.get(org_id)
        if not info:
            return False

        if not STRIPE_SECRET_KEY:
            info.status = "canceled"
            info.cancel_at_period_end = at_period_end
            return True

        try:
            if at_period_end:
                await self._client._post(
                    f"/subscriptions/{info.stripe_subscription_id}",
                    {"cancel_at_period_end": "true"}
                )
                info.cancel_at_period_end = True
            else:
                await self._client._delete(f"/subscriptions/{info.stripe_subscription_id}")
                info.status = "canceled"
            logger.info(f"[Stripe] Cancelled subscription for org {org_id} (period_end={at_period_end})")
            return True
        except StripeError as exc:
            logger.error(f"[Stripe] Cancel subscription failed: {exc}")
            return False

    async def upgrade_plan(self, org_id: str, new_plan: str) -> bool:
        """Upgrade/downgrade subscription to a new plan."""
        info = self._subscriptions.get(org_id)
        if not info:
            return False

        plan_info = PLANS.get(new_plan)
        if not plan_info or not plan_info.get("price_id"):
            return False

        if not STRIPE_SECRET_KEY:
            info.plan = new_plan
            return True

        try:
            # Get current subscription items
            sub = await self._client._get(f"/subscriptions/{info.stripe_subscription_id}")
            item_id = sub["items"]["data"][0]["id"]

            # Update the price
            await self._client._post(f"/subscriptions/{info.stripe_subscription_id}", {
                f"items[0][id]": item_id,
                f"items[0][price]": plan_info["price_id"],
                "proration_behavior": "always_invoice",
                "metadata[plan]": new_plan,
            })
            info.plan = new_plan
            logger.info(f"[Stripe] Upgraded org {org_id} to {new_plan}")
            return True
        except StripeError as exc:
            logger.error(f"[Stripe] Plan upgrade failed: {exc}")
            return False

    async def get_subscription(self, org_id: str) -> SubscriptionInfo | None:
        """Get current subscription info."""
        return self._subscriptions.get(org_id)

    async def handle_webhook(self, payload: bytes, signature: str) -> dict[str, Any]:
        """Process Stripe webhook event.
        
        Must be called from the /billing/webhook endpoint with raw request body.
        """
        if not STRIPE_SECRET_KEY:
            return {"received": True, "mock": True}

        try:
            import stripe
            event = stripe.Webhook.construct_event(
                payload, signature, STRIPE_WEBHOOK_SECRET
            )
        except Exception as exc:
            raise ValueError(f"Webhook signature verification failed: {exc}")

        event_type = event["type"]
        event_data = event["data"]["object"]

        logger.info(f"[Stripe] Webhook: {event_type}")

        if event_type == "customer.subscription.updated":
            org_id = event_data.get("metadata", {}).get("org_id")
            if org_id and org_id in self._subscriptions:
                self._subscriptions[org_id].status = event_data["status"]

        elif event_type == "customer.subscription.deleted":
            org_id = event_data.get("metadata", {}).get("org_id")
            if org_id and org_id in self._subscriptions:
                self._subscriptions[org_id].status = "canceled"

        elif event_type == "invoice.payment_failed":
            org_id = event_data.get("metadata", {}).get("org_id")
            cus_id = event_data.get("customer", "")
            logger.warning(f"[Stripe] Payment failed for customer {cus_id} (org={org_id})")
            # TODO: Notify org admins, pause non-critical workloads

        elif event_type == "invoice.paid":
            logger.info(f"[Stripe] Invoice paid: {event_data.get('id')}")

        elif event_type == "customer.subscription.trial_will_end":
            org_id = event_data.get("metadata", {}).get("org_id")
            logger.info(f"[Stripe] Trial ending in 3 days for org {org_id}")
            # TODO: Send trial ending email

        return {"received": True, "event_type": event_type}

    @staticmethod
    def get_pricing_page() -> dict[str, Any]:
        """Return pricing data for the landing page."""
        return {
            "plans": [
                {**PLANS[p], "id": p}
                for p in ["starter", "pro", "enterprise"]
            ],
            "trial_days": TRIAL_DAYS,
            "note": "All plans include a 14-day free trial. No credit card required until trial ends.",
        }


class StripeError(Exception):
    """Stripe API error."""


# Singleton
_billing: StripeBilling | None = None

def get_billing() -> StripeBilling:
    global _billing
    if _billing is None:
        _billing = StripeBilling()
    return _billing
