"""
OrQuanta — User API Key Management

Endpoints:
  POST   /api/v1/api-keys          Create a new API key (returned ONCE — store it)
  GET    /api/v1/api-keys          List keys for the authenticated user (no secrets)
  DELETE /api/v1/api-keys/{key_id} Revoke a key

Key format:  sk-orq-<16-char-user-prefix>-<32-char-random>
Storage:     SHA-256 hash only — plaintext never stored after creation
Auth:        Bearer sk-orq-... in Authorization header works everywhere JWT does
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..middleware.auth import get_current_user
from ..middleware.rate_limit import rate_limit_dependency

logger = logging.getLogger("orquanta.api_keys")
router = APIRouter(prefix="/api/v1/api-keys", tags=["API Keys"])

_DATABASE_URL = os.getenv("DATABASE_URL", "")
_USE_PG = _DATABASE_URL.startswith(("postgresql://", "postgres://"))


# ─── DB helpers ───────────────────────────────────────────────────────────────

_DDL = """
    CREATE TABLE IF NOT EXISTS api_keys (
        key_id      TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        name        TEXT NOT NULL DEFAULT '',
        key_hash    TEXT NOT NULL UNIQUE,
        key_prefix  TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL,
        last_used   TEXT,
        is_active   INTEGER NOT NULL DEFAULT 1
    )
