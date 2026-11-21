# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Hardened Inference API Key Manager — Phase 3 Objective 6
=================================================================
SECURITY RULES:
- Raw keys shown ONCE at creation; never stored in plaintext.
- Only SHA-256 hashes stored. Keys are prefixed sk-orq-.
- Budget enforcement uses threading.Lock for concurrency safety.
- Keys support scopes, model restrictions, expiry, and revocation.
- Admin endpoints require the "admin" scope explicitly.
- Key prefixes logged for auditability; full key never logged.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orquanta.inference.api_keys")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KEY_PREFIX   = "sk-orq-"
KEY_RAND_LEN = 40           # Random suffix length (chars)
KEY_TTL_DAYS = int(os.getenv("INFERENCE_KEY_TTL_DAYS", "90"))

SCOPES = frozenset([
    "inference:read",        # Read model listing
    "inference:write",       # Submit inference requests
    "models:read",           # Browse model registry
    "deployments:read",      # View deployments
    "deployments:write",     # Create/stop deployments
    "benchmarks:read",       # View benchmark results
    "benchmarks:write",      # Submit benchmark runs
    "admin",                 # Administrative endpoints (never default)
])

DEFAULT_SCOPES = ["inference:write", "models:read", "deployments:read"]


# ---------------------------------------------------------------------------
# Key record
# ---------------------------------------------------------------------------

@dataclass
class InferenceAPIKey:
    key_id: str
    user_id: str
    org_id: str
    name: str
    key_hash: str                   # SHA-256 of raw key — NEVER the raw key
    key_prefix: str                 # First 8 chars of raw key (for display/audit)
    scopes: List[str]
    models_allowed: List[str]       # ["*"] = all models; specific list = restricted
    budget_usd: float
    rate_limit_rpm: int
    created_at: str
    expires_at: str
    is_active: bool = True
    is_revoked: bool = False
    revocation_reason: str = ""
    spent_usd: float = 0.0
    last_used_at: Optional[str] = None
    request_times: List[float] = field(default_factory=list)   # For rate limiter

    def to_safe_dict(self) -> Dict[str, Any]:
        """Return a safe representation — no hash, no raw key, no request_times."""
        return {
            "key_id":        self.key_id,
            "user_id":       self.user_id,
            "org_id":        self.org_id,
            "name":          self.name,
            "key_prefix":    self.key_prefix,  # e.g. "sk-orq-ab"
            "scopes":        self.scopes,
            "models_allowed":self.models_allowed,
            "budget_usd":    self.budget_usd,
            "spent_usd":     round(self.spent_usd, 6),
            "rate_limit_rpm":self.rate_limit_rpm,
            "created_at":    self.created_at,
            "expires_at":    self.expires_at,
            "is_active":     self.is_active,
            "is_revoked":    self.is_revoked,
            "last_used_at":  self.last_used_at,
        }


# ---------------------------------------------------------------------------
# API Key Manager
# ---------------------------------------------------------------------------

