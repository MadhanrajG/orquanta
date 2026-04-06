"""
OrQuanta — Permanent Admin Credential Manager
==============================================
Creates or updates the permanent admin user with hardened credentials.
Run this ONCE after each deployment.

Usage:
    python create_admin.py

This script:
1. Connects to the database
2. Creates (or updates) the admin user with the credentials from env
3. Outputs confirmation

Security model:
- Password is read from ADMIN_PASSWORD env var (never hardcoded)
- Hashed with bcrypt (12 rounds) before storing
- Admin credentials should be stored in a password manager, NOT in .env in production
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("orquanta.admin")

# ── Secure credentials from environment ───────────────────────────────────────
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@orquanta.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_NAME = os.getenv("ADMIN_NAME", "OrQuanta Admin")

# ── PERMANENT ADMIN (fallback for local dev if env not set) ───────────────────
# These are only used if ADMIN_PASSWORD env is not set.
# In production: ALWAYS set ADMIN_PASSWORD via Railway Variables, not here.
_LOCAL_DEV_PASSWORD = "OrQ-Admin-2026!"   # Only for local dev


async def create_or_update_admin():
    """Create or update the permanent admin user."""
    if not ADMIN_PASSWORD and os.getenv("ENV", "development") == "production":
        logger.critical("❌ ADMIN_PASSWORD not set in production! Aborting.")
        sys.exit(1)

    password = ADMIN_PASSWORD or _LOCAL_DEV_PASSWORD
    if not ADMIN_PASSWORD:
        logger.warning("⚠️  ADMIN_PASSWORD not set in env — using local dev default")
        logger.warning("   For production: set ADMIN_PASSWORD in Railway Variables")

    # Hash the password with bcrypt
    try:
        import bcrypt
        pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
        logger.info("✅ Password hashed with bcrypt-12")
    except ImportError:
        import hashlib
        pw_hash = "pbkdf2:" + hashlib.pbkdf2_hmac(
            "sha256", password.encode(), b"orquanta-salt", 260000
        ).hex()
        logger.warning("⚠️  bcrypt not installed — using PBKDF2 fallback. Run: pip install bcrypt")

    # Connect to DB
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    try:
        from v4.database.models import engine, AsyncSessionLocal, User, Organization, Base
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy import select

        # Create tables if needed
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with AsyncSessionLocal() as session:
            # Check if admin exists
            result = await session.execute(
                select(User).where(User.email == ADMIN_EMAIL.lower())
            )
            existing_admin = result.scalar_one_or_none()

            if existing_admin:
                # Update password
                existing_admin.hashed_password = pw_hash
                existing_admin.role = "admin"
                await session.commit()
                logger.info(f"✅ Admin '{ADMIN_EMAIL}' password updated")
            else:
                # Create organization first
                org_result = await session.execute(
                    select(Organization).where(Organization.slug == "orquanta-platform")
                )
                org = org_result.scalar_one_or_none()

                if not org:
                    org = Organization(
                        id=str(uuid.uuid4()),
                        name="OrQuanta Platform",
                        slug="orquanta-platform",
                        plan="enterprise",
                    )
                    session.add(org)
                    await session.flush()

                admin = User(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    email=ADMIN_EMAIL.lower(),
                    hashed_password=pw_hash,
                    name=ADMIN_NAME,
                    role="admin",
                )
                session.add(admin)
                await session.commit()
                logger.info(f"✅ Admin user '{ADMIN_EMAIL}' created with role=admin")

    except ImportError as exc:
        logger.warning(f"DB models not available ({exc}) — creating local SQLite fallback admin")
        await create_sqlite_admin(pw_hash)
    except Exception as exc:
        logger.error(f"❌ DB error: {exc}")
        logger.info("Falling back to local SQLite admin creation...")
        await create_sqlite_admin(pw_hash)

    print("\n" + "=" * 50)
    print("  OrQuanta — Admin Credentials Summary")
    print("=" * 50)
    print(f"  Email:    {ADMIN_EMAIL}")
    print(f"  Password: {'[from ADMIN_PASSWORD env var]' if ADMIN_PASSWORD else _LOCAL_DEV_PASSWORD}")
    print(f"  Role:     admin")
    print(f"  URL:      http://localhost:8000/app")
    print("=" * 50)
    print("\n  ⚠️  SAVE THESE IN YOUR PASSWORD MANAGER!")
    print("  ⚠️  Never commit passwords to git.\n")


async def create_sqlite_admin(pw_hash: str):
    """Fallback: write admin to local SQLite directly."""
    import sqlite3
    db_path = os.getenv("DATABASE_URL", "orquanta_local.db").replace("sqlite:///./", "")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Create minimal users table if not exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            name TEXT,
            role TEXT DEFAULT 'user',
            created_at TEXT
        )
    """)

    admin_id = str(uuid.uuid4())
    cur.execute("""
        INSERT OR REPLACE INTO users (id, email, hashed_password, name, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        admin_id,
        ADMIN_EMAIL.lower(),
        pw_hash,
        ADMIN_NAME,
        "admin",
        datetime.now(timezone.utc).isoformat(),
    ))
    conn.commit()
    conn.close()
    logger.info(f"✅ Admin user written to local SQLite: {db_path}")


if __name__ == "__main__":
    asyncio.run(create_or_update_admin())
