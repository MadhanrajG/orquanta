"""
OrQuanta — Provider Health API Router
GET /api/v1/provider-health  — latest health check per provider
GET /api/v1/provider-health/{provider} — single provider health history
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..middleware.auth import get_current_user

logger = logging.getLogger("orquanta.api.provider_health")
router = APIRouter(prefix="/api/v1/provider-health", tags=["Provider Health"])


@router.get(
    "",
    summary="Get latest health status for all GPU providers",
)
async def get_provider_health(
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Returns the most recent health check result for each configured provider.
    is_real=false means no API key is configured — health reflects unavailability, not mock data.
    Health checks run every 2 minutes via Celery beat.
    """
    try:
        from ...execution.provider_health import get_latest_health
        health = get_latest_health()
        return {
            "providers": health,
            "count": len(health),
            "note": "Providers without API keys show is_real=false. Configure keys to enable real health monitoring.",
        }
    except Exception as exc:
        logger.warning(f"[ProviderHealth] API call failed: {exc}")
        return {
            "providers": [],
            "count": 0,
            "error": "Health data unavailable — Celery beat may not be running.",
        }


@router.get(
    "/{provider}",
    summary="Get health history for a specific provider",
)
async def get_single_provider_health(
    provider: str,
    limit: int = Query(20, ge=1, le=100),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Returns the last N health check results for a specific provider.
    """
    valid_providers = {"runpod", "lambda", "aws", "gcp", "azure"}
    if provider not in valid_providers:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider}'. Valid: {sorted(valid_providers)}")

    try:
        from ...execution.job_db import _get_conn, USE_PG, PH

        conn = _get_conn()
        cur = conn.cursor()
        if USE_PG:
            cur.execute(
                "SELECT provider, is_real, auth_ok, api_latency_ms, gpu_available, last_error, checked_at "
                "FROM provider_health WHERE provider = %s ORDER BY checked_at DESC LIMIT %s",
                (provider, limit),
            )
        else:
            cur.execute(
                "SELECT provider, is_real, auth_ok, api_latency_ms, gpu_available, last_error, checked_at "
                "FROM provider_health WHERE provider = ? ORDER BY checked_at DESC LIMIT ?",
                (provider, limit),
            )
        rows = cur.fetchall()
        conn.close()
        history = [dict(r) for r in rows]
        return {"provider": provider, "history": history, "count": len(history)}
    except Exception as exc:
        logger.warning(f"[ProviderHealth] History lookup failed for {provider}: {exc}")
        return {"provider": provider, "history": [], "count": 0, "error": str(exc)[:200]}
