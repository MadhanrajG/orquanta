"""
OrQuanta Agentic v1.0 — Production Environment Validator
=========================================================

Runs at startup to validate all required env vars and dependencies.
Prevents silent failures by making missing config explicit.

Levels:
  CRITICAL — app cannot function, raises SystemExit
  WARNING  — degraded mode, logged but app starts
  INFO     — optional feature not configured
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("orquanta.startup")


@dataclass
class EnvCheck:
    key: str
    level: str           # critical / warning / info
    description: str
    default: str | None = None
    secret: bool = False


# All environment variables OrQuanta uses
ENV_SPEC: list[EnvCheck] = [
    # ── Security (CRITICAL) ───────────────────────────────────────────────
    EnvCheck("JWT_SECRET",            "critical", "JWT signing secret — set to 256-bit random string", secret=True),
    EnvCheck("ADMIN_EMAIL",           "critical", "Admin user email", default="admin@orquanta.ai"),
    EnvCheck("ADMIN_PASSWORD",        "critical", "Admin user password", secret=True, default="orquanta-admin-2024"),

    # ── GPU Providers (WARNING — at least one needed for real jobs) ───────
    EnvCheck("RUNPOD_API_KEY",        "warning",  "RunPod API key — cheapest GPU, H100@$2.49/hr", secret=True),
    EnvCheck("LAMBDA_LABS_API_KEY",   "info",     "Lambda Labs API key — backup GPU provider", secret=True),
    EnvCheck("AWS_ACCESS_KEY_ID",     "info",     "AWS IAM key for EC2 GPU instances", secret=True),

    # ── LLM (WARNING — agents need this) ─────────────────────────────────
    EnvCheck("OPENAI_API_KEY",        "warning",  "OpenAI API key for agent reasoning", secret=True),
    EnvCheck("LLM_PROVIDER",          "info",     "LLM backend (mock|openai|anthropic)", default="mock"),

    # ── Billing (INFO — required before going live with payments) ─────────
    EnvCheck("STRIPE_SECRET_KEY",     "info",     "Stripe secret key for subscriptions & billing", secret=True),
    EnvCheck("STRIPE_WEBHOOK_SECRET", "info",     "Stripe webhook endpoint secret", secret=True),

    # ── Infrastructure (INFO) ────────────────────────────────────────────
    EnvCheck("DATABASE_URL",          "info",     "PostgreSQL URI (defaults to SQLite if not set)"),
    EnvCheck("REDIS_URL",             "info",     "Redis for caching and task queues"),

    # ── Notifications ────────────────────────────────────────────────────
    EnvCheck("SLACK_WEBHOOK_URL",     "info",     "Slack webhook for alerts"),

    # ── App config ───────────────────────────────────────────────────────
    EnvCheck("CORS_ORIGINS",          "info",     "Allowed CORS origins (CSV)", default="*"),
    EnvCheck("PORT",                  "info",     "HTTP server port", default="8000"),
    EnvCheck("ENV",                   "info",     "Environment (development|production)", default="production"),
]


def validate_env(strict: bool = False) -> dict[str, Any]:
    """
    Validate all environment variables at startup.
    
    Args:
        strict: If True, treat WARNING-level missing vars as CRITICAL.
    
    Returns a report dict with counts by level.
    Raises SystemExit on CRITICAL failures (unless in DEMO_MODE).
    """
    demo_mode = os.getenv("ORQUANTA_DEMO_MODE", "false").lower() in ("true", "1")
    criticals: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []
    configured: list[str] = []

    for check in ENV_SPEC:
        val = os.getenv(check.key, check.default or "")
        if val:
            display = f"{'***' if check.secret else val[:20]}"
            configured.append(f"  ✅ {check.key:<40} = {display}")
        else:
            msg = f"  {'❌' if check.level == 'critical' else '⚠️' if check.level == 'warning' else 'ℹ️'} {check.key:<40} — {check.description}"
            if check.level == "critical":
                criticals.append(msg)
            elif check.level == "warning":
                warnings.append(msg)
            else:
                infos.append(msg)

    # Log the report
    logger.info("=" * 60)
    logger.info("OrQuanta Production Environment Check")
    logger.info("=" * 60)
    for line in configured:
        logger.info(line)
    for line in warnings:
        logger.warning(line)
    for line in infos:
        logger.info(line)
    for line in criticals:
        logger.critical(line)

    # Provider capability check
    has_any_provider = any([
        os.getenv("RUNPOD_API_KEY"),
        os.getenv("LAMBDA_LABS_API_KEY"),
        os.getenv("AWS_ACCESS_KEY_ID"),
        os.getenv("GCP_PROJECT_ID"),
        os.getenv("AZURE_SUBSCRIPTION_ID"),
    ])

    use_real = os.getenv("USE_REAL_PROVIDERS", "false").lower() == "true"

    if use_real and not has_any_provider:
        logger.critical("  ❌ USE_REAL_PROVIDERS=true but NO provider API keys set!")
        criticals.append("no_providers")
    elif not has_any_provider and not demo_mode:
        logger.warning("  ⚠️  No provider API keys set — running in MOCK mode")
        logger.warning("     Set RUNPOD_API_KEY to enable real GPU provisioning")
    elif has_any_provider:
        providers = []
        if os.getenv("RUNPOD_API_KEY"): providers.append("RunPod ✅")
        if os.getenv("LAMBDA_LABS_API_KEY"): providers.append("Lambda Labs ✅")
        if os.getenv("AWS_ACCESS_KEY_ID"): providers.append("AWS ✅")
        logger.info(f"  🚀 Active providers: {', '.join(providers)}")

    # Summary
    logger.info("=" * 60)
    logger.info(
        f"Config: {len(configured)} set | "
        f"{len(warnings)} warnings | "
        f"{len(infos)} optional missing | "
        f"{len(criticals)} critical"
    )

    if criticals and not demo_mode:
        if strict or any("JWT_SECRET" in c for c in criticals):
            logger.critical("STARTUP ABORTED: Critical config missing. Set required env vars.")
            sys.exit(1)
        else:
            logger.warning("Critical config missing — starting in degraded mode (demo/dev only)")

    logger.info("=" * 60)

    return {
        "configured": len(configured),
        "warnings": len(warnings),
        "criticals": len(criticals),
        "has_real_providers": has_any_provider,
        "stripe_configured": bool(os.getenv("STRIPE_SECRET_KEY")),
        "llm_configured": bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),
        "demo_mode": demo_mode,
    }


def get_production_readiness() -> dict[str, Any]:
    """Return a production-readiness scorecard for the /health endpoint."""
    checks = {
        "jwt_secret":     bool(os.getenv("JWT_SECRET")),
        "runpod":         bool(os.getenv("RUNPOD_API_KEY")),
        "llm":            bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),
        "stripe":         bool(os.getenv("STRIPE_SECRET_KEY")),
        "database":       bool(os.getenv("DATABASE_URL")),
        "redis":          bool(os.getenv("REDIS_URL")),
    }
    score = sum(1 for v in checks.values() if v)
    total = len(checks)
    return {
        "score": score,
        "total": total,
        "pct": round(score / total * 100),
        "ready": score >= 4,       # JWT + RunPod + LLM + Stripe = minimum viable
        "checks": checks,
        "verdict": (
            "🟢 Production Ready" if score >= 5 else
            "🟡 Dev/Demo Mode" if score >= 3 else
            "🔴 Not Configured"
        ),
    }
