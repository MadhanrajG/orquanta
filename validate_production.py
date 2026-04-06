#!/usr/bin/env python3
"""
OrQuanta Production Readiness Validator
========================================
Run before deployment to verify all required environment variables
and services are configured correctly.

Usage:
    python validate_production.py
    python validate_production.py --strict   # Fail on any warning

Exit codes:
    0 = All required config present (production ready)
    1 = Missing critical config
    2 = Warnings only (deploy with caution)
"""
from __future__ import annotations

import os
import sys
import json
from datetime import datetime


def check(name: str, value: str | None, required: bool = True, hint: str = "") -> tuple[bool, str]:
    """Return (ok, message) for a single config check."""
    if value and value.strip():
        return True, f"✅ {name}"
    level = "❌ REQUIRED" if required else "⚠️  OPTIONAL"
    msg = f"{level} {name} — {hint}" if hint else f"{level} {name}"
    return False, msg


def validate() -> dict:
    results = []
    errors = 0
    warnings = 0

    # ── Core secrets ──────────────────────────────────────────────────────────
    ok, msg = check("JWT_SECRET_KEY", os.getenv("JWT_SECRET_KEY"), required=True,
                    hint="Generate: python -c \"import secrets; print(secrets.token_hex(32))\"")
    results.append(msg); errors += 0 if ok else 1

    ok, msg = check("ADMIN_PASSWORD", os.getenv("ADMIN_PASSWORD"), required=True,
                    hint="Set in Railway environment variables")
    results.append(msg); errors += 0 if ok else 1

    # ── Database ──────────────────────────────────────────────────────────────
    db_url = os.getenv("DATABASE_URL", "")
    ok = bool(db_url and "postgresql" in db_url)
    msg = f"✅ DATABASE_URL (PostgreSQL)" if ok else f"❌ REQUIRED DATABASE_URL — must be PostgreSQL for production"
    results.append(msg); errors += 0 if ok else 1

    # ── GPU Providers (at least one required) ─────────────────────────────────
    runpod_key = os.getenv("RUNPOD_API_KEY", "")
    lambda_key = os.getenv("LAMBDA_LABS_API_KEY", "")
    has_provider = bool(runpod_key or lambda_key)

    ok, msg = check("RUNPOD_API_KEY", runpod_key, required=False,
                    hint="Get from https://www.runpod.io/console/user/settings")
    results.append(msg); warnings += 0 if ok else 1

    ok, msg = check("LAMBDA_LABS_API_KEY", lambda_key, required=False,
                    hint="Get from https://cloud.lambdalabs.com/api-keys")
    results.append(msg); warnings += 0 if ok else 1

    if not has_provider:
        results.append("❌ REQUIRED: At least one GPU provider key (RUNPOD_API_KEY or LAMBDA_LABS_API_KEY)")
        errors += 1

    # ── LLM for AI reasoning ───────────────────────────────────────────────────
    ok, msg = check("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY"), required=False,
                    hint="Enables real LLM reasoning. Without it, agents use rule-based fallback.")
    results.append(msg); warnings += 0 if ok else 1

    ok, msg = check("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY"), required=False,
                    hint="Alternative LLM provider (Claude)")
    results.append(msg); warnings += 0 if ok else 1

    # ── Payments ───────────────────────────────────────────────────────────────
    ok, msg = check("STRIPE_SECRET_KEY", os.getenv("STRIPE_SECRET_KEY"), required=False,
                    hint="Required for billing. Get from https://dashboard.stripe.com/apikeys")
    results.append(msg); warnings += 0 if ok else 1

    ok, msg = check("STRIPE_WEBHOOK_SECRET", os.getenv("STRIPE_WEBHOOK_SECRET"), required=False,
                    hint="Required for Stripe webhooks. Set in Stripe Dashboard.")
    results.append(msg); warnings += 0 if ok else 1

    # ── Notifications ──────────────────────────────────────────────────────────
    ok, msg = check("SENDGRID_API_KEY", os.getenv("SENDGRID_API_KEY"), required=False,
                    hint="Enables email alerts and weekly digests")
    results.append(msg); warnings += 0 if ok else 1

    ok, msg = check("SLACK_WEBHOOK_URL", os.getenv("SLACK_WEBHOOK_URL"), required=False,
                    hint="Enables Slack alerts for critical events")
    results.append(msg); warnings += 0 if ok else 1

    # ── Ports / URLs ──────────────────────────────────────────────────────────
    port = os.getenv("PORT", "8000")
    results.append(f"✅ PORT={port}")

    cors = os.getenv("CORS_ORIGINS", "")
    if cors and cors != "*":
        results.append(f"✅ CORS_ORIGINS configured")
    else:
        results.append(f"⚠️  CORS_ORIGINS=* (restrict for production)")
        warnings += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    readiness_score = 100 - (errors * 20) - (warnings * 5)
    readiness_score = max(0, readiness_score)

    if errors == 0:
        verdict = "🚀 PRODUCTION READY"
    elif errors <= 1 and has_provider:
        verdict = "⚠️  DEPLOY WITH CAUTION"
    else:
        verdict = "❌ NOT PRODUCTION READY"

    return {
        "checks": results,
        "errors": errors,
        "warnings": warnings,
        "readiness_score": readiness_score,
        "verdict": verdict,
        "timestamp": datetime.utcnow().isoformat(),
        "has_real_providers": has_provider,
        "stripe_configured": bool(os.getenv("STRIPE_SECRET_KEY")),
        "llm_configured": bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),
    }


if __name__ == "__main__":
    strict = "--strict" in sys.argv
    report = validate()

    print("\n" + "="*60)
    print("  OrQuanta Production Readiness Check")
    print("="*60)
    for line in report["checks"]:
        print(f"  {line}")
    print("="*60)
    print(f"\n  Score: {report['readiness_score']}/100")
    print(f"  Errors: {report['errors']} | Warnings: {report['warnings']}")
    print(f"\n  {report['verdict']}\n")

    if report["errors"] > 0:
        sys.exit(1)
    elif report["warnings"] > 0 and strict:
        sys.exit(2)
    else:
        sys.exit(0)