class APIKeyManager:
    def __init__(self) -> None:
        self._keys: Dict[str, InferenceAPIKey] = {}   # key_hash → record
        self._by_id: Dict[str, str] = {}              # key_id → key_hash
        self._lock = threading.Lock()                  # Protects budget deductions

    # ── Key generation ───────────────────────────────────────────────────────

    def generate_key(
        self,
        user_id: str,
        org_id: str,
        name: str,
        scopes: Optional[List[str]] = None,
        models_allowed: Optional[List[str]] = None,
        budget_usd: float = 10.0,
        rate_limit_rpm: int = 60,
        ttl_days: int = KEY_TTL_DAYS,
    ) -> tuple[str, InferenceAPIKey]:
        """
        Generate a new inference API key.

        Returns (raw_key, InferenceAPIKey). The raw_key is returned ONCE
        and NEVER stored. Store it securely — it cannot be recovered.
        """
        if scopes is None:
            scopes = list(DEFAULT_SCOPES)

        # Validate scopes
        invalid = set(scopes) - SCOPES
        if invalid:
            raise ValueError(f"Invalid scopes: {invalid}. Valid: {sorted(SCOPES)}")

        # Generate raw key
        raw_rand = secrets.token_urlsafe(KEY_RAND_LEN)
        raw_key  = f"{KEY_PREFIX}{raw_rand}"

        # Hash it — only this is stored
        key_hash   = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:12]   # sk-orq-XXXX — safe prefix for logs

        now     = datetime.now(timezone.utc)
        expires = now + timedelta(days=ttl_days)

        record = InferenceAPIKey(
            key_id=str(uuid.uuid4()),
            user_id=user_id,
            org_id=org_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes,
            models_allowed=models_allowed or ["*"],
            budget_usd=budget_usd,
            rate_limit_rpm=rate_limit_rpm,
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
        )

        self._keys[key_hash]     = record
        self._by_id[record.key_id] = key_hash

        logger.info("[api_keys] Created key prefix=%s user=%s scopes=%s", key_prefix, user_id, scopes)
        # Raw key returned here and NEVER again
        return raw_key, record

    # ── Validation ──────────────────────────────────────────────────────────

    def validate_key(self, raw_key: str) -> Optional[InferenceAPIKey]:
        """
        Validate a raw key. Returns the record or None.
        Updates last_used_at on success.
        """
        if not raw_key or not raw_key.startswith(KEY_PREFIX):
            return None

        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        record   = self._keys.get(key_hash)

        if not record:
            logger.warning("[api_keys] Unknown key (prefix=%s)", raw_key[:12])
            return None

        if record.is_revoked:
            logger.warning("[api_keys] Revoked key used prefix=%s", record.key_prefix)
            return None

        if not record.is_active:
            return None

        # Expiry check
        try:
            expires = datetime.fromisoformat(record.expires_at)
            if datetime.now(timezone.utc) > expires:
                logger.warning("[api_keys] Expired key prefix=%s", record.key_prefix)
                return None
        except Exception:
            pass

        record.last_used_at = datetime.now(timezone.utc).isoformat()
        return record

    # ── Internal lookup by key_id ────────────────────────────────────────────

    def _get_record_by_id(self, key_id: str) -> Optional["InferenceAPIKey"]:
        key_hash = self._by_id.get(key_id)
        if not key_hash:
            return None
        return self._keys.get(key_hash)

    # ── Scope enforcement ────────────────────────────────────────────────────

    def has_scope(self, record_or_id, required_scope: str) -> bool:
        """Accept an InferenceAPIKey record or a key_id string."""
        if isinstance(record_or_id, str):
            record = self._get_record_by_id(record_or_id)
            if record is None:
                return False
        else:
            record = record_or_id
        return required_scope in record.scopes

    def check_model_permission(self, record_or_id, model_id: str) -> bool:
        if isinstance(record_or_id, str):
            record = self._get_record_by_id(record_or_id)
            if record is None:
                return False
        else:
            record = record_or_id
        if record.models_allowed == ["*"]:
            return True
        return model_id in record.models_allowed

    # ── Budget enforcement (concurrency-safe) ────────────────────────────────

    def check_and_deduct_budget(self, record_or_id, cost_usd: float) -> bool:
        """
        Atomically check budget and deduct cost.
        Accept an InferenceAPIKey record or a key_id string.
        Returns True if deducted, False if budget exceeded.
        """
        if isinstance(record_or_id, str):
            with self._lock:
                record = self._get_record_by_id(record_or_id)
                if record is None:
                    return False
                if record.spent_usd + cost_usd > record.budget_usd:
                    logger.warning(
                        "[api_keys] Budget exceeded id=%s spent=%.4f budget=%.4f cost=%.6f",
                        record_or_id, record.spent_usd, record.budget_usd, cost_usd,
                    )
                    return False
                record.spent_usd += cost_usd
                return True
        else:
            record = record_or_id
            with self._lock:
                if record.spent_usd + cost_usd > record.budget_usd:
                    logger.warning(
                        "[api_keys] Budget exceeded prefix=%s spent=%.4f budget=%.4f cost=%.6f",
                        record.key_prefix, record.spent_usd, record.budget_usd, cost_usd,
                    )
                    return False
                record.spent_usd += cost_usd
                return True

    # ── Rate limiting ────────────────────────────────────────────────────────

    def check_rate(self, record: InferenceAPIKey) -> bool:
        """Sliding-window rate limiter. Thread-safe via GIL for list ops."""
        import time as _t
        now = _t.time()
        window = 60.0
        with self._lock:
            record.request_times = [t for t in record.request_times if now - t < window]
            if len(record.request_times) >= record.rate_limit_rpm:
                return False
            record.request_times.append(now)
            return True

    # ── Revocation ───────────────────────────────────────────────────────────

    def revoke_key(self, key_id: str, reason: str = "") -> bool:
        """Revoke a key by key_id. Returns True if revoked, False if not found."""
        key_hash = self._by_id.get(key_id)
        if not key_hash:
            return False
        record = self._keys.get(key_hash)
        if not record:
            return False
        record.is_revoked = True
        record.is_active  = False
        record.revocation_reason = reason
        logger.info("[api_keys] Revoked key_id=%s prefix=%s reason=%s", key_id, record.key_prefix, reason[:80])
        return True

    # ── Listing ──────────────────────────────────────────────────────────────

    def list_keys(self, user_id: str) -> List[Dict[str, Any]]:
        """List keys for a user. Returns safe dicts — no hash, no raw key."""
        return [
            r.to_safe_dict()
            for r in self._keys.values()
            if r.user_id == user_id
        ]

    def get_key_by_id(self, key_id: str, user_id: str) -> Optional[InferenceAPIKey]:
        """Get key by ID, restricted to the requesting user."""
        key_hash = self._by_id.get(key_id)
        if not key_hash:
            return None
        record = self._keys.get(key_hash)
        if record and record.user_id == user_id:
            return record
        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager = APIKeyManager()


def get_key_manager() -> APIKeyManager:
    return _manager
