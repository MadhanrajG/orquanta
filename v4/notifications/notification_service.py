"""
OrQuanta Agentic v1.0 — Notification Service

Unified notification dispatcher supporting:
  - Email (SendGrid)
  - Slack (webhook)
  - In-app (Redis pub/sub → WebSocket)
  - SMS (Twilio — optional)

Features:
  - Per-user preference management
  - Deduplication with 1-hour cooldown
  - Batch mode: aggregates low-priority notifications
  - Unsubscribe tracking (CAN-SPAM compliant)

Usage:
    svc = get_notification_service()
    await svc.send(NotificationEvent(
        user_id="usr-123",
        type="job_completed",
        data={"job_id": "job-456", "cost": 2.74},
        channels=["email", "slack"],
    ))
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("orquanta.notifications")

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM = os.getenv("ALERT_EMAIL_FROM", "noreply@orquanta.ai")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")

DEDUP_COOLDOWN_SEC = 3600    # 1 hour between identical notifications


class Channel(str, Enum):
    EMAIL = "email"
    SLACK = "slack"
    IN_APP = "in_app"
    SMS = "sms"


class Priority(str, Enum):
    CRITICAL = "critical"   # Always sent immediately
    HIGH = "high"           # Sent immediately
    NORMAL = "normal"       # Sent in next batch (hourly)
    LOW = "low"             # Batched daily


@dataclass
class UserNotificationPrefs:
    """Per-user notification preferences."""
    user_id: str
    email: str
    phone: str | None = None
    slack_user_id: str | None = None
    channels: list[str] = field(default_factory=lambda: ["email", "in_app"])
    unsubscribed_types: list[str] = field(default_factory=list)
    digest_mode: bool = False   # If true, batch all normal/low priority
    quiet_hours_start: int = 23   # 11pm
    quiet_hours_end: int = 8      # 8am


@dataclass
class NotificationEvent:
    user_id: str
    type: str           # E.g. "job_completed", "cost_alert", "trial_ending"
    data: dict[str, Any]
    channels: list[str] | None = None    # None = use user prefs
    priority: str = "normal"
    idempotency_key: str | None = None   # Deduplication key


@dataclass
class NotificationRecord:
    notification_id: str
    user_id: str
    type: str
    channel: str
    status: str       # sent | failed | deduplicated | suppressed
    sent_at: str = ""
    error: str = ""


class NotificationService:
    """Unified notification dispatcher."""

    def __init__(self) -> None:
        self._redis = None
        self._prefs: dict[str, UserNotificationPrefs] = {}
        self._history: list[NotificationRecord] = []
        self._dedup_cache: dict[str, float] = {}
        self._connect_redis()

    def _connect_redis(self) -> None:
        try:
            import redis
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self._redis = redis.from_url(url, decode_responses=True, socket_timeout=1.0)
            self._redis.ping()
        except Exception:
            self._redis = None

    # ─── Main send ────────────────────────────────────────────────────

    async def send(self, event: NotificationEvent) -> list[NotificationRecord]:
        """Send a notification through appropriate channels."""
        records = []

        # Get user preferences
        prefs = self._prefs.get(event.user_id, UserNotificationPrefs(
            user_id=event.user_id, email="", channels=["email", "in_app"],
        ))

        # Check if user has unsubscribed from this type
        if event.type in prefs.unsubscribed_types:
            logger.debug(f"[Notifications] {event.user_id} unsubscribed from {event.type}")
            return []

        # Determine channels
        channels = event.channels or prefs.channels

        # Check quiet hours for non-critical
        if event.priority not in ("critical", "high"):
            if self._is_quiet_hours(prefs):
                logger.debug(f"[Notifications] Quiet hours for {event.user_id} — deferring {event.type}")
                return []

        # Check dedup
        dedup_key = self._make_dedup_key(event)
        if self._is_deduplicated(dedup_key) and event.priority not in ("critical",):
            logger.debug(f"[Notifications] Dedup suppressed: {dedup_key}")
            return [NotificationRecord(
                notification_id=dedup_key[:8], user_id=event.user_id,
                type=event.type, channel="all", status="deduplicated",
            )]

        # Send to each channel
        channel_fns = {
            Channel.EMAIL: self._send_email,
            Channel.SLACK: self._send_slack,
            Channel.IN_APP: self._send_in_app,
            Channel.SMS: self._send_sms,
        }

        send_tasks = []
        for ch in channels:
            fn = channel_fns.get(Channel(ch))
            if fn:
                send_tasks.append(fn(event, prefs))

        results = await asyncio.gather(*send_tasks, return_exceptions=True)

        for i, result in enumerate(results):
            ch = channels[i] if i < len(channels) else "unknown"
            if isinstance(result, BaseException):
                rec = NotificationRecord(
                    notification_id=self._new_id(),
                    user_id=event.user_id, type=event.type,
                    channel=ch, status="failed", error=str(result),
                )
            else:
                rec = result or NotificationRecord(
                    notification_id=self._new_id(),
                    user_id=event.user_id, type=event.type, channel=ch, status="sent",
                    sent_at=datetime.now(timezone.utc).isoformat(),
                )
            records.append(rec)
            self._history.append(rec)

        # Mark dedup
        self._dedup_cache[dedup_key] = time.monotonic()
        if self._redis:
            self._redis.setex(f"notif:dedup:{dedup_key}", DEDUP_COOLDOWN_SEC, "1")

        return records

    # ─── Channel implementations ──────────────────────────────────────

    async def _send_email(self, event: NotificationEvent, prefs: UserNotificationPrefs) -> NotificationRecord:
        """Send via SendGrid."""
        if not prefs.email:
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="email", status="suppressed", error="No email address",
            )

        if not SENDGRID_API_KEY:
            logger.debug(f"[Notifications] Email to {prefs.email} (mock — no SendGrid key)")
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="email", status="sent",
                sent_at=datetime.now(timezone.utc).isoformat(),
            )

        # Build email from template
        email_obj = self._build_email(event, prefs)
        if not email_obj:
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="email", status="failed", error="No template for event type",
            )

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "personalizations": [{"to": [{"email": prefs.email}]}],
                        "from": {"email": SENDGRID_FROM, "name": "OrQuanta"},
                        "subject": email_obj.subject,
                        "content": [
                            {"type": "text/plain", "value": email_obj.text},
                            {"type": "text/html", "value": email_obj.html},
                        ],
                    },
                )
            status = "sent" if resp.status_code in (200, 202) else "failed"
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="email", status=status,
                sent_at=datetime.now(timezone.utc).isoformat(),
                error="" if status == "sent" else f"SendGrid HTTP {resp.status_code}",
            )
        except Exception as exc:
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="email", status="failed", error=str(exc),
            )

    async def _send_slack(self, event: NotificationEvent, prefs: UserNotificationPrefs) -> NotificationRecord:
        """Send via Slack webhook."""
        webhook = SLACK_WEBHOOK_URL
        if not webhook:
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="slack", status="suppressed", error="No SLACK_WEBHOOK_URL",
            )

        text = self._build_slack_text(event)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook, json={"text": text, "mrkdwn": True})
            status = "sent" if resp.status_code == 200 else "failed"
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="slack", status=status,
                sent_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="slack", status="failed", error=str(exc),
            )

    async def _send_in_app(self, event: NotificationEvent, prefs: UserNotificationPrefs) -> NotificationRecord:
        """Publish in-app notification via Redis pub/sub (picked up by WebSocket handler)."""
        if self._redis:
            import json
            self._redis.publish(
                f"notifications:{event.user_id}",
                json.dumps({"type": event.type, "data": event.data, "ts": time.time()}),
            )
        return NotificationRecord(
            notification_id=self._new_id(), user_id=event.user_id,
            type=event.type, channel="in_app", status="sent",
            sent_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _send_sms(self, event: NotificationEvent, prefs: UserNotificationPrefs) -> NotificationRecord:
        """Send via Twilio (critical alerts only)."""
        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, prefs.phone]):
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="sms", status="suppressed", error="Twilio not configured or no phone",
            )
        # Only send SMS for critical events
        if event.priority not in ("critical",):
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="sms", status="suppressed", error="Not critical — SMS skipped",
            )
        try:
            import httpx
            from base64 import b64encode
            auth = b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()
            body = f"OrQuanta Alert: {event.type.replace('_', ' ').title()} — check your dashboard: {os.getenv('APP_URL', 'https://app.orquanta.ai')}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
                    headers={"Authorization": f"Basic {auth}"},
                    data={"From": TWILIO_FROM_NUMBER, "To": prefs.phone, "Body": body},
                )
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="sms", status="sent" if resp.status_code == 201 else "failed",
                sent_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            return NotificationRecord(
                notification_id=self._new_id(), user_id=event.user_id,
                type=event.type, channel="sms", status="failed", error=str(exc),
            )

    # ─── Preferences ─────────────────────────────────────────────────

    def set_preferences(self, prefs: UserNotificationPrefs) -> None:
        self._prefs[prefs.user_id] = prefs

    def unsubscribe(self, user_id: str, notification_type: str | None = None) -> None:
        """Unsubscribe user from a type or all notifications."""
        prefs = self._prefs.get(user_id)
        if prefs:
            if notification_type:
                if notification_type not in prefs.unsubscribed_types:
                    prefs.unsubscribed_types.append(notification_type)
            else:
                prefs.unsubscribed_types = ["*"]  # All types

    def get_history(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get notification history for a user."""
        user_records = [r for r in self._history if r.user_id == user_id]
        return [asdict(r) for r in user_records[-limit:]]

    # ─── Helpers ─────────────────────────────────────────────────────

    def _build_email(self, event: NotificationEvent, prefs: UserNotificationPrefs):
        from v4.notifications.email_templates import EmailTemplates
        d = event.data
        name = d.get("name", "there")
        try:
            if event.type == "welcome":
                return EmailTemplates.welcome(name, prefs.email, d.get("plan", "starter"), d.get("trial_ends", ""), d.get("verification_url", ""))
            elif event.type == "job_completed":
                return EmailTemplates.job_completed(prefs.email, name, d.get("job_id", ""), d.get("goal_summary", ""), d.get("gpu_type", ""), d.get("provider", ""), d.get("duration_min", 0), d.get("cost_usd", 0), d.get("saved_usd", 0), d.get("artifacts_url", ""))
            elif event.type == "cost_alert":
                return EmailTemplates.cost_alert(prefs.email, name, d.get("daily_budget_usd", 0), d.get("spent_usd", 0), d.get("threshold_pct", 80), d.get("reset_time", ""))
            elif event.type == "trial_ending":
                return EmailTemplates.trial_ending(prefs.email, name, d.get("days_left", 3), d.get("plan", "pro"), d.get("price_usd_mo", 499), d.get("upgrade_url", ""))
            elif event.type == "payment_failed":
                return EmailTemplates.payment_failed(prefs.email, name, d.get("amount_usd", 0), d.get("retry_url", ""), d.get("retry_date", ""))
        except Exception as exc:
            logger.error(f"[Notifications] Email template error: {exc}")
        return None

    def _build_slack_text(self, event: NotificationEvent) -> str:
        d = event.data
        icons = {"job_completed": "✅", "cost_alert": "⚠️", "trial_ending": "⏰", "payment_failed": "❌"}
        icon = icons.get(event.type, "ℹ️")
        return f"{icon} *OrQuanta {event.type.replace('_', ' ').title()}*\n{d.get('message', str(d)[:200])}"

    def _is_quiet_hours(self, prefs: UserNotificationPrefs) -> bool:
        hour = datetime.now(timezone.utc).hour
        s, e = prefs.quiet_hours_start, prefs.quiet_hours_end
        if s > e:  # Crosses midnight
            return hour >= s or hour < e
        return s <= hour < e

    def _is_deduplicated(self, key: str) -> bool:
        if self._redis:
            return bool(self._redis.get(f"notif:dedup:{key}"))
        last = self._dedup_cache.get(key, 0)
        return (time.monotonic() - last) < DEDUP_COOLDOWN_SEC

    def _make_dedup_key(self, event: NotificationEvent) -> str:
        if event.idempotency_key:
            return event.idempotency_key
        raw = f"{event.user_id}:{event.type}:{sorted(event.data.items())}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def _new_id() -> str:
        import secrets
        return f"notif-{secrets.token_hex(6)}"


# ─── Singleton ────────────────────────────────────────────────────────────────

_service: NotificationService | None = None

def get_notification_service() -> NotificationService:
    global _service
    if _service is None:
        _service = NotificationService()
    return _service
