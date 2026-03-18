"""
OrQuanta — Stripe Billing API Router
=====================================
Handles:
  GET  /api/v1/billing/plans              — Return available plans + pricing
  GET  /api/v1/billing/subscription       — Get current user's subscription
  POST /api/v1/billing/checkout           — Create Stripe checkout session
  POST /api/v1/billing/portal             — Create customer portal session
  POST /api/v1/webhooks/stripe            — Stripe webhook endpoint
  POST /api/v1/billing/subscribe          — Subscribe to a plan (direct API)
  DELETE /api/v1/billing/subscription     — Cancel subscription

These endpoints are already mounted in v4/api/main.py under the /api/v1/billing prefix.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("orquanta.api.billing")

router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])
webhook_router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
APP_URL = os.getenv("APP_URL", "https://orquanta.ai")


# ── Schemas ────────────────────────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    plan: str        # starter | pro | enterprise
    email: str
    org_name: Optional[str] = "My Organization"


class CheckoutRequest(BaseModel):
    plan: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


# ── Dependency: get current user (simplified, uses JWT from main.py auth) ─────

async def get_current_user(request: Request) -> dict:
    """Extract user info from JWT. Re-uses the main auth middleware."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    # The actual JWT decode is in v4/api/security.py — mock for now
    return {"user_id": "user-from-jwt", "org_id": "org-from-jwt", "email": "user@example.com"}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/plans")
async def get_plans():
    """Return available subscription plans and pricing."""
    from ...billing.stripe_integration import StripeBilling
    return StripeBilling.get_pricing_page()


@router.get("/subscription")
async def get_subscription(request: Request):
    """Get the current user's subscription status."""
    try:
        from ...billing.stripe_integration import get_billing
        # Extract org_id from JWT (simplified)
        auth_header = request.headers.get("Authorization", "")
        org_id = "demo-org"  # In production: decode JWT

        billing = get_billing()
        sub = await billing.get_subscription(org_id)
        if not sub:
            return {"status": "free", "plan": "free", "trial_days_remaining": 14}
        return sub.to_dict()
    except Exception as exc:
        logger.error(f"Get subscription error: {exc}")
        return {"status": "free", "plan": "free"}


@router.post("/checkout")
async def create_checkout_session(body: CheckoutRequest, request: Request):
    """
    Create a Stripe Checkout session.
    Frontend redirects user to the Stripe-hosted checkout page.
    """
    if not STRIPE_SECRET_KEY:
        # Return mock checkout URL for demo mode
        return {
            "checkout_url": f"{APP_URL}/app/billing?mock=true&plan={body.plan}",
            "session_id": f"cs_mock_{body.plan}",
            "demo_mode": True,
        }

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        from ...billing.stripe_integration import PLANS
        plan_info = PLANS.get(body.plan)
        if not plan_info or not plan_info.get("price_id"):
            raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan}")

        success = body.success_url or f"{APP_URL}/app/billing?success=true"
        cancel = body.cancel_url or f"{APP_URL}/app/billing?cancelled=true"

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{
                "price": plan_info["price_id"],
                "quantity": 1,
            }],
            subscription_data={"trial_period_days": 14},
            success_url=success + "&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel,
            allow_promotion_codes=True,
        )
        return {"checkout_url": session.url, "session_id": session.id}

    except stripe.error.StripeError as exc:
        logger.error(f"Stripe checkout error: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/portal")
async def create_portal_session(request: Request):
    """Create a Stripe Customer Portal session for managing subscription."""
    if not STRIPE_SECRET_KEY:
        return {
            "portal_url": f"{APP_URL}/app/billing",
            "demo_mode": True,
        }

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        # Get customer_id from DB (simplified)
        customer_id = "cus_placeholder"  # In production: query DB

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{APP_URL}/app/billing",
        )
        return {"portal_url": session.url}

    except Exception as exc:
        logger.error(f"Portal session error: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/subscribe")
async def subscribe(body: SubscribeRequest, request: Request):
    """
    Subscribe to a plan directly via API (for SDK/CLI users).
    Creates Stripe customer + subscription with 14-day trial.
    """
    try:
        from ...billing.stripe_integration import get_billing
        billing = get_billing()

        org_id = f"org-{hash(body.email) % 1000000}"
        customer_id = await billing.create_customer(org_id, body.email, body.org_name or "")
        cust_id, sub_id = await billing.create_subscription(org_id, customer_id, body.plan)

        return {
            "success": True,
            "org_id": org_id,
            "customer_id": cust_id,
            "subscription_id": sub_id,
            "plan": body.plan,
            "trial_days": 14,
            "message": f"Subscribed to {body.plan} plan with 14-day free trial",
        }
    except Exception as exc:
        logger.error(f"Subscribe error: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/subscription")
async def cancel_subscription(request: Request, at_period_end: bool = True):
    """Cancel the current subscription."""
    try:
        from ...billing.stripe_integration import get_billing
        billing = get_billing()
        org_id = "demo-org"  # In production: from JWT
        ok = await billing.cancel_subscription(org_id, at_period_end)
        if ok:
            return {"success": True, "message": "Subscription cancelled"}
        return {"success": False, "message": "No active subscription found"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Webhook ───────────────────────────────────────────────────────────────────

@webhook_router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    """
    Stripe webhook endpoint.
    Must be registered at: https://dashboard.stripe.com/webhooks
    URL: https://your-railway-url.up.railway.app/api/v1/webhooks/stripe
    Events: customer.subscription.*, invoice.paid, invoice.payment_failed
    """
    payload = await request.body()

    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        from ...billing.stripe_integration import get_billing
        billing = get_billing()
        result = await billing.handle_webhook(payload, stripe_signature)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Webhook processing error: {exc}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")
