"""
OrQuanta  -  Stripe Billing API Router
=====================================
Handles:
  GET  /api/v1/billing/plans               -  Return available plans + pricing
  GET  /api/v1/billing/subscription        -  Get current user's subscription
  POST /api/v1/billing/checkout            -  Create Stripe checkout session
  POST /api/v1/billing/portal              -  Create customer portal session
  POST /api/v1/webhooks/stripe             -  Stripe webhook endpoint
  POST /api/v1/billing/subscribe           -  Subscribe to a plan (direct API)
  DELETE /api/v1/billing/subscription      -  Cancel subscription

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
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
APP_URL = os.getenv("APP_URL", "https://orquanta.com")


# -- Schemas --------------------------------------------------------------------

class SubscribeRequest(BaseModel):
    plan: str        # starter | pro | enterprise
    email: str
    org_name: Optional[str] = "My Organization"


class CheckoutRequest(BaseModel):
    plan: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


# -- Dependency: real JWT auth (shared with the rest of the API) ---------------
# FIXED: was a local mock that always returned a fake user and org_id.
# Now uses the same middleware as every other protected endpoint.
from ..middleware.auth import get_current_user  # noqa: E402


# -- Endpoints -----------------------------------------------------------------

@router.get("/plans")
async def get_plans():
    """Return available subscription plans and pricing."""
    try:
        from ...billing.stripe_integration import StripeBilling
        data = StripeBilling.get_pricing_page()
    except Exception:
        data = {}
    data["stripe_enabled"] = bool(STRIPE_SECRET_KEY)
    data["stripe_publishable_key"] = STRIPE_PUBLISHABLE_KEY
    return data


@router.get("/subscription")
async def get_subscription(
    current_user: dict = Depends(get_current_user),
):
    """Get the authenticated user's subscription status."""
    try:
        from ...billing.stripe_integration import get_billing
        # Use real user email as the stable org identifier
        org_id = current_user.get("sub") or current_user.get("email", "unknown")
        billing = get_billing()
        sub = await billing.get_subscription(org_id)
        if not sub:
            return {"status": "free", "plan": "free", "trial_days_remaining": 14}
        return sub.to_dict()
    except Exception as exc:
        logger.error(f"Get subscription error: {exc}")
        return {"status": "free", "plan": "free"}


@router.post("/checkout")
async def create_checkout_session(
    body: CheckoutRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a Stripe Checkout session for the authenticated user.
    Frontend redirects user to the Stripe-hosted checkout page.
    """
    if not STRIPE_SECRET_KEY:
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

        # Tag the session with the real user so the webhook can look them up
        user_email = current_user.get("email", "")
        user_id = current_user.get("sub", "")

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=user_email or None,
            line_items=[{"price": plan_info["price_id"], "quantity": 1}],
            subscription_data={"trial_period_days": 14},
            metadata={"user_id": user_id, "user_email": user_email},
            success_url=success + "&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel,
            allow_promotion_codes=True,
        )
        return {"checkout_url": session.url, "session_id": session.id}

    except Exception as exc:  # stripe.error.StripeError or import error
        logger.error(f"Stripe checkout error: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/portal")
async def create_portal_session(
    current_user: dict = Depends(get_current_user),
):
    """Create a Stripe Customer Portal session for the authenticated user."""
    if not STRIPE_SECRET_KEY:
        return {"portal_url": f"{APP_URL}/app/billing", "demo_mode": True}

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        user_email = current_user.get("email", "")
        # Look up Stripe customer by email
        customers = stripe.Customer.list(email=user_email, limit=1)
        if not customers.data:
            raise HTTPException(status_code=404, detail="No Stripe customer found for this account.")
        customer_id = customers.data[0].id

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{APP_URL}/app/billing",
        )
        return {"portal_url": session.url}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Portal session error: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/subscribe")
async def subscribe(
    body: SubscribeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Subscribe to a plan directly via API (for SDK/CLI users).
    Creates Stripe customer + subscription with 14-day trial.
    """
    try:
        from ...billing.stripe_integration import get_billing
        billing = get_billing()

        # Use authenticated user's real ID as the stable org identifier
        user_id = current_user.get("sub", "")
        user_email = current_user.get("email", body.email)
        org_id = f"org-{user_id}" if user_id else f"org-{hash(user_email) % 1000000}"

        customer_id = await billing.create_customer(org_id, user_email, body.org_name or "")
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
async def cancel_subscription(
    at_period_end: bool = True,
    current_user: dict = Depends(get_current_user),
):
    """Cancel the authenticated user's subscription."""
    try:
        from ...billing.stripe_integration import get_billing
        billing = get_billing()
        user_id = current_user.get("sub", "")
        user_email = current_user.get("email", "")
        org_id = f"org-{user_id}" if user_id else f"org-{hash(user_email) % 1000000}"
        ok = await billing.cancel_subscription(org_id, at_period_end)
        if ok:
            return {"success": True, "message": "Subscription cancelled successfully."}
        return {"success": False, "message": "No active subscription found."}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# -- Webhook -------------------------------------------------------------------

@webhook_router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    """
    Stripe webhook endpoint — signature-verified.
    Register at: https://dashboard.stripe.com/webhooks
    URL: https://orquanta.com/api/v1/webhooks/stripe
    Events: customer.subscription.*, invoice.paid, invoice.payment_failed
    Requires: STRIPE_WEBHOOK_SECRET env var (from Stripe dashboard).
    """
    payload = await request.body()

    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    # --- Signature verification (M1 security fix) ----------------------------
    # Without this check anyone can POST fake events to activate subscriptions.
    if STRIPE_WEBHOOK_SECRET:
        try:
            import stripe as _stripe
            _stripe.Webhook.construct_event(
                payload, stripe_signature, STRIPE_WEBHOOK_SECRET
            )
        except _stripe.error.SignatureVerificationError:
            logger.warning("[Webhook] Invalid Stripe signature — request rejected")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
        except Exception as exc:
            logger.error(f"[Webhook] Signature check error: {exc}")
            raise HTTPException(status_code=400, detail="Webhook verification failed")
    else:
        # In production, missing webhook secret is a hard failure.
        # Prevents attackers from posting fake subscription-activation events.
        is_production = os.getenv("ENVIRONMENT", "development").lower() in ("production", "prod")
        if is_production:
            logger.error(
                "[Webhook] CRITICAL: STRIPE_WEBHOOK_SECRET is not set in production. "
                "Rejecting webhook to prevent spoofed event processing."
            )
            raise HTTPException(
                status_code=500,
                detail="Webhook signature verification not configured. Contact support."
            )
        else:
            logger.warning(
                "[Webhook] STRIPE_WEBHOOK_SECRET not set — skipping signature check. "
                "Acceptable in development; MUST be set before production deployment."
            )
    # -------------------------------------------------------------------------

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
