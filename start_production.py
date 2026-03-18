#!/usr/bin/env python3
"""
OrQuanta — Railway Production Startup Script
==============================================
This is the SINGLE entrypoint for Railway deployment.
Handles:
  1. Database initialization (first boot)
  2. Admin user seeding
  3. Environment validation
  4. Launches uvicorn

Usage (Railway sets this as start command):
  python start_production.py

Or direct:
  python start_production.py --port 8000 --workers 2
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import argparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("orquanta.startup")


async def initialize_database():
    """Create tables and seed admin user if needed."""
    logger.info("🗄️  Initializing database...")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "v4"))
        from v4.database.models import engine, Base, AsyncSessionLocal
        from sqlalchemy import text

        # Test connection
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection OK")

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables ready")

        # Seed admin if not exists
        await seed_admin(AsyncSessionLocal)

    except Exception as exc:
        logger.error(f"❌ Database init failed: {exc}")
        db_url = os.getenv("DATABASE_URL", "NOT SET")
        if "postgresql" not in db_url and "sqlite" not in db_url:
            logger.warning("DATABASE_URL not set — running without persistence (demo mode)")
        else:
            logger.warning(f"DB URL prefix: {db_url[:30]}...")


async def seed_admin(AsyncSessionLocal):
    """Seed admin user if ADMIN_PASSWORD is set and user doesn't exist."""
    admin_email = os.getenv("ADMIN_EMAIL", "admin@orquanta.ai")
    admin_password = os.getenv("ADMIN_PASSWORD", "")

    if not admin_password:
        logger.warning("⚠️  ADMIN_PASSWORD not set — skipping admin seed. Set it in Railway env vars.")
        return

    try:
        from v4.database.models import User, Organization
        from sqlalchemy import select
        import uuid

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.email == admin_email.lower())
            )
            if result.scalar_one_or_none():
                logger.info(f"✅ Admin user '{admin_email}' exists")
                return

            # Create org + admin
            try:
                import bcrypt
                pw_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
            except ImportError:
                import hashlib
                pw_hash = hashlib.sha256(admin_password.encode()).hexdigest()

            org = Organization(
                id=str(uuid.uuid4()),
                name="OrQuanta Platform",
                slug="orquanta",
                plan="enterprise",
            )
            session.add(org)
            await session.flush()

            admin = User(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                email=admin_email.lower(),
                hashed_password=pw_hash,
                name="OrQuanta Admin",
                role="admin",
            )
            session.add(admin)
            await session.commit()
            logger.info(f"✅ Admin user '{admin_email}' created")

    except Exception as exc:
        logger.warning(f"Admin seed skipped: {exc}")


def run_validation():
    """Run production readiness check."""
    logger.info("🔍 Running production validation...")
    env = os.getenv("ENV", "production")
    jwt_key = os.getenv("JWT_SECRET_KEY", "")
    runpod = os.getenv("RUNPOD_API_KEY", "")
    lambda_key = os.getenv("LAMBDA_LABS_API_KEY", "")
    stripe = os.getenv("STRIPE_SECRET_KEY", "")

    checks = {
        "JWT_SECRET_KEY": bool(jwt_key),
        "GPU Provider": bool(runpod or lambda_key),
        "Stripe Billing": bool(stripe),
    }

    for name, ok in checks.items():
        status = "✅" if ok else ("⚠️ " if name == "Stripe Billing" else "❌")
        logger.info(f"  {status} {name}")

    if not jwt_key and env == "production":
        logger.critical("❌ JWT_SECRET_KEY not set in production! Authentication will fail.")
        logger.critical("   Generate: python -c \"import secrets; print(secrets.token_hex(32))\"")

    if not (runpod or lambda_key):
        logger.warning("⚠️  No GPU provider keys — jobs will run in MOCK mode")
        logger.warning("   Add RUNPOD_API_KEY in Railway → Variables to enable real GPU jobs")


def main():
    parser = argparse.ArgumentParser(description="OrQuanta Production Server")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--skip-db-init", action="store_true", help="Skip database initialization")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  OrQuanta AI GPU Cloud v1.0 — Production Server")
    logger.info("=" * 60)
    logger.info(f"  ENV: {os.getenv('ENV', 'production')}")
    logger.info(f"  PORT: {args.port}")
    logger.info(f"  PID: {os.getpid()}")
    logger.info("=" * 60)

    # Run validation
    run_validation()

    # Initialize database
    if not args.skip_db_init:
        try:
            asyncio.run(initialize_database())
        except Exception as exc:
            logger.warning(f"DB init had errors (continuing): {exc}")

    # Launch uvicorn
    logger.info(f"\n🚀 Starting OrQuanta API server on {args.host}:{args.port}...\n")

    import uvicorn
    uvicorn.run(
        "v4.api.main:app",
        host=args.host,
        port=args.port,
        workers=args.workers,
        log_level="info",
        access_log=True,
        proxy_headers=True,  # Trust Railway's reverse proxy
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
