"""
OrQuanta Agentic v1.0 — Billing API Router
==========================================

Exposes billing and subscription management endpoints:
  POST /billing/webhook          — Stripe webhook processor
  GET  /billing/plans            — Pricing page data
  GET  /billing/subscription     — Current user's subscription
  POST /billing/subscribe        — Start a subscription / trial
  POST /billing/upgrade          — Upgrade/downgrade plan
  DELETE /billing/subscription   — Cancel subscription
  GET  /billing/usage            — GPU hours usage this period
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..middleware.auth import get_current_user
from ...billing.stripe_integration import get_billing, PLANS, TRIAL_DAYS

logger = logging.getLogger("orquanta.routers.billing")
router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])


# ── Public: pricing page ──────────────────────────────────────────────────────

@router.get("/plans", summary="Get pricing plans (public)")
async def get_plans() -> dict[str, Any]:
    """Return all pricing plans for the landing/pricing page. No auth required."""
    return get_billing().get_pricing_page()


# ── Stripe webhook (raw body required) ───────────────────────────────────────

@router.post("/webhook", summary="Stripe webhook receiver", include_in_schema=False)
async def stripe_webhook(request: Request) -> dict[str, Any]:
    """
    Receives and processes all Stripe webhook events.
    Must be registered in Stripe Dashboard → Webhooks.
    Set STRIPE_WEBHOOK_SECRET in env.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        billing = get_billing()
        result = await billing.handle_webhook(payload, signature)
        return result
    except ValueError as exc:
        logger.warning(f"[Billing] Webhook signature invalid: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"[Billing] Webhook processing error: {exc}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


# ── Authenticated billing endpoints ──────────────────────────────────────────

@router.get("/subscription", summary="Get current subscription")
async def get_subscription(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return the current user's subscription status and plan details."""
    billing = get_billing()
    sub = await billing.get_subscription(user["sub"])
    if not sub:
        return {
            "status": "no_subscription",
            "trial_available": True,
            "trial_days": TRIAL_DAYS,
            "plans": list(PLANS.keys()),
        }
    return sub.to_dict()


@router.post("/subscribe", summary="Start a subscription or trial")
async def subscribe(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Create a new subscription for the current user.
    Body: {"plan": "starter" | "pro" | "enterprise", "name": "Org name"}
    """
    body = await request.json()
    plan = body.get("plan", "starter")
    org_name = body.get("name", user.get("name", "OrQuanta User"))

    if plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {plan}. Choose from {list(PLANS.keys())}")

    billing = get_billing()
    email = user.get("email", "")

    try:
        customer_id = await billing.create_customer(
            org_id=user["sub"],
            email=email,
            org_name=org_name,
        )
        cid, sub_id = await billing.create_subscription(
            org_id=user["sub"],
            customer_id=customer_id,
            plan=plan,
        )
        logger.info(f"[Billing] New subscription: user={email} plan={plan} sub={sub_id}")
        return {
            "subscription_id": sub_id,
            "customer_id": cid,
            "plan": plan,
            "status": "trialing",
            "trial_days": TRIAL_DAYS,
            "message": f"Your {TRIAL_DAYS}-day free trial has started!",
        }
    except Exception as exc:
        logger.error(f"[Billing] Subscribe failed for {email}: {exc}")
        raise HTTPException(status_code=500, detail=f"Subscription creation failed: {exc}")


@router.post("/upgrade", summary="Upgrade or downgrade plan")
async def upgrade_plan(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Change the user's subscription plan. Body: {"plan": "pro"}"""
    body = await request.json()
    new_plan = body.get("plan")
    if new_plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {new_plan}")

    billing = get_billing()
    ok = await billing.upgrade_plan(user["sub"], new_plan)
    if not ok:
        raise HTTPException(status_code=400, detail="No active subscription found or plan update failed")

    return {"plan": new_plan, "message": f"Plan upgraded to {new_plan}"}


@router.delete("/subscription", summary="Cancel subscription")
async def cancel_subscription(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Cancel at period end (no proration)."""
    billing = get_billing()
    ok = await billing.cancel_subscription(user["sub"], at_period_end=True)
    if not ok:
        raise HTTPException(status_code=404, detail="No active subscription found")
    return {"status": "cancelled", "message": "Subscription will cancel at the end of current period"}


@router.get("/usage", summary="Get GPU usage this billing period")
async def get_usage(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Return GPU hours consumed this billing period and estimated cost."""
    from ...execution.pipeline import get_pipeline
    pipeline = get_pipeline()
    stats = pipeline.get_stats()

    billing = get_billing()
    sub = await billing.get_subscription(user["sub"])
    plan_limit = None
    if sub:
        plan_info = PLANS.get(sub.plan, {})
        plan_limit = plan_info.get("gpu_spend_limit_usd_mo")

    return {
        "user_id": user["sub"],
        "total_jobs": stats["total"],
        "total_gpu_hours": stats["total_gpu_hours"],
        "total_cost_usd": stats["total_cost_usd"],
        "plan_spend_limit_usd": plan_limit,
        "jobs_by_status": stats["by_status"],
        "subscription": sub.to_dict() if sub else None,
    }
