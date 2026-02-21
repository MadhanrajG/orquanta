"""
OrQuanta Agentic v1.0 — Security Headers Middleware + Auth Hardening

Implements:
  - HTTPS enforcement (redirect HTTP → HTTPS)
  - Security response headers (HSTS, CSP, X-Frame-Options, etc.)
  - CORS strict policy with allowlist
  - API key hashing (SHA-256 + salt, never stored plaintext)
  - JWT refresh token rotation with Redis blacklist
  - Request ID injection for log correlation
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
import uuid
from typing import Any

logger = logging.getLogger("orquanta.security.headers")

HTTPS_ENFORCE = os.getenv("HTTPS_ENFORCE", "false").lower() == "true"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
JWT_REFRESH_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "30"))
API_KEY_SALT = os.getenv("API_KEY_SALT", "orquanta-api-key-salt-change-in-prod")
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://localhost:8000"
    ).split(",") if o.strip()
]


# ─── Security Headers Middleware ─────────────────────────────────────────────

def make_security_headers_middleware():
    """Create starlette middleware that adds all security headers."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import RedirectResponse

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        _CSP = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "   # Needed for Vite dev
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )

        async def dispatch(self, request, call_next):
            # 1. HTTPS redirect
            if HTTPS_ENFORCE and request.url.scheme == "http":
                https_url = request.url.replace(scheme="https")
                return RedirectResponse(url=str(https_url), status_code=301)

            # 2. Inject request ID for log correlation
            request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
            request.state.request_id = request_id

            response = await call_next(request)

            # 3. Add security headers
            response.headers.update({
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "Permissions-Policy": (
                    "camera=(), microphone=(), geolocation=(), "
                    "payment=(), usb=(), interest-cohort=()"
                ),
                "Content-Security-Policy": self._CSP,
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
            })

            # HSTS only over HTTPS
            if request.url.scheme == "https":
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains; preload"
                )

            # Remove server identity headers
            response.headers.pop("Server", None)
            response.headers.pop("X-Powered-By", None)

            return response

    return SecurityHeadersMiddleware


# ─── CORS configuration ───────────────────────────────────────────────────────

def get_cors_config() -> dict[str, Any]:
    """Return strict CORS configuration for FastAPI."""
    return {
        "allow_origins": ALLOWED_ORIGINS,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        "allow_headers": [
            "Authorization", "Content-Type", "X-Request-ID",
            "X-API-Key", "Accept", "Origin",
        ],
        "expose_headers": [
            "X-Request-ID", "X-RateLimit-Remaining",
            "X-RateLimit-Reset", "X-RateLimit-Limit",
        ],
        "max_age": 600,
    }


# ─── API Key management ───────────────────────────────────────────────────────

class APIKeyManager:
    """
    Secure API key generation and verification.

    Keys are NEVER stored in plaintext. We store:
      - key_prefix (first 8 chars, for fast lookup)
      - key_hash   (SHA-256 HMAC with fixed salt)

    Key format: bm_v4_{random_32_hex}
    """

    KEY_PREFIX_LEN = 8
    KEY_PREFIX_FORMAT = "bm_v4_"

    @classmethod
    def generate(cls) -> tuple[str, str, str]:
        """
        Generate a new API key.
        Returns: (full_key, key_prefix, key_hash)

        full_key is returned ONCE — never stored.
        key_prefix and key_hash are stored in DB.
        """
        random_part = secrets.token_hex(32)
        full_key = f"{cls.KEY_PREFIX_FORMAT}{random_part}"
        prefix = full_key[:cls.KEY_PREFIX_LEN + 6]   # "bm_v4_" + 8 chars
        key_hash = cls.hash_key(full_key)
        return full_key, prefix, key_hash

    @classmethod
    def hash_key(cls, full_key: str) -> str:
        """Produce a deterministic HMAC-SHA256 hash of a key."""
        return hmac.new(
            API_KEY_SALT.encode(),
            full_key.encode(),
            hashlib.sha256
        ).hexdigest()

    @classmethod
    def verify(cls, provided_key: str, stored_hash: str) -> bool:
        """Constant-time comparison — safe against timing attacks."""
        expected_hash = cls.hash_key(provided_key)
        return hmac.compare_digest(expected_hash, stored_hash)

    @classmethod
    def extract_prefix(cls, key: str) -> str | None:
        """Extract the prefix for database lookup."""
        if not key.startswith(cls.KEY_PREFIX_FORMAT):
            return None
        return key[:cls.KEY_PREFIX_LEN + 6]


