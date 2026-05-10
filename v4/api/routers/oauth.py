"""
OrQuanta — Google + GitHub OAuth2 Routes

/auth/google/login    → redirect to Google consent screen
/auth/google/callback → exchange code, create/find user, issue JWT → redirect /app?token=xxx
/auth/github/login    → redirect to GitHub consent screen
/auth/github/callback → same

No authlib required — uses httpx (already in requirements).
State parameter is HMAC-signed to prevent CSRF.

Required env vars (optional — routes return 302 to /app?error=not_configured if absent):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
  GITHUB_CLIENT_ID,  GITHUB_CLIENT_SECRET
  APP_URL (default: https://orquanta.com)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

import httpx
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

logger = logging.getLogger("orquanta.oauth")

router = APIRouter(prefix="/auth", tags=["auth"])

_JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("JWT_SECRET_KEY", "dev-secret"))
_APP_URL = os.getenv("APP_URL", "https://orquanta.com")

_GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
_GOOGLE_AUTH_URL      = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL     = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL  = "https://www.googleapis.com/oauth2/v3/userinfo"

_GITHUB_CLIENT_ID     = os.getenv("GITHUB_CLIENT_ID", "")
_GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
_GITHUB_AUTH_URL      = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL     = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL      = "https://api.github.com/user"
_GITHUB_EMAILS_URL    = "https://api.github.com/user/emails"


# ─── CSRF state helpers ────────────────────────────────────────────────────────

def _make_state(provider: str) -> str:
    data = json.dumps({"p": provider, "ts": int(time.time()), "n": secrets.token_hex(4)})
    sig = hmac.new(_JWT_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{data}|{sig}".encode()).decode()


def _verify_state(state: str, provider: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(state.encode()).decode()
        data_str, sig = decoded.rsplit("|", 1)
        expected = hmac.new(_JWT_SECRET.encode(), data_str.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return False
        data = json.loads(data_str)
        return data.get("p") == provider and abs(time.time() - data.get("ts", 0)) < 300
    except Exception:
        return False


def _err(msg: str) -> RedirectResponse:
    return RedirectResponse(url=f"{_APP_URL}/app?error={msg}", status_code=302)


# ─── Google ────────────────────────────────────────────────────────────────────

@router.get("/google/login", include_in_schema=False)
async def google_login():
    """Redirect user to Google consent screen."""
    if not _GOOGLE_CLIENT_ID:
        return _err("google_not_configured")
    state = _make_state("google")
    cb = f"{_APP_URL}/auth/google/callback"
    url = (
        f"{_GOOGLE_AUTH_URL}?client_id={_GOOGLE_CLIENT_ID}"
        f"&redirect_uri={cb}&response_type=code"
        f"&scope=openid+email+profile&state={state}&access_type=offline"
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/google/callback", include_in_schema=False)
async def google_callback(code: str = "", state: str = "", error: str = ""):
    """Exchange Google auth code for JWT and redirect to app."""
    if error or not code:
        return _err(error or "google_auth_failed")
    if not _verify_state(state, "google"):
        return _err("invalid_state")

    cb = f"{_APP_URL}/auth/google/callback"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            tr = await c.post(_GOOGLE_TOKEN_URL, data={
                "code": code, "client_id": _GOOGLE_CLIENT_ID,
                "client_secret": _GOOGLE_CLIENT_SECRET,
                "redirect_uri": cb, "grant_type": "authorization_code",
            })
            if tr.status_code != 200:
                logger.warning(f"[OAuth/Google] token exchange failed: {tr.text[:200]}")
                return _err("google_token_failed")
            access_token = tr.json().get("access_token", "")

            ur = await c.get(_GOOGLE_USERINFO_URL,
                             headers={"Authorization": f"Bearer {access_token}"})
            if ur.status_code != 200:
                return _err("google_userinfo_failed")
            info = ur.json()
    except Exception as exc:
        logger.error(f"[OAuth/Google] HTTP error: {exc}")
        return _err("google_http_error")

    email = info.get("email", "")
    if not email:
        return _err("google_no_email")

    try:
        token = _get_or_create_oauth_user(email, info.get("name", ""), "google")
        logger.info(f"[OAuth/Google] Login: {email}")
        return RedirectResponse(url=f"{_APP_URL}/app?token={token}", status_code=302)
    except Exception as exc:
        logger.error(f"[OAuth/Google] user create failed: {exc}")
        return _err("user_create_failed")


# ─── GitHub ────────────────────────────────────────────────────────────────────

@router.get("/github/login", include_in_schema=False)
async def github_login():
    """Redirect user to GitHub consent screen."""
    if not _GITHUB_CLIENT_ID:
        return _err("github_not_configured")
    state = _make_state("github")
    cb = f"{_APP_URL}/auth/github/callback"
    url = (
        f"{_GITHUB_AUTH_URL}?client_id={_GITHUB_CLIENT_ID}"
        f"&redirect_uri={cb}&scope=user:email&state={state}"
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/github/callback", include_in_schema=False)
async def github_callback(code: str = "", state: str = "", error: str = ""):
    """Exchange GitHub auth code for JWT and redirect to app."""
    if error or not code:
        return _err(error or "github_auth_failed")
    if not _verify_state(state, "github"):
        return _err("invalid_state")

    cb = f"{_APP_URL}/auth/github/callback"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            tr = await c.post(_GITHUB_TOKEN_URL, data={
                "code": code, "client_id": _GITHUB_CLIENT_ID,
                "client_secret": _GITHUB_CLIENT_SECRET,
                "redirect_uri": cb,
            }, headers={"Accept": "application/json"})
            if tr.status_code != 200:
                return _err("github_token_failed")
            access_token = tr.json().get("access_token", "")
            if not access_token:
                return _err("github_token_empty")

            gh_headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            pr = await c.get(_GITHUB_USER_URL, headers=gh_headers)
            if pr.status_code != 200:
                return _err("github_profile_failed")
            profile = pr.json()

            # Fetch primary verified email if not public
            email = profile.get("email", "")
            if not email:
                er = await c.get(_GITHUB_EMAILS_URL, headers=gh_headers)
                if er.status_code == 200:
                    for e in er.json():
                        if isinstance(e, dict) and e.get("primary") and e.get("verified"):
                            email = e["email"]
                            break
    except Exception as exc:
        logger.error(f"[OAuth/GitHub] HTTP error: {exc}")
        return _err("github_http_error")

    if not email:
        return _err("github_no_email")

    try:
        name = profile.get("name", "") or profile.get("login", "")
        token = _get_or_create_oauth_user(email, name, "github")
        logger.info(f"[OAuth/GitHub] Login: {email}")
        return RedirectResponse(url=f"{_APP_URL}/app?token={token}", status_code=302)
    except Exception as exc:
        logger.error(f"[OAuth/GitHub] user create failed: {exc}")
        return _err("user_create_failed")


# ─── Shared helper ─────────────────────────────────────────────────────────────

def _get_or_create_oauth_user(email: str, name: str, provider: str) -> str:
    """Find existing user or create new one; return signed JWT."""
    from ..middleware.auth import (
        _get_db, _USE_PG, _ph, create_access_token, register_user,
    )
    email = email.strip().lower()
    ph = _ph()

    # Look up existing user
    conn = _get_db()
    try:
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(f"SELECT id, role FROM users WHERE email = {ph}", (email,))
            row = cur.fetchone()
            cur.close()
        else:
            row = conn.execute(
                f"SELECT id, role FROM users WHERE email = {ph}", (email,)
            ).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()

    if row:
        row = dict(row)
        return create_access_token(user_id=row["id"], email=email, role=row.get("role", "user"))

    # New user — assign a random unguessable password (OAuth users never need it)
    user = register_user(
        email=email,
        password=secrets.token_urlsafe(32),
        name=name or email.split("@")[0],
    )
    logger.info(f"[OAuth/{provider}] Created new user: {email}")
    return create_access_token(user_id=user["id"], email=email, role="user")
