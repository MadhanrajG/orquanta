"""
OrQuanta Agentic v1.0 — Secrets Manager

Hierarchy (first found wins):
  1. AWS Secrets Manager (production)
  2. HashiCorp Vault (enterprise alternative)
  3. Environment variables / .env file (development)

Rules:
  - Secrets are NEVER logged, even at DEBUG level
  - Secrets are NEVER included in exception messages
  - Secret values are wrapped in a SecretString class
    that redacts itself in repr/str
  - Rotation-aware: cached with TTL, re-fetched on expiry
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("orquanta.security.secrets")

# Never log these key substrings even if someone asks
_SENSITIVE_KEYWORDS = {
    "key", "secret", "password", "token", "credential",
    "private", "cert", "auth", "api_key", "signing",
}

SECRETS_BACKEND = os.getenv("SECRETS_BACKEND", "env")   # env | aws | vault
AWS_SECRETS_REGION = os.getenv("AWS_SECRETS_REGION", "us-east-1")
AWS_SECRETS_PREFIX = os.getenv("AWS_SECRETS_PREFIX", "orquanta/v4/")
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "")
VAULT_PATH_PREFIX = os.getenv("VAULT_PATH_PREFIX", "secret/orquanta/")
SECRET_CACHE_TTL_SECONDS = int(os.getenv("SECRET_CACHE_TTL_SECONDS", "300"))  # 5 min


class SecretString:
    """Wraps a secret value so it never appears in logs or repr."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        object.__setattr__(self, "_value", value)

    def get(self) -> str:
        """Return the actual secret value — call this at the last moment."""
        return object.__getattribute__(self, "_value")

    def __repr__(self) -> str:
        return "SecretString(***)"

    def __str__(self) -> str:
        return "***"

    def __bool__(self) -> bool:
        return bool(object.__getattribute__(self, "_value"))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SecretString):
            return self.get() == other.get()
        return False

    # Prevent accidental serialization
    def __reduce__(self):
        raise RuntimeError("SecretString cannot be pickled")


@dataclass
class SecretCacheEntry:
    value: SecretString
    fetched_at: float = field(default_factory=time.monotonic)

    def is_expired(self, ttl: int = SECRET_CACHE_TTL_SECONDS) -> bool:
        return (time.monotonic() - self.fetched_at) > ttl


