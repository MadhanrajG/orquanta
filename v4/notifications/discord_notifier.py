"""
OrQuanta — Discord Notifier (OpenClaw-inspired)

Sends rich embed notifications to Discord via:
  - Webhook URL (per-user, stored in prefs)
  - Bot DM (optional, requires DISCORD_BOT_TOKEN)

Events supported:
  - job_completed  → green embed with cost, savings, GPU details
  - job_failed     → red embed with reason + retry link
  - cost_alert     → yellow embed with spend gauge
  - job_started    → blue embed with estimated cost
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("orquanta.notifications.discord")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
APP_URL = os.getenv("APP_URL", "https://orquanta.com")


# ─── Embed colour constants ────────────────────────────────────────────────────
COLOUR = {
    "success": 0x00FF88,   # green
    "error":   0xFF4444,   # red
    "warning": 0xFFB800,   # amber
    "info":    0x00D4FF,   # cyan
}


class DiscordNotifier:
    """Sends rich Discord embeds for OrQuanta GPU job events."""

    @staticmethod
    async def send_via_webhook(webhook_url: str, event_type: str, data: dict[str, Any]) -> bool:
        """Fire a rich embed to a Discord channel webhook URL."""
        payload = DiscordNotifier._build_embed(event_type, data)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json=payload)
                if resp.status_code in (200, 204):
                    logger.info(f"[Discord] Sent {event_type} via webhook")
                    return True
                logger.warning(f"[Discord] Webhook returned {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as exc:
            logger.error(f"[Discord] Webhook failed: {exc}")
            return False

    @staticmethod
    async def send_dm(user_discord_id: str, event_type: str, data: dict[str, Any]) -> bool:
        """Send a DM to a Discord user via bot (requires DISCORD_BOT_TOKEN)."""
        if not DISCORD_BOT_TOKEN:
            logger.debug("[Discord] No DISCORD_BOT_TOKEN — DM skipped")
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Open DM channel
                dm_resp = await client.post(
                    "https://discord.com/api/v10/users/@me/channels",
                    headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"},
                    json={"recipient_id": user_discord_id},
                )
                if not dm_resp.is_success:
                    logger.warning(f"[Discord] DM channel create failed: {dm_resp.status_code}")
                    return False
                channel_id = dm_resp.json()["id"]

                # 2. Send message
                payload = DiscordNotifier._build_embed(event_type, data)
                msg_resp = await client.post(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"},
                    json=payload,
                )
                success = msg_resp.is_success
                logger.info(f"[Discord] DM to {user_discord_id}: {'sent' if success else 'failed'}")
                return success
        except Exception as exc:
            logger.error(f"[Discord] DM failed: {exc}")
            return False

    @staticmethod
    def _build_embed(event_type: str, data: dict[str, Any]) -> dict:
        """Build a rich Discord embed payload for an event."""
        builders = {
            "job_completed": DiscordNotifier._embed_job_completed,
            "job_failed":    DiscordNotifier._embed_job_failed,
            "job_started":   DiscordNotifier._embed_job_started,
            "cost_alert":    DiscordNotifier._embed_cost_alert,
        }
        builder = builders.get(event_type, DiscordNotifier._embed_generic)
        return builder(data)

    @staticmethod
    def _embed_job_completed(d: dict) -> dict:
        job_id   = d.get("job_id", "unknown")
        goal     = d.get("goal_summary", "GPU workload")[:80]
        gpu      = d.get("gpu_type", "GPU")
        provider = d.get("provider", "cloud")
        duration = d.get("duration_min", 0)
        cost     = d.get("cost_usd", 0)
        saved    = d.get("saved_usd", 0)
        return {
            "embeds": [{
                "title": "✅ GPU Job Completed",
                "description": f"**Goal:** {goal}",
                "color": COLOUR["success"],
                "fields": [
                    {"name": "🖥️ GPU", "value": f"{gpu} on {provider}", "inline": True},
                    {"name": "⏱️ Duration", "value": f"{duration:.1f} min", "inline": True},
                    {"name": "💰 Cost", "value": f"${cost:.2f}", "inline": True},
                    {"name": "💚 Saved vs AWS", "value": f"${saved:.2f}", "inline": True},
                    {"name": "📋 Job ID", "value": f"`{job_id}`", "inline": True},
                ],
                "url": f"{APP_URL}/app",
                "footer": {"text": "OrQuanta GPU Cloud"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
            "components": [{
                "type": 1,
                "components": [{
                    "type": 2, "style": 5, "label": "View in Dashboard",
                    "url": f"{APP_URL}/app",
                }],
            }],
        }

    @staticmethod
    def _embed_job_failed(d: dict) -> dict:
        job_id  = d.get("job_id", "unknown")
        reason  = d.get("reason", "Unknown error")[:120]
        goal    = d.get("goal_summary", "GPU workload")[:80]
        return {
            "embeds": [{
                "title": "❌ GPU Job Failed",
                "description": f"**Goal:** {goal}\n**Reason:** {reason}",
                "color": COLOUR["error"],
                "fields": [
                    {"name": "📋 Job ID", "value": f"`{job_id}`", "inline": True},
                    {"name": "🔄 Action", "value": "Retry from dashboard", "inline": True},
                ],
                "url": f"{APP_URL}/app",
                "footer": {"text": "OrQuanta GPU Cloud"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
            "components": [{
                "type": 1,
                "components": [
                    {"type": 2, "style": 5, "label": "🔄 Retry Job", "url": f"{APP_URL}/app"},
                    {"type": 2, "style": 5, "label": "📋 View Logs", "url": f"{APP_URL}/app"},
                ],
            }],
        }

    @staticmethod
    def _embed_job_started(d: dict) -> dict:
        job_id  = d.get("job_id", "unknown")
        goal    = d.get("goal_summary", "GPU workload")[:80]
        gpu     = d.get("gpu_type", "GPU")
        provider= d.get("provider", "cloud")
        est_cost= d.get("estimated_cost_usd", 0)
        return {
            "embeds": [{
                "title": "🚀 GPU Job Started",
                "description": f"**Goal:** {goal}",
                "color": COLOUR["info"],
                "fields": [
                    {"name": "🖥️ GPU", "value": f"{gpu} on {provider}", "inline": True},
                    {"name": "💰 Est. Cost", "value": f"~${est_cost:.2f}", "inline": True},
                    {"name": "📋 Job ID", "value": f"`{job_id}`", "inline": True},
                ],
                "url": f"{APP_URL}/app",
                "footer": {"text": "OrQuanta GPU Cloud · You'll get another message when done"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    @staticmethod
    def _embed_cost_alert(d: dict) -> dict:
        budget  = d.get("daily_budget_usd", 0)
        spent   = d.get("spent_usd", 0)
        pct     = d.get("threshold_pct", 80)
        pct_used = int((spent / budget * 100)) if budget > 0 else 0
        bar_filled = int(pct_used / 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        return {
            "embeds": [{
                "title": f"⚠️ Cost Alert — {pct_used}% of Daily Budget Used",
                "description": f"```\n[{bar}] {pct_used}%\n```\nSpent **${spent:.2f}** of **${budget:.2f}** daily budget",
                "color": COLOUR["warning"],
                "fields": [
                    {"name": "💰 Spent", "value": f"${spent:.2f}", "inline": True},
                    {"name": "🏦 Budget", "value": f"${budget:.2f}", "inline": True},
                    {"name": "🔔 Threshold", "value": f"{pct}%", "inline": True},
                ],
                "url": f"{APP_URL}/app",
                "footer": {"text": "OrQuanta GPU Cloud · Review your running jobs"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    @staticmethod
    def _embed_generic(d: dict) -> dict:
        return {
            "embeds": [{
                "title": "ℹ️ OrQuanta Notification",
                "description": str(d)[:300],
                "color": COLOUR["info"],
                "footer": {"text": "OrQuanta GPU Cloud"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }
