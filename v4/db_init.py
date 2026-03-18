"""
OrQuanta Database Initializer
==============================
Run this once on first deploy (Railway, Render, etc.) to create all tables.
Also seeds a default admin user if ADMIN_EMAIL and ADMIN_PASSWORD are set.

Usage:
    python v4/db_init.py

On Railway:
    Set as start command or run once from the Railway console.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger("orquanta.db_init")


async def init_db():
    """Create all ORM tables and seed admin user."""
    from database.models import engine, Base, AsyncSessionLocal, User, Organization
    from sqlalchemy import text
    import hashlib
    import uuid

    logger.info("Creating database tables...")

    # Create all tables (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Tables created (or already exist)")

    # Seed admin user
    admin_email = os.getenv("ADMIN_EMAIL", "admin@orquanta.ai")
    admin_password = os.getenv("ADMIN_PASSWORD", "")

    if not admin_password:
        logger.warning("ADMIN_PASSWORD not set — skipping admin seed")
        return

    async with AsyncSessionLocal() as session:
        # Check if admin already exists
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.email == admin_email.lower())
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Admin user '{admin_email}' already exists — skipping")
            return

        # Create default organization
        org = Organization(
            id=str(uuid.uuid4()),
            name="OrQuanta Admin",
            slug="orquanta-admin",
            plan="enterprise",
        )
        session.add(org)
        await session.flush()

        # Create admin user with bcrypt-compatible hash
        try:
            import bcrypt
            pw_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
        except ImportError:
            # Fallback: SHA-256 (not production-safe, replace with bcrypt)
            pw_hash = hashlib.sha256(admin_password.encode()).hexdigest()
            logger.warning("bcrypt not installed — using SHA-256 fallback. Install: pip install bcrypt")

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
        logger.info(f"✅ Admin user '{admin_email}' created with role=admin")


async def check_connection():
    """Verify database is reachable before init."""
    from database.models import engine
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info(f"✅ Database connection OK")
        return True
    except Exception as exc:
        logger.error(f"❌ Database connection failed: {exc}")
        return False


async def main():
    logger.info("OrQuanta DB Initializer starting...")
    logger.info(f"DATABASE_URL: {os.getenv('DATABASE_URL', 'NOT SET')[:50]}...")

    ok = await check_connection()
    if not ok:
        logger.error("Cannot connect to database. Check DATABASE_URL and ensure PostgreSQL is running.")
        sys.exit(1)

    await init_db()
    logger.info("Database initialization complete ✅")


if __name__ == "__main__":
    # Add v4 directory to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(main())