class SecretsManager:
    """Unified secrets access layer.

    Usage:
        sm = SecretsManager()
        api_key = sm.get("OPENAI_API_KEY").get()
    """

    def __init__(self) -> None:
        self._cache: dict[str, SecretCacheEntry] = {}
        self._backend = SECRETS_BACKEND
        self._boto_client = None
        logger.info(f"[SecretsManager] Backend: {self._backend}")

    # ─── Public API ────────────────────────────────────────────────────

    def get(self, key: str, default: str = "") -> SecretString:
        """Retrieve a secret by key. Returns SecretString (never logs value)."""
        # Check cache first
        cached = self._cache.get(key)
        if cached and not cached.is_expired():
            return cached.value

        # Fetch from backend
        raw = self._fetch(key, default)

        if not raw and default:
            raw = default

        secret = SecretString(raw)
        self._cache[key] = SecretCacheEntry(value=secret)
        return secret

    def get_json(self, key: str) -> dict[str, Any]:
        """Fetch a JSON secret (e.g. service account JSON)."""
        raw = self.get(key).get()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"[SecretsManager] Failed to parse JSON secret '{key}'")
            return {}

    def set_secret(self, key: str, value: str) -> bool:
        """Save or update a secret in the backend."""
        if self._backend == "aws":
            return self._aws_put(key, value)
        elif self._backend == "vault":
            return self._vault_put(key, value)
        else:
            logger.warning("[SecretsManager] set_secret() not supported in env backend")
            return False

    def rotate_secret(self, key: str, new_value: str) -> bool:
        """Rotate a secret: update backend + invalidate cache."""
        success = self.set_secret(key, new_value)
        if success:
            self._cache.pop(key, None)
            # Log rotation event (NOT the value)
            logger.info(f"[SecretsManager] Secret '{key}' rotated successfully (hash={self._key_hash(new_value)})")
        return success

    def invalidate_cache(self, key: str | None = None) -> None:
        """Flush cache for one key or all."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()
        logger.debug(f"[SecretsManager] Cache invalidated: {'all' if key is None else key}")

    def health_check(self) -> dict[str, Any]:
        """Test backend connectivity."""
        result = {"backend": self._backend, "status": "unknown", "cached_count": len(self._cache)}
        try:
            if self._backend == "aws":
                client = self._get_boto_client()
                # Minimal API call just to test auth
                client.list_secrets(MaxResults=1)
                result["status"] = "healthy"
            elif self._backend == "vault":
                import httpx, asyncio
                # Sync check
                resp = httpx.get(f"{VAULT_ADDR}/v1/sys/health", timeout=3.0)
                result["status"] = "healthy" if resp.status_code in (200, 429) else "degraded"
            else:
                result["status"] = "healthy"   # env is always "healthy"
        except Exception as exc:
            result["status"] = "error"
            result["error"] = type(exc).__name__
        return result

    # ─── Internal fetch ────────────────────────────────────────────────

    def _fetch(self, key: str, default: str = "") -> str:
        if self._backend == "aws":
            return self._aws_get(key) or os.getenv(key, default)
        elif self._backend == "vault":
            return self._vault_get(key) or os.getenv(key, default)
        else:
            return os.getenv(key, default)

    # ─── AWS Secrets Manager ───────────────────────────────────────────

    def _get_boto_client(self):
        if self._boto_client is None:
            try:
                import boto3
                self._boto_client = boto3.client(
                    "secretsmanager",
                    region_name=AWS_SECRETS_REGION,
                )
            except ImportError:
                raise RuntimeError("boto3 not installed — cannot use AWS Secrets Manager backend")
        return self._boto_client

    def _aws_get(self, key: str) -> str:
        secret_id = f"{AWS_SECRETS_PREFIX}{key}"
        try:
            client = self._get_boto_client()
            resp = client.get_secret_value(SecretId=secret_id)
            raw = resp.get("SecretString") or ""
            # Never log the value
            logger.debug(f"[SecretsManager] AWS fetched '{key}' (present={bool(raw)})")
            return raw
        except Exception as exc:
            exc_name = type(exc).__name__
            if "ResourceNotFoundException" in exc_name or "ResourceNotFound" in str(exc):
                logger.debug(f"[SecretsManager] Secret '{key}' not found in AWS SM")
            else:
                logger.warning(f"[SecretsManager] AWS SM error for '{key}': {exc_name}")
            return ""

    def _aws_put(self, key: str, value: str) -> bool:
        secret_id = f"{AWS_SECRETS_PREFIX}{key}"
        try:
            client = self._get_boto_client()
            try:
                client.put_secret_value(SecretId=secret_id, SecretString=value)
            except Exception:
                client.create_secret(Name=secret_id, SecretString=value)
            return True
        except Exception as exc:
            logger.error(f"[SecretsManager] AWS SM put failed for '{key}': {type(exc).__name__}")
            return False

    # ─── HashiCorp Vault ───────────────────────────────────────────────

    def _vault_get(self, key: str) -> str:
        path = f"{VAULT_PATH_PREFIX}{key}"
        try:
            import httpx
            resp = httpx.get(
                f"{VAULT_ADDR}/v1/{path}",
                headers={"X-Vault-Token": VAULT_TOKEN},
                timeout=5.0,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                # KV v2 wraps in data.data
                if "data" in data:
                    data = data["data"]
                value = data.get("value") or data.get(key, "")
                logger.debug(f"[SecretsManager] Vault fetched '{key}' (present={bool(value)})")
                return value
            return ""
        except Exception as exc:
            logger.warning(f"[SecretsManager] Vault error for '{key}': {type(exc).__name__}")
            return ""

    def _vault_put(self, key: str, value: str) -> bool:
        path = f"{VAULT_PATH_PREFIX}{key}"
        try:
            import httpx
            resp = httpx.post(
                f"{VAULT_ADDR}/v1/{path}",
                headers={"X-Vault-Token": VAULT_TOKEN, "Content-Type": "application/json"},
                json={"data": {"value": value}},
                timeout=5.0,
            )
            return resp.status_code in (200, 204)
        except Exception as exc:
            logger.error(f"[SecretsManager] Vault put failed for '{key}': {type(exc).__name__}")
            return False

    @staticmethod
    def _key_hash(value: str) -> str:
        """SHA-256 fingerprint for rotation audit — safe to log."""
        return hashlib.sha256(value.encode()).hexdigest()[:12]


# ─── Singleton ───────────────────────────────────────────────────────────────

_secrets_manager: SecretsManager | None = None


def get_secrets_manager() -> SecretsManager:
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


def get_secret(key: str, default: str = "") -> str:
    """Convenience function — returns raw string. Use sparingly."""
    return get_secrets_manager().get(key, default).get()
