"""
OrQuanta Agentic v1.0 — JWT Authentication Middleware
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("orquanta.auth")

JWT_SECRET = os.getenv("JWT_SECRET", "orquanta-dev-secret-change-in-production-please")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
LEGACY_API_KEY = os.getenv("ORQUANTA_API_KEY", "dev-key-change-in-production")

http_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------

def create_access_token(user_id: str, email: str, role: str = "user") -> str:
    """Create a signed JWT access token.

    Args:
        user_id: Unique user identifier.
        email: User email address.
        role: User role (user/admin).

    Returns:
        Signed JWT string.
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Args:
        token: JWT string.

    Returns:
        Decoded payload dict.

    Raises:
        HTTPException 401: If token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    request: Request = None,
) -> dict[str, Any]:
    """FastAPI dependency: extract and validate the current user.

    Supports two auth methods:
    1. Bearer JWT token (primary)
    2. X-API-Key header (legacy v3.8 compatibility)

    Returns:
        User payload dict with sub, email, role.

    Raises:
        HTTPException 401: If no valid credentials provided.
    """
    # Method 1: Bearer token
    if credentials and credentials.scheme.lower() == "bearer":
        return decode_token(credentials.credentials)

    # Method 2: Legacy API key (X-API-Key header)
    if request:
        api_key = request.headers.get("X-API-Key", "")
        if api_key and api_key == LEGACY_API_KEY:
            return {
                "sub": "legacy-api-user",
                "email": "api@orquanta.internal",
                "role": "user",  # FIX-10: was "admin" — legacy key must not grant admin
                "auth_method": "api_key",
            }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide a Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_admin(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """FastAPI dependency: require admin role."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for this operation.",
        )
    return user


# ---------------------------------------------------------------------------
# User store — PostgreSQL (prod) with SQLite fallback (local dev)
# ---------------------------------------------------------------------------

import hashlib
import sqlite3
import secrets as sec_module
from typing import Optional

_DATABASE_URL = os.getenv("DATABASE_URL", "")
_USE_PG = _DATABASE_URL.startswith(("postgresql://", "postgres://"))

if _USE_PG:
    try:
        import psycopg2
        import psycopg2.extras
        logger.info("Auth: PostgreSQL mode (DATABASE_URL detected)")
    except ImportError:
        logger.error("psycopg2-binary not installed — falling back to SQLite")
        _USE_PG = False

_DB_FILE = "./orquanta.db" if not _USE_PG else None

_CREATE_USERS_TABLE = """
    CREATE TABLE IF NOT EXISTS users (
        id          TEXT PRIMARY KEY,
        email       TEXT UNIQUE NOT NULL,
        name        TEXT NOT NULL DEFAULT '',
        hashed_pw   TEXT NOT NULL,
        salt        TEXT NOT NULL,
        role        TEXT NOT NULL DEFAULT 'user',
        created_at  TEXT NOT NULL
    )
"""


def _get_db():
    """Return a database connection — PostgreSQL in prod, SQLite in dev."""
    if _USE_PG:
        # connect_timeout=10 prevents startup hang on cross-region connections
        conn = psycopg2.connect(
            _DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=10,
        )
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(_CREATE_USERS_TABLE)
        conn.commit()
        return conn
    else:
        conn = sqlite3.connect(_DB_FILE)
        conn.row_factory = sqlite3.Row
        conn.execute(_CREATE_USERS_TABLE)
        conn.commit()
        return conn


def _ph() -> str:
    """Parameter placeholder — %s for PostgreSQL, ? for SQLite."""
    return "%s" if _USE_PG else "?"


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), iterations=100_000
    ).hex()


def register_user(email: str, password: str, name: str = "") -> dict[str, Any]:
    """Register a new user. Works with both PostgreSQL and SQLite."""
    conn = _get_db()
    ph = _ph()
    try:
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(f"SELECT id FROM users WHERE email = {ph}", (email.lower(),))
            existing = cur.fetchone()
        else:
            existing = conn.execute(
                f"SELECT id FROM users WHERE email = {ph}", (email.lower(),)
            ).fetchone()

        if existing:
            raise ValueError(f"Email '{email}' is already registered.")

        user_id = sec_module.token_hex(16)
        salt = sec_module.token_hex(8)
        hashed = hash_password(password, salt)
        created_at = datetime.now(timezone.utc).isoformat()
        display_name = name or email.split("@")[0]

        sql = (
            f"INSERT INTO users (id, email, name, hashed_pw, salt, role, created_at) "
            f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})"
        )
        params = (user_id, email.lower(), display_name, hashed, salt, "user", created_at)

        if _USE_PG:
            cur.execute(sql, params)
            conn.commit()
            cur.close()
        else:
            conn.execute(sql, params)
            conn.commit()

        logger.info(f"User registered: {email} (id={user_id}) — {'PostgreSQL' if _USE_PG else 'SQLite'}")
        return {"id": user_id, "email": email.lower(), "name": display_name,
                "hashed_pw": hashed, "salt": salt, "role": "user", "created_at": created_at}
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Optional[dict[str, Any]]:
    """Verify credentials. Works with both PostgreSQL and SQLite."""
    conn = _get_db()
    ph = _ph()
    try:
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM users WHERE email = {ph}", (email.lower(),))
            row = cur.fetchone()
            cur.close()
            if row is None:
                return None
            row = dict(row)
        else:
            row = conn.execute(
                f"SELECT * FROM users WHERE email = {ph}", (email.lower(),)
            ).fetchone()
            if row is None:
                return None
            row = dict(row)

        if hash_password(password, row["salt"]) == row["hashed_pw"]:
            return row
        return None
    finally:
        conn.close()

