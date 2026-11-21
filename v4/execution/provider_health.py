"""
OrQuanta — Provider Health Service (Celery Beat Task)
======================================================
Monitors all configured GPU providers every 2 minutes.
Results are stored in the provider_health table for the dashboard.

IMPORTANT: Never exposes API credentials in results or logs.
Real vs mock provider status is always clearly distinguished.
"""
from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger("orquanta.execution.provider_health")

PIPELINE_MOCK = os.getenv("USE_REAL_PROVIDERS", "false").lower() != "true"

try:
    from .celery_app import celery_app
    from .job_db import _get_conn, PH, USE_PG
    _CELERY_AVAILABLE = True
except Exception as _e:
    logger.warning(f"[ProviderHealth] Celery not available: {_e}")
    _CELERY_AVAILABLE = False

PROVIDERS_TO_CHECK = ["runpod", "lambda", "aws", "gcp", "azure"]


if _CELERY_AVAILABLE:

    @celery_app.task(
        name="v4.execution.provider_health.check_all_providers",
        queue="orquanta.ops",
        max_retries=1,
        soft_time_limit=100,
    )
    def check_all_providers() -> dict:
        """Check health of all configured GPU providers. Store results in DB."""
        results = {}
        for provider in PROVIDERS_TO_CHECK:
            result = _check_provider(provider)
            results[provider] = result
            _persist_health(provider, result)
        return results


def _check_provider(provider: str) -> dict:
    """
    Check a single provider's health.
    Returns a health dict. Never includes credentials.
    is_real=False means no API key is configured — health reflects mock state.
    """
    t0 = time.time()
    result = {
        "provider": provider,
        "is_real": False,
        "auth_ok": False,
        "api_latency_ms": None,
        "gpu_available": None,
        "last_error": None,
    }

    try:
        if provider == "runpod":
            api_key = os.getenv("RUNPOD_API_KEY", "")
            if not api_key:
                result["last_error"] = "RUNPOD_API_KEY not configured (mock mode)"
                return result
            result["is_real"] = True
            result.update(_check_runpod(api_key, t0))

        elif provider == "lambda":
            api_key = os.getenv("LAMBDA_LABS_API_KEY", "")
            if not api_key:
                result["last_error"] = "LAMBDA_LABS_API_KEY not configured"
                return result
            result["is_real"] = True
            result.update(_check_lambda(api_key, t0))

        else:
            # AWS, GCP, Azure: check env key presence only (full health check is provider-specific)
            key_map = {
                "aws": "AWS_ACCESS_KEY_ID",
                "gcp": "GCP_PROJECT_ID",
                "azure": "AZURE_SUBSCRIPTION_ID",
            }
            env_key = key_map.get(provider)
            if env_key and os.getenv(env_key, ""):
                result["is_real"] = True
                result["auth_ok"] = True
                result["api_latency_ms"] = 0.0
                result["last_error"] = "Full health check not yet implemented for this provider"
            else:
                result["last_error"] = f"{env_key} not configured"

    except Exception as exc:
        # Strip any credential-like strings from error messages
        err_msg = str(exc)
        for secret_key in ["RUNPOD_API_KEY", "LAMBDA_LABS_API_KEY", "AWS_SECRET_ACCESS_KEY"]:
            secret_val = os.getenv(secret_key, "")
            if secret_val and secret_val in err_msg:
                err_msg = err_msg.replace(secret_val, "***REDACTED***")
        result["last_error"] = err_msg[:500]
        logger.warning(f"[ProviderHealth] {provider} health check error: {err_msg[:200]}")

    return result


def _check_runpod(api_key: str, t0: float) -> dict:
    """Check RunPod API health. Returns partial health dict."""
    import asyncio

    async def _do_check():
        try:
            import runpod as rp
            rp.api_key = api_key
            # List pods — lightweight auth + API availability test
            pods = rp.get_pods()
            latency_ms = (time.time() - t0) * 1000
            # Count GPU instances available (from pricing endpoint, not pods)
            gpu_count = 0
            try:
                gpu_types = rp.get_gpu()
                gpu_count = sum(1 for g in gpu_types if g.get("lowestPrice", {}).get("stockStatus") == "HIGH")
            except Exception:
                pass
            return {
                "auth_ok": True,
                "api_latency_ms": round(latency_ms, 1),
                "gpu_available": gpu_count,
                "last_error": None,
            }
        except Exception as exc:
            latency_ms = (time.time() - t0) * 1000
            return {
                "auth_ok": False,
                "api_latency_ms": round(latency_ms, 1),
                "gpu_available": 0,
                "last_error": str(exc)[:300],
            }

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do_check())
    finally:
        loop.close()


def _check_lambda(api_key: str, t0: float) -> dict:
    """Check Lambda Labs API health."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "https://cloud.lambdalabs.com/api/v1/instance-types",
            headers={"Authorization": f"Basic {api_key}:"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        latency_ms = (time.time() - t0) * 1000
        data = json.loads(resp.read())
        gpu_count = len(data.get("data", {}))
        return {
            "auth_ok": True,
            "api_latency_ms": round(latency_ms, 1),
            "gpu_available": gpu_count,
            "last_error": None,
        }
    except Exception as exc:
        latency_ms = (time.time() - t0) * 1000
        return {
            "auth_ok": False,
            "api_latency_ms": round(latency_ms, 1),
            "gpu_available": 0,
            "last_error": str(exc)[:300],
        }


def _persist_health(provider: str, result: dict) -> None:
    """Write a health check result to the provider_health table."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if USE_PG:
            cur.execute(
                """INSERT INTO provider_health
                   (provider, is_real, auth_ok, api_latency_ms, gpu_available, last_error, checked_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    provider,
                    result.get("is_real", False),
                    result.get("auth_ok", False),
                    result.get("api_latency_ms"),
                    result.get("gpu_available"),
                    result.get("last_error"),
                    now,
                ),
            )
        else:
            cur.execute(
                """INSERT INTO provider_health
                   (provider, is_real, auth_ok, api_latency_ms, gpu_available, last_error, checked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    provider,
                    1 if result.get("is_real") else 0,
                    1 if result.get("auth_ok") else 0,
                    result.get("api_latency_ms"),
                    result.get("gpu_available"),
                    result.get("last_error"),
                    now,
                ),
            )
        conn.commit()
    except Exception as exc:
        logger.warning(f"[ProviderHealth] Failed to persist health for {provider}: {exc}")
    finally:
        conn.close()


def get_latest_health() -> list[dict]:
    """
    Return the most recent health check for each provider.
    Safe to call from FastAPI (sync, short-lived connection).
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if USE_PG:
            cur.execute(
                """SELECT DISTINCT ON (provider)
                       provider, is_real, auth_ok, api_latency_ms, gpu_available, last_error, checked_at
                   FROM provider_health
                   ORDER BY provider, checked_at DESC"""
            )
        else:
            cur.execute(
                """SELECT provider, is_real, auth_ok, api_latency_ms, gpu_available, last_error, checked_at
                   FROM provider_health p1
                   WHERE checked_at = (
                       SELECT MAX(checked_at) FROM provider_health p2 WHERE p2.provider = p1.provider
                   )
                   GROUP BY provider"""
            )
        rows = cur.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            # Never include credentials or internal paths
            d.pop("last_error_detail", None)
            if d.get("last_error") and len(d["last_error"]) > 300:
                d["last_error"] = d["last_error"][:300] + "..."
            results.append(d)
        return results
    except Exception as exc:
        logger.warning(f"[ProviderHealth] get_latest_health failed: {exc}")
        return []
    finally:
        conn.close()
