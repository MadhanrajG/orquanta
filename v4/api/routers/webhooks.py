"""
OrQuanta — Webhook Automation Router (OpenClaw-inspired)

Endpoints:
  POST   /api/v1/webhooks              Register a webhook
  GET    /api/v1/webhooks              List user webhooks
  DELETE /api/v1/webhooks/{id}         Remove a webhook
  POST   /api/v1/webhooks/{id}/test    Test-fire a webhook
  POST   /api/v1/webhooks/inbound/{token}  Inbound trigger (starts a job)
  GET    /api/v1/webhooks/{id}/deliveries  Delivery log

HMAC-SHA256 signed outbound payloads:
  Header: X-OrQuanta-Signature: sha256=<hex>
  Header: X-OrQuanta-Event: job_completed
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, HttpUrl

logger = logging.getLogger("orquanta.webhooks")

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

WEBHOOK_SIGNING_SECRET = os.getenv("WEBHOOK_SIGNING_SECRET", secrets.token_hex(32))
APP_URL = os.getenv("APP_URL", "https://orquanta.com")

# ─── In-memory store (replace with DB in production) ─────────────────────────
_webhooks: dict[str, dict] = {}       # id → webhook record
_inbound_tokens: dict[str, str] = {}  # token → user_id
_deliveries: dict[str, list] = {}     # webhook_id → [delivery records]


# ─── Schemas ─────────────────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = ["job_completed", "job_failed", "cost_alert"]
    description: str = ""
    secret: str = ""   # User-supplied secret for their own HMAC verification


class WebhookOut(BaseModel):
    id: str
    url: str
    events: list[str]
    description: str
    created_at: str
    last_delivery: str | None = None
    delivery_count: int = 0
    inbound_url: str


# ─── Auth dependency (reuse from app) ────────────────────────────────────────

def _get_current_user(request: Request) -> dict:
    """Simplified auth — in production uses the real JWT middleware."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    # For demo mode, accept any bearer token and return "admin"
    return {"user_id": "admin", "email": "admin@orquanta.com"}


CurrentUser = Annotated[dict, Depends(_get_current_user)]


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("", response_model=WebhookOut, status_code=201)
async def create_webhook(body: WebhookCreate, user: CurrentUser):
    """Register a new outbound webhook."""
    wid = f"wh-{secrets.token_hex(8)}"
    token = secrets.token_urlsafe(24)
    record = {
        "id": wid,
        "user_id": user["user_id"],
        "url": str(body.url),
        "events": body.events,
        "description": body.description,
        "secret": body.secret or WEBHOOK_SIGNING_SECRET,
        "inbound_token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_delivery": None,
        "delivery_count": 0,
    }
    _webhooks[wid] = record
    _inbound_tokens[token] = user["user_id"]
    _deliveries[wid] = []
    logger.info(f"[Webhooks] Registered {wid} → {body.url} for {user['user_id']}")
    return _to_out(record)


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(user: CurrentUser):
    """List all webhooks for the current user."""
    return [_to_out(w) for w in _webhooks.values() if w["user_id"] == user["user_id"]]


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: str, user: CurrentUser):
    """Remove a webhook."""
    hook = _webhooks.get(webhook_id)
    if not hook or hook["user_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Webhook not found")
    _inbound_tokens.pop(hook["inbound_token"], None)
    _webhooks.pop(webhook_id)
    _deliveries.pop(webhook_id, None)


@router.post("/{webhook_id}/test", status_code=200)
async def test_webhook(webhook_id: str, user: CurrentUser):
    """Test-fire a webhook with a sample job_completed event."""
    hook = _webhooks.get(webhook_id)
    if not hook or hook["user_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Webhook not found")

    test_payload = {
        "event": "job_completed",
        "job_id": "job-test-0000",
        "goal_summary": "Fine-tune LLaMA 3 8B on customer support data",
        "gpu_type": "A100 80GB",
        "provider": "Lambda Labs",
        "duration_min": 45.2,
        "cost_usd": 1.49,
        "saved_usd": 3.21,
        "ts": time.time(),
        "test": True,
    }
    success, status_code, resp_body = await _fire_webhook(hook, "job_completed", test_payload)
    return {
        "success": success,
        "http_status": status_code,
        "response": resp_body[:200] if resp_body else None,
    }


