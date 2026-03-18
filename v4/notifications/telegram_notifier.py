"""
OrQuanta — Telegram Notifier (OpenClaw-inspired)

Sends job event notifications to Telegram via Bot API.
Users add their Telegram chat_id to their profile.

Setup:
  1. Create bot via @BotFather → get TELEGRAM_BOT_TOKEN
  2. User starts your bot and runs /start → gets their chat_id
  3. User enters chat_id in OrQuanta profile settings

Events: job_completed, job_failed, job_started, cost_alert
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("orquanta.notifications.telegram")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
APP_URL = os.getenv("APP_URL", "https://orquanta-production.up.railway.app")
TELEGRAM_API = "https://api.telegram.org"


class TelegramNotifier:
    """Sends job event messages to Telegram via Bot API."""

    @staticmethod
    async def send(chat_id: str, event_type: str, data: dict[str, Any]) -> bool:
        """Send an event notification to a Telegram chat ID."""
        if not TELEGRAM_BOT_TOKEN:
            logger.debug("[Telegram] No TELEGRAM_BOT_TOKEN configured")
            return False
        if not chat_id:
            return False

        message, reply_markup = TelegramNotifier._build_message(event_type, data)
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{TELEGRAM_API}/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json=payload,
                )
                if resp.status_code == 200:
                    logger.info(f"[Telegram] Sent {event_type} to {chat_id}")
                    return True
                logger.warning(f"[Telegram] API returned {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as exc:
            logger.error(f"[Telegram] Send failed: {exc}")
            return False

    @staticmethod
    def _build_message(event_type: str, data: dict[str, Any]) -> tuple[str, dict | None]:
        """Build MarkdownV2 message and optional inline keyboard."""
        builders = {
            "job_completed": TelegramNotifier._msg_job_completed,
            "job_failed":    TelegramNotifier._msg_job_failed,
            "job_started":   TelegramNotifier._msg_job_started,
            "cost_alert":    TelegramNotifier._msg_cost_alert,
        }
        builder = builders.get(event_type, TelegramNotifier._msg_generic)
        return builder(data)

    @staticmethod
    def _escape(text: str) -> str:
        """Escape special chars for MarkdownV2."""
        specials = r"\_*[]()~`>#+-=|{}.!"
        return "".join(f"\\{c}" if c in specials else c for c in str(text))

    @staticmethod
    def _msg_job_completed(d: dict) -> tuple[str, dict | None]:
        e   = TelegramNotifier._escape
        job = e(d.get("job_id", "?")[:8])
        goal= e(d.get("goal_summary", "GPU workload")[:60])
        gpu = e(d.get("gpu_type", "GPU"))
        prov= e(d.get("provider", "cloud"))
        dur = e(f"{d.get('duration_min', 0):.1f}")
        cost= e(f"${d.get('cost_usd', 0):.2f}")
        saved=e(f"${d.get('saved_usd', 0):.2f}")
        msg = (
            f"✅ *GPU Job Completed*\n\n"
            f"📋 `{job}` \| {goal}\n\n"
            f"🖥️ *GPU:* {gpu} on {prov}\n"
            f"⏱️ *Duration:* {dur} min\n"
            f"💰 *Cost:* {cost}\n"
            f"💚 *Saved vs AWS:* {saved}\n"
        )
        keyboard = {
            "inline_keyboard": [[
                {"text": "📊 View Dashboard", "url": f"{APP_URL}/app"},
            ]],
        }
        return msg, keyboard

    @staticmethod
    def _msg_job_failed(d: dict) -> tuple[str, dict | None]:
        e      = TelegramNotifier._escape
        job    = e(d.get("job_id", "?")[:8])
        goal   = e(d.get("goal_summary", "GPU workload")[:60])
        reason = e(d.get("reason", "Unknown error")[:100])
        msg = (
            f"❌ *GPU Job Failed*\n\n"
            f"📋 `{job}` \| {goal}\n\n"
            f"⚠️ *Reason:* {reason}\n"
        )
        keyboard = {
            "inline_keyboard": [[
                {"text": "🔄 Retry", "url": f"{APP_URL}/app"},
                {"text": "📋 View Logs", "url": f"{APP_URL}/app"},
            ]],
        }
        return msg, keyboard

    @staticmethod
    def _msg_job_started(d: dict) -> tuple[str, dict | None]:
        e    = TelegramNotifier._escape
        job  = e(d.get("job_id", "?")[:8])
        goal = e(d.get("goal_summary", "GPU workload")[:60])
        gpu  = e(d.get("gpu_type", "GPU"))
        prov = e(d.get("provider", "cloud"))
        est  = e(f"~${d.get('estimated_cost_usd', 0):.2f}")
        msg = (
            f"🚀 *GPU Job Started*\n\n"
            f"📋 `{job}` \| {goal}\n\n"
            f"🖥️ *GPU:* {gpu} on {prov}\n"
            f"💰 *Est\\. Cost:* {est}\n\n"
            f"_You'll get a message when it completes_"
        )
        return msg, None

    @staticmethod
    def _msg_cost_alert(d: dict) -> tuple[str, dict | None]:
        e      = TelegramNotifier._escape
        budget = d.get("daily_budget_usd", 0)
        spent  = d.get("spent_usd", 0)
        pct    = int(spent / budget * 100) if budget > 0 else 0
        bar_f  = int(pct / 10)
        bar    = "█" * bar_f + "░" * (10 - bar_f)
        msg = (
            f"⚠️ *Cost Alert — {e(pct)}% of Daily Budget*\n\n"
            f"`\[{e(bar)}\] {e(pct)}%`\n\n"
            f"💰 Spent: *{e(f'${spent:.2f}')}* of *{e(f'${budget:.2f}')}*\n"
        )
        keyboard = {
            "inline_keyboard": [[
                {"text": "📊 Review Jobs", "url": f"{APP_URL}/app"},
            ]],
        }
        return msg, keyboard

    @staticmethod
    def _msg_generic(d: dict) -> tuple[str, dict | None]:
        return f"ℹ️ *OrQuanta Alert*\n\n{TelegramNotifier._escape(str(d)[:200])}", None
