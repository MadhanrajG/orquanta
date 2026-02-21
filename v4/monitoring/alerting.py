"""
OrQuanta Agentic v1.0 — Alert Manager

Multi-channel alerting:
- Slack webhooks (immediate)
- Email via SendGrid (async batch)
- PagerDuty (P1 incidents)

Features:
- Alert deduplication (same alert not resent within cooldown)
- Severity levels: INFO, WARNING, CRITICAL, P1
- Escalation: WARNING → CRITICAL → P1 → PagerDuty page
- Alert history and acknowledgment
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any

import httpx

logger = logging.getLogger("orquanta.monitoring.alerting")

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
PAGERDUTY_ROUTING_KEY = os.getenv("PAGERDUTY_ROUTING_KEY", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "alerts@orquanta.ai")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "ops@orquanta.ai")


class AlertSeverity(IntEnum):
    INFO = 1
    WARNING = 2
    CRITICAL = 3
    P1 = 4  # Page on-call engineer


SEVERITY_COLORS = {
    AlertSeverity.INFO: "#36a64f",      # Green
    AlertSeverity.WARNING: "#ff9900",   # Amber
    AlertSeverity.CRITICAL: "#ff0000",  # Red
    AlertSeverity.P1: "#800000",        # Dark red
}

SEVERITY_EMOJI = {
    AlertSeverity.INFO: "ℹ️",
    AlertSeverity.WARNING: "⚠️",
    AlertSeverity.CRITICAL: "🔴",
    AlertSeverity.P1: "🚨",
}


@dataclass
class Alert:
    """An alert event."""
    alert_id: str
    title: str
    message: str
    severity: AlertSeverity
    source: str              # e.g. "healing_agent", "cost_tracker"
    instance_id: str = ""
    job_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def dedup_key(self) -> str:
        """Hash key for deduplication."""
        return hashlib.md5(f"{self.source}:{self.title}:{self.instance_id}".encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "message": self.message,
            "severity": self.severity.name,
            "source": self.source,
            "instance_id": self.instance_id,
            "job_id": self.job_id,
            "acknowledged": self.acknowledged,
            "created_at": self.created_at,
        }


class AlertManager:
    """Sends, deduplicates, and tracks alerts across all channels.

    Usage:
        manager = AlertManager()
        await manager.send(Alert(
            alert_id="a-001",
            title="GPU Temperature Critical",
            message="Instance i-0123 GPU0 hit 87°C",
            severity=AlertSeverity.CRITICAL,
            source="gpu_telemetry",
            instance_id="i-0123",
        ))
    """

    # Cooldown: don't re-fire the same alert within this many seconds
    COOLDOWN: dict[AlertSeverity, int] = {
        AlertSeverity.INFO: 3600,
        AlertSeverity.WARNING: 900,
        AlertSeverity.CRITICAL: 300,
        AlertSeverity.P1: 60,
    }

    def __init__(self) -> None:
        self._history: list[Alert] = []
        self._last_fired: dict[str, float] = {}  # dedup_key → timestamp
        self._send_queue: asyncio.Queue[Alert] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start background alert sender."""
        self._task = asyncio.create_task(self._sender_loop())
        logger.info("[AlertManager] Started.")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def send(self, alert: Alert) -> bool:
        """Queue an alert for delivery (de-duplicated)."""
        key = alert.dedup_key()
        last = self._last_fired.get(key, 0)
        cooldown = self.COOLDOWN.get(alert.severity, 300)
        if time.time() - last < cooldown:
            logger.debug(f"[AlertManager] Suppressed (cooldown): {alert.title}")
            return False

        self._history.append(alert)
        self._last_fired[key] = time.time()
        await self._send_queue.put(alert)
        return True

    async def acknowledge(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged."""
        for a in self._history:
            if a.alert_id == alert_id:
                a.acknowledged = True
                return True
        return False

    def get_history(self, severity: AlertSeverity | None = None, limit: int = 100) -> list[dict[str, Any]]:
        alerts = self._history
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return [a.to_dict() for a in alerts[-limit:]]

    def get_open_alerts(self) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self._history if not a.acknowledged]

    # ------------------------------------------------------------------
    # Background sender
    # ------------------------------------------------------------------

    async def _sender_loop(self) -> None:
        """Process the alert queue."""
        while True:
            alert = await self._send_queue.get()
            tasks = [self._send_slack(alert)]
            if alert.severity >= AlertSeverity.CRITICAL:
                tasks.append(self._send_email(alert))
            if alert.severity >= AlertSeverity.P1:
                tasks.append(self._send_pagerduty(alert))
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # Slack
    # ------------------------------------------------------------------

    async def _send_slack(self, alert: Alert) -> None:
        if not SLACK_WEBHOOK_URL:
            logger.info(f"[AlertManager] Slack not configured. Alert: [{alert.severity.name}] {alert.title}")
            return

        emoji = SEVERITY_EMOJI.get(alert.severity, "⚠️")
        color = SEVERITY_COLORS.get(alert.severity, "#ff9900")
        payload = {
            "text": f"{emoji} *OrQuanta Platform Alert* — {alert.severity.name}",
            "attachments": [{
                "color": color,
                "title": alert.title,
                "text": alert.message,
                "fields": [
                    {"title": "Source", "value": alert.source, "short": True},
                    {"title": "Instance", "value": alert.instance_id or "—", "short": True},
                    {"title": "Job", "value": alert.job_id or "—", "short": True},
                    {"title": "Time", "value": alert.created_at, "short": True},
                ],
                "footer": "OrQuanta Agentic v1.0",
                "ts": int(time.time()),
            }],
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(SLACK_WEBHOOK_URL, json=payload)
                if resp.status_code != 200:
                    logger.warning(f"[AlertManager] Slack returned {resp.status_code}")
                else:
                    logger.info(f"[AlertManager] Slack alert sent: {alert.title}")
        except Exception as exc:
            logger.error(f"[AlertManager] Slack send failed: {exc}")

    # ------------------------------------------------------------------
    # Email (SendGrid)
    # ------------------------------------------------------------------

    async def _send_email(self, alert: Alert) -> None:
        if not SENDGRID_API_KEY:
            return

        html_body = f"""
        <h2>OrQuanta Platform Alert — {alert.severity.name}</h2>
        <h3>{alert.title}</h3>
        <p>{alert.message}</p>
        <table>
          <tr><td><strong>Source</strong></td><td>{alert.source}</td></tr>
          <tr><td><strong>Instance</strong></td><td>{alert.instance_id}</td></tr>
          <tr><td><strong>Job</strong></td><td>{alert.job_id}</td></tr>
          <tr><td><strong>Time</strong></td><td>{alert.created_at}</td></tr>
        </table>
        """

        payload = {
            "personalizations": [{"to": [{"email": ALERT_EMAIL_TO}]}],
            "from": {"email": ALERT_EMAIL_FROM, "name": "OrQuanta Platform"},
            "subject": f"[{alert.severity.name}] {alert.title}",
            "content": [{"type": "text/html", "value": html_body}],
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers={"Authorization": f"Bearer {SENDGRID_API_KEY}"},
                )
                if resp.status_code in (200, 202):
                    logger.info(f"[AlertManager] Email alert sent to {ALERT_EMAIL_TO}: {alert.title}")
        except Exception as exc:
            logger.error(f"[AlertManager] Email send failed: {exc}")

    # ------------------------------------------------------------------
    # PagerDuty
    # ------------------------------------------------------------------

    async def _send_pagerduty(self, alert: Alert) -> None:
        if not PAGERDUTY_ROUTING_KEY:
            return

        payload = {
            "routing_key": PAGERDUTY_ROUTING_KEY,
            "event_action": "trigger",
            "dedup_key": alert.dedup_key(),
            "payload": {
                "summary": alert.title,
                "severity": "critical" if alert.severity >= AlertSeverity.P1 else "error",
                "source": alert.source,
                "custom_details": {
                    "message": alert.message,
                    "instance_id": alert.instance_id,
                    "job_id": alert.job_id,
                    "platform": "OrQuanta Agentic v1.0",
                    **alert.metadata,
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json=payload,
                )
                if resp.status_code == 202:
                    logger.info(f"[AlertManager] PagerDuty triggered: {alert.title}")
                else:
                    logger.warning(f"[AlertManager] PagerDuty returned {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.error(f"[AlertManager] PagerDuty send failed: {exc}")


# Singleton
_manager: AlertManager | None = None

def get_alert_manager() -> AlertManager:
    global _manager
    if _manager is None:
        _manager = AlertManager()
    return _manager