@router.get("/{webhook_id}/deliveries")
async def get_deliveries(webhook_id: str, user: CurrentUser):
    """Get delivery log for a webhook."""
    hook = _webhooks.get(webhook_id)
    if not hook or hook["user_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return _deliveries.get(webhook_id, [])[-50:]  # Last 50


@router.post("/inbound/{token}", status_code=202)
async def inbound_trigger(token: str, request: Request):
    """
    Inbound webhook — external systems POST here to trigger an OrQuanta job.

    Expected JSON body:
      { "goal": "Fine-tune LLaMA 3 8B...", "budget_usd": 50, "gpu_type": "A100" }

    Returns: { "job_id": "job-xxxx", "status": "queued" }
    """
    user_id = _inbound_tokens.get(token)
    if not user_id:
        raise HTTPException(status_code=403, detail="Invalid inbound token")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    goal = body.get("goal", "")
    if not goal:
        raise HTTPException(status_code=400, detail="'goal' field is required")

    # Create job via internal API (import here to avoid circular)
    job_id = f"job-{secrets.token_hex(6)}"
    logger.info(f"[Webhooks] Inbound trigger from {user_id}: {goal[:60]}")

    # In production: call the goal orchestration pipeline
    # from v4.agents.master_orchestrator import MasterOrchestrator
    # For now: queue a job record and return immediately
    return {
        "job_id": job_id,
        "status": "queued",
        "goal": goal[:120],
        "message": "Job queued — check dashboard for status",
        "dashboard_url": f"{APP_URL}/app",
    }


# ─── Internal: fire a webhook ────────────────────────────────────────────────

async def dispatch_event(event_type: str, data: dict[str, Any], user_id: str | None = None) -> None:
    """
    Fire all registered webhooks for an event.
    Called by agents after job completion/failure/cost alert.
    """
    targets = [
        w for w in _webhooks.values()
        if event_type in w["events"] and (user_id is None or w["user_id"] == user_id)
    ]
    for hook in targets:
        payload = {"event": event_type, "ts": time.time(), **data}
        await _fire_webhook(hook, event_type, payload)


async def _fire_webhook(
    hook: dict, event_type: str, payload: dict
) -> tuple[bool, int, str]:
    """Send a signed POST to a webhook URL. Returns (success, status_code, body)."""
    body = json.dumps(payload, default=str)
    sig  = _sign(body, hook["secret"])

    headers = {
        "Content-Type": "application/json",
        "X-OrQuanta-Signature": f"sha256={sig}",
        "X-OrQuanta-Event": event_type,
        "X-OrQuanta-Delivery": secrets.token_hex(8),
        "User-Agent": "OrQuanta-Webhook/1.0",
    }

    delivery = {
        "id": secrets.token_hex(6),
        "event": event_type,
        "url": hook["url"],
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "http_status": None,
        "response": None,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(hook["url"], content=body, headers=headers)
        success = resp.status_code < 400
        delivery["http_status"] = resp.status_code
        delivery["response"] = resp.text[:300]
        delivery["status"] = "success" if success else "failed"
    except Exception as exc:
        delivery["status"] = "error"
        delivery["response"] = str(exc)[:200]
        success = False

    # Record delivery
    wid = hook["id"]
    if wid in _deliveries:
        _deliveries[wid].append(delivery)
        if len(_deliveries[wid]) > 200:
            _deliveries[wid] = _deliveries[wid][-200:]

    # Update hook metadata
    hook["last_delivery"] = delivery["attempted_at"]
    hook["delivery_count"] = hook.get("delivery_count", 0) + 1

    logger.info(f"[Webhooks] {delivery['status']} → {hook['url']} ({delivery.get('http_status')})")
    return success, delivery.get("http_status") or 0, delivery.get("response") or ""


def _sign(body: str, secret: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def _to_out(w: dict) -> WebhookOut:
    return WebhookOut(
        id=w["id"],
        url=w["url"],
        events=w["events"],
        description=w.get("description", ""),
        created_at=w["created_at"],
        last_delivery=w.get("last_delivery"),
        delivery_count=w.get("delivery_count", 0),
        inbound_url=f"{APP_URL}/api/v1/webhooks/inbound/{w['inbound_token']}",
    )
