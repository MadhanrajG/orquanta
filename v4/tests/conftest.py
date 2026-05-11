"""
OrQuanta Test Configuration
=============================
Patches DATABASE_URL to use SQLite in-memory so tests run without
a live PostgreSQL instance. Also mocks Stripe, Redis, and cloud providers.
"""
import os
import pytest

# ── Override DB to in-memory SQLite BEFORE any module imports ─────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./orquanta_test.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRE_MINUTES", "60")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("USE_REAL_PROVIDERS", "false")
os.environ.setdefault("ORQUANTA_DEMO_MODE", "false")
os.environ.setdefault("STRIPE_SECRET_KEY", "")  # Disable billing
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-pass")


def pytest_configure(config):
    """Ensure test environment is clean."""
    import pathlib
    for db_file in ("orquanta_test.db", "orquanta.db"):
        p = pathlib.Path(db_file)
        if p.exists():
            p.unlink()