# ─── JWT Token management ─────────────────────────────────────────────────────

class JWTManager:
    """
    Secure JWT access + refresh token pair.

    Refresh tokens are tracked in Redis for:
      - Rotation: old refresh token → new pair
      - Revocation: logout invalidates all sessions
      - Hijacking detection: reuse of old token = forced logout
    """

    def __init__(self) -> None:
        self._redis = None
        self._connect_redis()

    def _connect_redis(self) -> None:
        try:
            import redis
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self._redis = redis.from_url(url, decode_responses=True, socket_timeout=1.0)
            self._redis.ping()
        except Exception:
            self._redis = None

    def create_access_token(self, user_id: str, email: str, role: str, org_id: str = "") -> str:
        """Create a short-lived access JWT."""
        from jose import jwt
        now = int(time.time())
        payload = {
            "sub": user_id,
            "email": email,
            "role": role,
            "org_id": org_id,
            "iat": now,
            "exp": now + (JWT_ACCESS_EXPIRE_MINUTES * 60),
            "jti": secrets.token_hex(16),   # Unique token ID
            "type": "access",
        }
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    def create_refresh_token(self, user_id: str) -> str:
        """Create a long-lived refresh JWT and register in Redis."""
        from jose import jwt
        now = int(time.time())
        jti = secrets.token_hex(32)
        payload = {
            "sub": user_id,
            "iat": now,
            "exp": now + (JWT_REFRESH_EXPIRE_DAYS * 86400),
            "jti": jti,
            "type": "refresh",
        }
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        # Register in Redis
        if self._redis:
            key = f"refresh_token:{user_id}:{jti}"
            self._redis.setex(key, JWT_REFRESH_EXPIRE_DAYS * 86400, "active")

        return token

    def verify_access_token(self, token: str) -> dict[str, Any] | None:
        """Verify and decode an access JWT. Returns payload or None."""
        from jose import jwt, JWTError
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "access":
                return None
            # Check blacklist
            jti = payload.get("jti", "")
            if self._redis and self._redis.get(f"blacklist:access:{jti}"):
                return None
            return payload
        except JWTError:
            return None

    def rotate_refresh_token(self, old_refresh_token: str) -> tuple[str, str] | None:
        """
        Exchange an old refresh token for a new access+refresh pair.
        Old token is invalidated — reuse triggers forced logout.
        Returns (new_access_token, new_refresh_token) or None if invalid.
        """
        from jose import jwt, JWTError
        try:
            payload = jwt.decode(old_refresh_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "refresh":
                return None

            user_id = payload["sub"]
            jti = payload["jti"]

            if self._redis:
                redis_key = f"refresh_token:{user_id}:{jti}"
                if not self._redis.get(redis_key):
                    # Token already used — detect hijacking
                    self._revoke_all_sessions(user_id)
                    logger.warning(f"[JWTManager] REFRESH TOKEN REUSE DETECTED — user {user_id} forced logout")
                    return None
                # Invalidate old token
                self._redis.delete(redis_key)

            # Issue new pair
            new_access = self.create_access_token(user_id, payload.get("email", ""), payload.get("role", "operator"))
            new_refresh = self.create_refresh_token(user_id)
            return new_access, new_refresh

        except JWTError:
            return None

    def revoke_token(self, token: str) -> None:
        """Blacklist an access token until its natural expiry."""
        from jose import jwt, JWTError
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            jti = payload.get("jti", "")
            ttl = payload.get("exp", 0) - int(time.time())
            if self._redis and ttl > 0 and jti:
                self._redis.setex(f"blacklist:access:{jti}", ttl, "revoked")
        except JWTError:
            pass

    def _revoke_all_sessions(self, user_id: str) -> None:
        """Nuclear option: delete all refresh tokens for a user."""
        if self._redis:
            for key in self._redis.scan_iter(f"refresh_token:{user_id}:*"):
                self._redis.delete(key)


# ─── Singletons ───────────────────────────────────────────────────────────────

_jwt_manager: JWTManager | None = None

def get_jwt_manager() -> JWTManager:
    global _jwt_manager
    if _jwt_manager is None:
        _jwt_manager = JWTManager()
    return _jwt_manager