"""


def _get_db():
    if _USE_PG:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(_DATABASE_URL,
                                cursor_factory=psycopg2.extras.RealDictCursor,
                                connect_timeout=10)
        conn.autocommit = False
        return conn
    import sqlite3
    conn = sqlite3.connect("./orquanta.db")
    conn.row_factory = sqlite3.Row
    return conn


def _ph() -> str:
    return "%s" if _USE_PG else "?"


def _ensure_table() -> None:
    try:
        conn = _get_db()
        if _USE_PG:
            cur = conn.cursor(); cur.execute(_DDL); conn.commit(); cur.close()
        else:
            conn.execute(_DDL); conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning(f"[APIKeys] ensure_table: {exc}")


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _create_key_in_db(user_id: str, name: str) -> tuple[str, str]:
    """Generate key, store hash, return (key_id, full_key)."""
    key_id = secrets.token_hex(8)
    random_part = secrets.token_urlsafe(24)
    prefix = user_id[:8].replace("-", "")
    full_key = f"sk-orq-{prefix}-{random_part}"
    key_hash = _hash_key(full_key)
    now = datetime.now(timezone.utc).isoformat()
    ph = _ph()

    conn = _get_db()
    sql = (f"INSERT INTO api_keys (key_id, user_id, name, key_hash, key_prefix, created_at) "
           f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph})")
    try:
        if _USE_PG:
            cur = conn.cursor(); cur.execute(sql, (key_id, user_id, name, key_hash, full_key[:18], now))
            conn.commit(); cur.close()
        else:
            conn.execute(sql, (key_id, user_id, name, key_hash, full_key[:18], now))
            conn.commit()
    finally:
        conn.close()
    return key_id, full_key


def lookup_api_key(raw_key: str) -> dict[str, Any] | None:
    """Given a raw key, return user dict or None. Also updates last_used."""
    key_hash = _hash_key(raw_key)
    ph = _ph()
    try:
        conn = _get_db()
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(
                f"SELECT ak.user_id, u.email, u.role FROM api_keys ak "
                f"JOIN users u ON u.id = ak.user_id "
                f"WHERE ak.key_hash = {ph} AND ak.is_active = 1", (key_hash,))
            row = cur.fetchone()
            cur.close()
        else:
            row = conn.execute(
                f"SELECT ak.user_id, u.email, u.role FROM api_keys ak "
                f"JOIN users u ON u.id = ak.user_id "
                f"WHERE ak.key_hash = {ph} AND ak.is_active = 1", (key_hash,)).fetchone()

        if row:
            row = dict(row)
            # Update last_used (fire-and-forget)
            try:
                now = datetime.now(timezone.utc).isoformat()
                if _USE_PG:
                    cur2 = conn.cursor()
                    cur2.execute(f"UPDATE api_keys SET last_used = {ph} WHERE key_hash = {ph}",
                                 (now, key_hash))
                    conn.commit(); cur2.close()
                else:
                    conn.execute(f"UPDATE api_keys SET last_used = {ph} WHERE key_hash = {ph}",
                                 (now, key_hash))
                    conn.commit()
            except Exception:
                pass
        conn.close()
        if row:
            return {"sub": row["user_id"], "email": row["email"],
                    "role": row.get("role", "user"), "auth_method": "api_key"}
        return None
    except Exception as exc:
        logger.warning(f"[APIKeys] lookup failed: {exc}")
        return None


def _list_keys_for_user(user_id: str) -> list[dict]:
    ph = _ph()
    try:
        conn = _get_db()
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(
                f"SELECT key_id, name, key_prefix, created_at, last_used "
                f"FROM api_keys WHERE user_id = {ph} AND is_active = 1 ORDER BY created_at DESC",
                (user_id,))
            rows = [dict(r) for r in cur.fetchall()]; cur.close()
        else:
            rows = [dict(r) for r in conn.execute(
                f"SELECT key_id, name, key_prefix, created_at, last_used "
                f"FROM api_keys WHERE user_id = {ph} AND is_active = 1 ORDER BY created_at DESC",
                (user_id,)).fetchall()]
        conn.close()
        return rows
    except Exception as exc:
        logger.warning(f"[APIKeys] list failed: {exc}")
        return []


def _revoke_key(key_id: str, user_id: str) -> bool:
    ph = _ph()
    try:
        conn = _get_db()
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(f"UPDATE api_keys SET is_active = 0 WHERE key_id = {ph} AND user_id = {ph}",
                        (key_id, user_id))
            affected = cur.rowcount; conn.commit(); cur.close()
        else:
            cur = conn.execute(
                f"UPDATE api_keys SET is_active = 0 WHERE key_id = {ph} AND user_id = {ph}",
                (key_id, user_id))
            affected = cur.rowcount; conn.commit()
        conn.close()
        return affected > 0
    except Exception as exc:
        logger.warning(f"[APIKeys] revoke failed: {exc}")
        return False


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80,
                      description="Human-readable label, e.g. 'CI pipeline'")


class ApiKeyOut(BaseModel):
    key_id: str
    name: str
    key_prefix: str
    created_at: str
    last_used: str | None = None


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(..., description="Full API key — shown ONCE, store it securely")


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("", response_model=ApiKeyCreated, status_code=201,
             summary="Create API key — returned once, store immediately")
async def create_api_key(
    body: ApiKeyCreate,
    user: dict = Depends(get_current_user),
    _: None = Depends(rate_limit_dependency),
):
    _ensure_table()
    user_id = user["sub"]

    # Max 10 active keys per user
    existing = _list_keys_for_user(user_id)
    if len(existing) >= 10:
        raise HTTPException(status_code=429, detail="Maximum 10 active API keys per user.")

    key_id, full_key = _create_key_in_db(user_id, body.name)
    logger.info(f"[APIKeys] Created key '{body.name}' for user {user.get('email')}")
    return ApiKeyCreated(
        key_id=key_id,
        name=body.name,
        key_prefix=full_key[:18] + "...",
        created_at=datetime.now(timezone.utc).isoformat(),
        key=full_key,
    )


@router.get("", response_model=list[ApiKeyOut], summary="List your API keys")
async def list_api_keys(user: dict = Depends(get_current_user)):
    _ensure_table()
    rows = _list_keys_for_user(user["sub"])
    return [ApiKeyOut(**r) for r in rows]


@router.delete("/{key_id}", status_code=204, summary="Revoke an API key")
async def revoke_api_key(key_id: str, user: dict = Depends(get_current_user)):
    _ensure_table()
    if not _revoke_key(key_id, user["sub"]):
        raise HTTPException(status_code=404, detail="Key not found or already revoked.")
    logger.info(f"[APIKeys] Revoked {key_id} for {user.get('email')}")
