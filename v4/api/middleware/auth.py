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
                "role": "admin",
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
# In-memory user store (replace with PostgreSQL in production)
# ---------------------------------------------------------------------------

import hashlib
import secrets as sec_module
from typing import Optional

_USERS: dict[str, dict[str, Any]] = {}


def hash_password(password: str, salt: str) -> str:
    """Hash a password with salt using SHA-256."""
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def register_user(email: str, password: str, name: str = "") -> dict[str, Any]:
    """Register a new user.

    Args:
        email: User email.
        password: Plain-text password (will be hashed).
        name: Display name.

    Returns:
        User dict.

    Raises:
        ValueError: If email already registered.
    """
    if email.lower() in _USERS:
        raise ValueError(f"Email '{email}' is already registered.")

    user_id = sec_module.token_hex(16)
    salt = sec_module.token_hex(8)
    hashed = hash_password(password, salt)

    user = {
        "id": user_id,
        "email": email.lower(),
        "name": name or email.split("@")[0],
        "hashed_pw": hashed,
        "salt": salt,
        "role": "user",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _USERS[email.lower()] = user
    logger.info(f"User registered: {email} (id={user_id})")
    return user


def authenticate_user(email: str, password: str) -> Optional[dict[str, Any]]:
    """Verify credentials and return user if valid."""
    user = _USERS.get(email.lower())
    if not user:
        return None
    expected = hash_password(password, user["salt"])
    if expected == user["hashed_pw"]:
        return user
    return None
