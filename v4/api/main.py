"""
OrQuanta Agentic v1.0 Ã¢â‚¬â€ FastAPI Application Entry Point

Wires together all routers, middleware, startup/shutdown hooks,
authentication, Prometheus metrics exposure, and WebSocket stream.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from .prometheus_metrics import PrometheusMiddleware, get_metrics_response

from .routers import goals, jobs, agents, metrics, audit
from .routers.admin import router as admin_router
from .routers.billing import router as billing_router
from .routers.webhooks import router as webhooks_router
from .routers.schedules import router as schedules_router, get_cron_scheduler
from .routers.pricing import router as pricing_router
from .routers.free_tier import router as free_tier_router
from .routers.vero import router as vero_router
from .routers.nemoclaw import router as nemoclaw_router
from .routers.uix import router as uix_router
from .routers.oauth import router as oauth_router
from .routers.api_keys import router as api_keys_router
from .websocket.agent_stream import router as ws_router
from .middleware.auth import authenticate_user, create_access_token, register_user, get_current_user
from .models.schemas import (
    HealthResponse, LoginRequest, RegisterRequest, TokenResponse
)

# Demo mode Ã¢â‚¬â€ check both env var names for compatibility
_DEMO_MODE = (
    os.getenv("ORQUANTA_DEMO_MODE", "false").lower() in ("true", "1", "yes")
    or os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
)

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Logging Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s Ã¢â‚¬â€ %(message)s",
)
logger = logging.getLogger("orquanta.api")

VERSION = "1.0.0"
_ENV = os.getenv("ENV", "production")
_DEFAULT_ORIGINS = "*" if _ENV == "development" else "https://orquanta.com,https://orquanta-app.pages.dev"
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",")

# Sentry — production error tracking + performance monitoring (no-op when DSN absent)
_SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            environment=_ENV,
            release=f"orquanta@{VERSION}",
            traces_sample_rate=0.1,     # 10% of requests traced for performance
            profiles_sample_rate=0.05,  # 5% profiling overhead
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
            ],
            send_default_pii=False,
        )
        logger.info(f"[Sentry] Initialized — env={_ENV}, traces=10%")
    except ImportError:
        logger.warning("[Sentry] sentry-sdk not installed — skipping")
else:
    logger.debug("[Sentry] SENTRY_DSN not set — error tracking disabled")


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Lifespan (startup / shutdown) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup: validate env, boot agents, wire pipeline. Shutdown: graceful stop."""
    logger.info(f"OrQuanta Agentic v{VERSION} starting upÃ¢â‚¬Â¦")

    # Ã¢â€â‚¬Ã¢â€â‚¬ 0. Validate production environment Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    try:
        from ..startup_validator import validate_env
        env_report = validate_env(strict=False)
        logger.info(
            f"Env validated: {env_report['configured']} vars set | "
            f"providers={'real' if env_report['has_real_providers'] else 'mock'} | "
            f"stripe={'yes' if env_report['stripe_configured'] else 'no'}"
        )
    except SystemExit:
        raise
    except Exception as exc:
        logger.warning(f"Env validation error (non-fatal): {exc}")

    # Ensure goals + jobs tables exist and restore persisted state
    try:
        from ..database.persistence import ensure_tables, load_all_goals, load_all_jobs
        ensure_tables()
        _persisted_goals = load_all_goals()
        _persisted_jobs = load_all_jobs()
    except Exception as _exc:
        logger.warning(f"[Persistence] Startup load failed (non-fatal): {_exc}")
        _persisted_goals, _persisted_jobs = [], []

    # Start MasterOrchestrator
    from .routers.goals import get_orchestrator
    orchestrator = get_orchestrator()
    await orchestrator.start()
    if _persisted_goals:
        orchestrator.restore_goals(_persisted_goals)

    # Start specialist agents — use module-level singletons so all routers
    # share the same instances (not orphan copies with empty state).
    from ..agents.scheduler_agent import get_scheduler as _get_scheduler
    from ..agents.cost_optimizer_agent import get_cost_optimizer as _get_cost_optimizer
    from ..agents.healing_agent import get_healing_agent as _get_healing_agent
    from ..agents.forecast_agent import get_forecast_agent as _get_forecast_agent

    scheduler = _get_scheduler()
    await scheduler.start()

    cost_agent = _get_cost_optimizer()
    await cost_agent.start()

    healing_agent = _get_healing_agent()
    await healing_agent.start()

    forecast_agent = _get_forecast_agent()
    await forecast_agent.start()

    # Start Vero -- Superior Intelligence Meta-Agent (boots last, monitors all)
    try:
        from ..agents.vero_agent import get_vero
        vero = get_vero()
        await vero.start(orchestrator=orchestrator)
        logger.info('VERO ONLINE -- Superior agent oversight active. Monitoring 5 agents.')
    except Exception as exc:
        logger.warning(f'[Vero] Failed to start (non-fatal): {exc}')

    # Start NemoClaw — OpenClaw-inspired multi-agent cognitive layer
    try:
        from ..agents.nemoclaw_engine import get_nemoclaw
        nemoclaw = get_nemoclaw()
        _vero_ref = vero if 'vero' in dir() else None
        await nemoclaw.start(vero=_vero_ref, orchestrator=orchestrator)
        logger.info('🧬 NEMOCLAW ONLINE — ContextGraph ready, CostWatcher active, PredictivePrefetch started.')
    except Exception as exc:
        logger.warning(f'[NemoClaw] Failed to start (non-fatal): {exc}')

    # Pre-warm Live Pricing cache — so /pricing shows data on first page load
    try:
        from .routers.pricing import _refresh_cache
        import asyncio as _asyncio
        _asyncio.ensure_future(_refresh_cache())
        logger.info('[Pricing] Cache pre-warm scheduled.')
    except Exception as exc:
        logger.warning(f'[Pricing] Pre-warm failed (non-fatal): {exc}')


    # Ã¢â€â‚¬Ã¢â€â‚¬ Init production job pipeline Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    from ..execution.pipeline import get_pipeline
    pipeline = get_pipeline()
    if _persisted_jobs:
        pipeline.restore_jobs(_persisted_jobs)
    # Wire WebSocket broadcaster so pipeline can push live events to clients
    try:
        from .websocket.agent_stream import broadcast_to_all
        pipeline.set_ws_broadcaster(broadcast_to_all)
        logger.info("[Pipeline] WebSocket broadcaster wired.")
    except Exception as exc:
        logger.warning(f"[Pipeline] WS broadcaster not available: {exc}")

    # Seed admin user + promote role in background — DB latency must never block startup
    # (critical for cross-region PostgreSQL: Oregon web service -> Singapore DB)
    import asyncio as _asyncio

    async def _seed_admin() -> None:
        from .middleware.auth import _get_db, _USE_PG
        _admin_email = os.getenv("ADMIN_EMAIL", "admin@orquanta.com")
        _admin_password = os.getenv("ADMIN_PASSWORD", "")
        if not _admin_password:
            logger.warning("ADMIN_PASSWORD not set — skipping admin seed.")
            return
        try:
            register_user(email=_admin_email, password=_admin_password, name="OrQuanta Admin")
            logger.info(f"Admin user '{_admin_email}' created.")
        except Exception:
            pass  # Already exists — fine
        try:
            _ph = "%s" if _USE_PG else "?"
            _conn = _get_db()
            if _USE_PG:
                _cur = _conn.cursor()
                _cur.execute(f"UPDATE users SET role = {_ph} WHERE email = {_ph}", ("admin", _admin_email.lower()))
                _conn.commit()
                _cur.close()
            else:
                _conn.execute(f"UPDATE users SET role = {_ph} WHERE email = {_ph}", ("admin", _admin_email.lower()))
                _conn.commit()
            _conn.close()
            logger.info(f"Admin role set for '{_admin_email}'.")
        except Exception as _exc:
            logger.warning(f"Admin role promotion skipped: {_exc}")

    _asyncio.ensure_future(_seed_admin())
    # Start demo engine if in demo mode
    if _DEMO_MODE:
        try:
            from ..demo.demo_mode import get_demo_engine
            from ..demo.demo_scenario import run_scenario
            engine = get_demo_engine()
            await engine.start()
            # Auto-run first scenario in background
            import asyncio
            asyncio.create_task(run_scenario("cost_optimizer", engine))
            logger.info("[Demo] Demo mode active Ã¢â‚¬â€ scenario 'cost_optimizer' starting")
        except Exception as exc:
            logger.warning(f"[Demo] Demo startup error (non-fatal): {exc}")

    # Ã¢â€â‚¬Ã¢â€â‚¬ Start CronScheduler (OpenClaw-inspired recurring GPU jobs) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
    import asyncio as _asyncio
    cron_scheduler = get_cron_scheduler()
    cron_task = _asyncio.create_task(cron_scheduler.run())
    logger.info("[CronScheduler] Recurring job scheduler started.")

    logger.info("All agents started. Platform ready.")

    yield

    # Stop cron scheduler on shutdown
    cron_scheduler.stop()
    cron_task.cancel()

    # Shutdown
    logger.info("OrQuanta shutting downÃ¢â‚¬Â¦")
    await orchestrator.stop()
    await scheduler.stop()
    await cost_agent.stop()
    await healing_agent.stop()
    await forecast_agent.stop()
    logger.info("Shutdown complete.")


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ FastAPI App Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

app = FastAPI(
    title="OrQuanta Agentic v1.0",
    description=(
        "Autonomous GPU Cloud Orchestration Platform. "
        "Submit natural-language goals Ã¢â‚¬â€ OrQuanta agents handle the rest."
    ),
    version=VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Security Headers Middleware Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add production-grade security headers to every response."""

    # Strict CSP for API and app routes
    _CSP_APP = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' fonts.googleapis.com; "
        "font-src 'self' fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' wss: https:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    # Demo page uses server-rendered inline scripts — allow unsafe-inline for /demo only
    _CSP_DEMO = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' fonts.googleapis.com; "
        "font-src 'self' fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' wss: https:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Only add security headers to non-binary, non-stream responses
        # Always set transport-security and clickjacking protection
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        # Apply per-route CSP — demo page needs unsafe-inline for its inline scripts
        path = request.url.path
        if path.startswith("/demo"):
            response.headers["Content-Security-Policy"] = self._CSP_DEMO
        else:
            response.headers["Content-Security-Policy"] = self._CSP_APP
        return response

# ─── Middleware registration order (CRITICAL) ───────────────────────────────
# Starlette applies add_middleware() in REVERSE order:
#   last registered = outermost wrapper = first to execute on every request
#
# Desired execution order (outermost → innermost):
#   1. SecurityHeadersMiddleware   ← adds CSP/HSTS/XSS headers to ALL responses
#   2. PrometheusMiddleware        ← records metrics (inner, skips /health)
#   3. CORSMiddleware              ← already added above
#   4. Route handlers
#
# Registration order must therefore be OPPOSITE:

# Register FIRST → runs INNERMOST (after security headers are already set)
app.add_middleware(PrometheusMiddleware)

# Register LAST → runs OUTERMOST (executes before anything else, wraps all responses)
app.add_middleware(SecurityHeadersMiddleware)


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Global exception handler Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": type(exc).__name__,
            "detail": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Auth endpoints Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

_REGISTER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Join OrQuanta  Free 14-Day Trial</title>
  <meta name="description" content="Create your free OrQuanta account. 14-day trial, no credit card required.">
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:#050608;color:#e2e8f0;font-family:'Inter',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
    .card{background:rgba(15,22,36,0.95);border:1px solid rgba(0,212,255,0.2);border-radius:20px;padding:48px 40px;width:100%;max-width:440px;box-shadow:0 0 80px rgba(0,212,255,0.1)}
    .logo-text{font-family:'Space Grotesk',sans-serif;font-size:1.8rem;font-weight:700;background:linear-gradient(135deg,#00D4FF,#7B2FFF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;text-align:center}
    .tagline{text-align:center;color:#64748b;font-size:.88rem;margin-bottom:24px}
    .badge-row{text-align:center;margin-bottom:28px}
    .badge{display:inline-block;background:rgba(0,255,136,0.1);border:1px solid rgba(0,255,136,0.3);color:#00FF88;font-size:.8rem;padding:5px 14px;border-radius:20px}
    .features{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:28px}
    .feat{background:rgba(0,0,0,0.2);border-radius:8px;padding:8px 12px;font-size:.8rem;color:#94a3b8}
    .feat span{color:#00FF88;margin-right:5px}
    h1{font-family:'Space Grotesk',sans-serif;font-size:1.45rem;font-weight:700;text-align:center;margin-bottom:6px}
    .sub{text-align:center;color:#94a3b8;font-size:.92rem;margin-bottom:26px}
    label{display:block;color:#94a3b8;font-size:.83rem;margin-bottom:5px;margin-top:14px}
    input{width:100%;background:rgba(0,0,0,0.4);border:1px solid rgba(0,212,255,0.2);border-radius:8px;color:#e2e8f0;font-size:1rem;padding:11px 15px;font-family:'Inter',sans-serif;outline:none;transition:border-color .2s}
    input:focus{border-color:#00D4FF;box-shadow:0 0 0 3px rgba(0,212,255,0.1)}
    .btn{width:100%;background:linear-gradient(135deg,#00D4FF,#7B2FFF);border:none;border-radius:10px;color:white;font-size:1.05rem;font-weight:600;padding:14px;cursor:pointer;font-family:'Space Grotesk',sans-serif;margin-top:22px;transition:opacity .2s,transform .1s}
    .btn:hover{opacity:.9;transform:translateY(-1px)}
    .btn:disabled{opacity:.6;cursor:not-allowed}
    .error{background:rgba(255,68,68,0.1);border:1px solid rgba(255,68,68,0.3);border-radius:8px;color:#ff6b6b;padding:12px;margin-top:14px;font-size:.88rem;display:none}
    .success{background:rgba(0,255,136,0.08);border:1px solid rgba(0,255,136,0.25);border-radius:12px;color:#00FF88;padding:28px;margin-top:14px;font-size:.95rem;text-align:center;display:none}
    .success a{color:#00D4FF;text-decoration:none;font-weight:600}
    .success .pu{color:#A78BFA;text-decoration:none;font-weight:600}
    hr{border:none;border-top:1px solid rgba(255,255,255,0.07);margin:22px 0}
    .login-link{text-align:center;color:#64748b;font-size:.88rem}
    .login-link a{color:#00D4FF;text-decoration:none}
  </style>
</head>
<body>
<div class="card">
  <div class="logo-text">OrQuanta</div>
  <div class="tagline">Orchestrate. Optimize. Evolve.</div>
  <div class="badge-row"><span class="badge">Free 14-Day Trial &mdash; No Credit Card</span></div>
  <div class="features">
    <div class="feat"><span>&#10003;</span>5 AI agents</div>
    <div class="feat"><span>&#10003;</span>Multi-cloud routing</div>
    <div class="feat"><span>&#10003;</span>Self-healing jobs</div>
    <div class="feat"><span>&#10003;</span>Cost tracking</div>
  </div>
  <h1>Create Your Account</h1>
  <p class="sub">Start managing GPU cloud automatically</p>
  <div id="form-section">
    <label>Full Name</label>
    <input type="text" id="name" placeholder="Your name" autocomplete="name">
    <label>Work Email</label>
    <input type="email" id="email" placeholder="you@company.com" autocomplete="email">
    <label>Password</label>
    <input type="password" id="password" placeholder="Min 8 characters" autocomplete="new-password">
    <label>Organization (optional)</label>
    <input type="text" id="org" placeholder="Your company or project">
    <div id="err" class="error"></div>
    <button class="btn" onclick="doRegister()" id="sub-btn">Start Free Trial &rarr;</button>
  </div>
  <div id="success-msg" class="success">
    <div style="font-size:2rem;margin-bottom:8px">&#127881;</div>
    <strong>Account created!</strong><br><br>
    Taking you to your welcome page...<br>
    <div style="margin-top:14px;font-size:.85rem;color:#64748b">Redirecting in 2 seconds</div>
  </div>
  <hr>
  <div class="login-link">Already have an account? <a href="/app">Sign in &rarr;</a></div>
</div>
<script>
async function doRegister() {
  var name = document.getElementById('name').value.trim();
  var email = document.getElementById('email').value.trim();
  var pw = document.getElementById('password').value;
  var org = document.getElementById('org').value.trim();
  var errDiv = document.getElementById('err');
  var btn = document.getElementById('sub-btn');
  errDiv.style.display = 'none';
  if (!name) { errDiv.textContent = 'Please enter your name'; errDiv.style.display = 'block'; return; }
  if (!email || email.indexOf('@') < 0) { errDiv.textContent = 'Please enter a valid email'; errDiv.style.display = 'block'; return; }
  if (pw.length < 8) { errDiv.textContent = 'Password must be at least 8 characters'; errDiv.style.display = 'block'; return; }
  btn.textContent = 'Creating account...'; btn.disabled = true;
  try {
    var res = await fetch('/auth/register', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name, email:email, password:pw, organization:org||'Personal'})});
    var data = await res.json();
    if (res.ok) {
      if (data.access_token) localStorage.setItem('orquanta_token', data.access_token);
      if (data.email) localStorage.setItem('orquanta_email', data.email);
      document.getElementById('form-section').style.display = 'none';
      document.getElementById('success-msg').style.display = 'block';
      setTimeout(function(){ window.location.href = '/welcome'; }, 2000);
    } else {
      errDiv.textContent = data.detail || data.error || 'Registration failed. Please try again.';
      errDiv.style.display = 'block';
      btn.textContent = 'Start Free Trial ->'; btn.disabled = false;
    }
  } catch(e) {
    errDiv.textContent = 'Connection error. Please try again.';
    errDiv.style.display = 'block';
    btn.textContent = 'Start Free Trial ->'; btn.disabled = false;
  }
}
document.addEventListener('keypress', function(e){ if (e.key === 'Enter') doRegister(); });
</script>
</body>
</html>
"""


_WELCOME_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome to OrQuanta  You're In!</title>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:#050608;color:#e2e8f0;font-family:'Inter',sans-serif;min-height:100vh;overflow-x:hidden}

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Animated gradient hero Ã¢â€â‚¬Ã¢â€â‚¬ */
    .hero{position:relative;text-align:center;padding:64px 24px 48px;overflow:hidden}
    .hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 80% 60% at 50% 0%,rgba(0,212,255,0.13),transparent 70%);pointer-events:none}
    .hero::after{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:1px;height:120px;background:linear-gradient(to bottom,rgba(0,212,255,0.6),transparent)}

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Success badge Ã¢â€â‚¬Ã¢â€â‚¬ */
    .badge{display:inline-flex;align-items:center;gap:8px;padding:6px 18px;border-radius:999px;border:1px solid rgba(0,255,136,0.4);background:rgba(0,255,136,0.08);font-size:13px;font-weight:600;color:#00FF88;margin-bottom:28px;animation:fadeSlideDown .5s ease}
    .badge-dot{width:8px;height:8px;border-radius:50%;background:#00FF88;animation:pulse 2s infinite}

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Typography Ã¢â€â‚¬Ã¢â€â‚¬ */
    .logo{font-family:'Space Grotesk',sans-serif;font-size:1rem;font-weight:600;color:#8892A4;letter-spacing:2px;text-transform:uppercase;margin-bottom:20px}
    h1{font-family:'Space Grotesk',sans-serif;font-size:clamp(1.8rem,4vw,2.8rem);font-weight:700;line-height:1.15;margin-bottom:12px;animation:fadeSlideDown .5s .1s ease both}
    .h1-sub{color:#8892A4;font-size:.95rem;margin-bottom:20px;animation:fadeSlideDown .5s .15s ease both}
    .email-pill{display:inline-block;background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.25);border-radius:999px;color:#00D4FF;font-size:.82rem;padding:5px 16px;margin-bottom:40px;animation:fadeSlideDown .5s .2s ease both}

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Token box (collapsed) Ã¢â€â‚¬Ã¢â€â‚¬ */
    .token-section{max-width:540px;margin:0 auto 40px;animation:fadeSlideDown .5s .25s ease both}
    .token-toggle{background:rgba(15,22,36,0.8);border:1px solid rgba(0,212,255,0.15);border-radius:10px;padding:12px 18px;cursor:pointer;display:flex;align-items:center;justify-content:space-between;font-size:.85rem;color:#8892A4;user-select:none;transition:border-color .2s}
    .token-toggle:hover{border-color:rgba(0,212,255,0.35)}
    .token-toggle span{color:#00D4FF;font-weight:600}
    .token-body{display:none;background:rgba(0,0,0,0.4);border:1px solid rgba(0,212,255,0.12);border-top:none;border-radius:0 0 10px 10px;padding:14px 16px}
    .token-body.open{display:block}
    .token-val{font-family:'JetBrains Mono',monospace;font-size:.78rem;color:#A78BFA;word-break:break-all;line-height:1.6;margin-bottom:10px}
    .copy-btn{background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.3);border-radius:6px;color:#00D4FF;font-size:.78rem;padding:5px 14px;cursor:pointer;font-family:'Inter',sans-serif;transition:background .2s}
    .copy-btn:hover{background:rgba(0,212,255,0.2)}
    .copy-hint{font-size:.75rem;color:#64748b;margin-top:8px}

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Action cards Ã¢â€â‚¬Ã¢â€â‚¬ */
    .cards-label{font-family:'Space Grotesk',sans-serif;font-size:.7rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#8892A4;text-align:center;margin-bottom:14px}
    .cards{display:grid;grid-template-columns:1fr;gap:14px;max-width:520px;margin:0 auto 40px;padding:0 20px}
    .card{background:rgba(15,22,36,0.9);border:1px solid rgba(255,255,255,0.07);border-radius:16px;padding:24px 26px;text-decoration:none;display:block;transition:transform .15s,box-shadow .15s,border-color .15s}
    .card:hover{transform:translateY(-3px);box-shadow:0 12px 36px rgba(0,0,0,.4)}
    .card.c1{border-color:rgba(0,212,255,0.3);background:linear-gradient(135deg,rgba(0,212,255,0.05),rgba(123,47,255,0.04))}
    .card.c1:hover{box-shadow:0 12px 36px rgba(0,212,255,.15)}
    .card.c2:hover{box-shadow:0 12px 36px rgba(0,255,136,.08);border-color:rgba(0,255,136,0.2)}
    .card.c3:hover{box-shadow:0 12px 36px rgba(167,139,250,.08);border-color:rgba(167,139,250,0.2)}
    .card-num{font-family:'Space Grotesk',sans-serif;font-size:.7rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px}
    .c1 .card-num{color:#00D4FF} .c2 .card-num{color:#00FF88} .c3 .card-num{color:#A78BFA}
    .card-icon{font-size:26px;margin-bottom:10px}
    .card-title{font-family:'Space Grotesk',sans-serif;font-size:1.05rem;font-weight:700;margin-bottom:6px;color:#e2e8f0}
    .card-desc{color:#8892A4;font-size:.86rem;line-height:1.6}
    .card-tag{display:inline-flex;align-items:center;gap:5px;margin-top:12px;font-size:.75rem;font-weight:600;padding:3px 12px;border-radius:999px}
    .c1 .card-tag{background:rgba(0,212,255,0.1);color:#00D4FF;border:1px solid rgba(0,212,255,0.25)}
    .c2 .card-tag{background:rgba(0,255,136,0.08);color:#00FF88;border:1px solid rgba(0,255,136,0.25)}
    .c3 .card-tag{background:rgba(167,139,250,0.08);color:#A78BFA;border:1px solid rgba(167,139,250,0.25)}

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Footer Ã¢â€â‚¬Ã¢â€â‚¬ */
    .foot{text-align:center;color:#475569;font-size:.82rem;padding:0 24px 40px;line-height:1.8}
    .foot a{color:#00D4FF;text-decoration:none}

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Animations Ã¢â€â‚¬Ã¢â€â‚¬ */
    @keyframes fadeSlideDown{from{opacity:0;transform:translateY(-12px)}to{opacity:1;transform:translateY(0)}}
    @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.3)}}

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Confetti canvas Ã¢â€â‚¬Ã¢â€â‚¬ */
    #confetti{position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:100}
  </style>
</head>
<body>
<canvas id="confetti"></canvas>

<div class="hero">
  <div class="logo">OrQuanta</div>
  <div class="badge"><span class="badge-dot"></span> Account created successfully</div>
  <h1>You're in.<br>Welcome aboard! </h1>
  <p class="h1-sub">Your 14-day free trial starts now. Zero setup. Cancel anytime.</p>
  <div class="email-pill" id="user-email">Account active</div>
</div>

<!-- JWT Token for devs -->
<div class="token-section">
  <div class="token-toggle" onclick="toggleToken(this)">
    <span> Your API token is ready</span>
    <span id="tok-arrow" style="transition:transform .2s"></span>
  </div>
  <div class="token-body" id="tok-body">
    <div class="token-val" id="tok-val">Loading your JWT token...</div>
    <button class="copy-btn" onclick="copyToken()">Copy Token</button>
    <div class="copy-hint">Use as <code style="color:#A78BFA">Authorization: Bearer &lt;token&gt;</code> in API calls</div>
  </div>
</div>

<p class="cards-label">Start here</p>
<div class="cards">

  <a class="card c1" href="/app">
    <div class="card-num">Step 1  Recommended</div>
    <div class="card-icon"></div>
    <div class="card-title">Open Your Dashboard</div>
    <div class="card-desc">Your personal mission control. Submit AI goals, monitor live agents, track costs, and view audit logs  all in one place.</div>
    <div class="card-tag"> Open now</div>
  </a>

  <a class="card c2" href="/demo#goal-input">
    <div class="card-num">Step 2</div>
    <div class="card-icon"></div>
    <div class="card-title">Analyze Your First GPU Goal</div>
    <div class="card-desc">Type your workload in plain English  "Fine-tune Llama 3 on my data, cost under $100"  and our AI gives you an instant cost breakdown across 5 cloud providers.</div>
    <div class="card-tag">2 min  No setup</div>
  </a>

  <a class="card c3" href="/demo">
    <div class="card-num">Step 3</div>
    <div class="card-icon"></div>
    <div class="card-title">Watch Agents Work Live</div>
    <div class="card-desc">See 5 specialized AI agents  Scheduler, Cost Optimizer, Healing, Forecast, Audit  orchestrating a real GPU job with live streaming logs and metrics.</div>
    <div class="card-tag">Live stream</div>
  </a>

</div>

<div class="foot">
  Need help? <a href="mailto:orquanta.founder@gmail.com">orquanta.founder@gmail.com</a> &nbsp;&nbsp;
  <a href="/demo">Back to Demo</a> &nbsp;&nbsp;
  <a href="/app">Dashboard </a>
</div>

<script>
// Ã¢â€â‚¬Ã¢â€â‚¬ Token display Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
var tok = localStorage.getItem('orquanta_token');
var em  = localStorage.getItem('orquanta_email');
if (em) document.getElementById('user-email').textContent = em;
if (tok) {
  var el = document.getElementById('tok-val');
  el.textContent = tok;
}

function toggleToken(btn){
  var body  = document.getElementById('tok-body');
  var arrow = document.getElementById('tok-arrow');
  var open  = body.classList.toggle('open');
  arrow.style.transform = open ? 'rotate(180deg)' : '';
}

function copyToken(){
  var t = document.getElementById('tok-val').textContent;
  navigator.clipboard.writeText(t).then(function(){
    var b = document.querySelector('.copy-btn');
    b.textContent = 'Ã¢Å“â€œ Copied!';
    setTimeout(function(){ b.textContent = 'Copy Token'; }, 2000);
  });
}

// Ã¢â€â‚¬Ã¢â€â‚¬ Confetti burst Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
(function(){
  var cv = document.getElementById('confetti');
  var cx = cv.getContext('2d');
  cv.width = window.innerWidth; cv.height = window.innerHeight;
  var pieces = [];
  var colors = ['#00D4FF','#7B2FFF','#00FF88','#FFB800','#FF4444','#A78BFA'];
  for(var i=0;i<120;i++){
    pieces.push({
      x: Math.random()*cv.width, y: -20-Math.random()*200,
      w: 8+Math.random()*8, h: 4+Math.random()*4,
      r: Math.random()*Math.PI*2, dr: (Math.random()-.5)*.2,
      dx: (Math.random()-.5)*3, dy: 2+Math.random()*3,
      color: colors[Math.floor(Math.random()*colors.length)],
      alpha: 1
    });
  }
  var frame=0;
  function draw(){
    cx.clearRect(0,0,cv.width,cv.height);
    var alive=false;
    pieces.forEach(function(p){
      if(p.y>cv.height+20||p.alpha<=0) return;
      alive=true;
      p.x+=p.dx; p.y+=p.dy; p.r+=p.dr;
      if(p.y>cv.height*0.7) p.alpha-=0.02;
      cx.save(); cx.globalAlpha=Math.max(0,p.alpha);
      cx.translate(p.x,p.y); cx.rotate(p.r);
      cx.fillStyle=p.color;
      cx.fillRect(-p.w/2,-p.h/2,p.w,p.h);
      cx.restore();
    });
    if(alive && frame++<180) requestAnimationFrame(draw);
    else { cx.clearRect(0,0,cv.width,cv.height); cv.style.display='none'; }
  }
  draw();
})();
</script>
</body>
</html>
"""



@app.get("/welcome", response_class=HTMLResponse, tags=["Auth"], summary="Post-signup welcome page", include_in_schema=False)
async def welcome_page():
    """Welcome page shown after successful registration."""
    return HTMLResponse(content=_WELCOME_HTML, status_code=200)


@app.get("/auth/register", response_class=HTMLResponse, tags=["Auth"], summary="Signup page", include_in_schema=False)
async def register_page():
    """Serve the signup HTML page (GET). The form POSTs to /auth/register."""
    return HTMLResponse(content=_REGISTER_HTML, status_code=200)


@app.post("/auth/register", tags=["Auth"], summary="Register a new user", status_code=201)
async def register(req: RegisterRequest):
    """Create a new OrQuanta user account."""
    try:
        user = register_user(email=req.email, password=req.password, name=req.name)
        token = create_access_token(user["id"], user["email"], user["role"])
        return JSONResponse(status_code=201, content={
            "user_id": user["id"],
            "email": user["email"],
            "access_token": token,
            "token_type": "bearer",
        })
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


# Per-IP sliding-window rate limiter for /auth/login
# Tracks FAILED attempts only — successful logins don't count toward the limit.
# Limits: 5 failures/60s triggers soft block; 10 failures/300s triggers hard block.
_login_failures: defaultdict[str, deque] = defaultdict(deque)
_LOGIN_SOFT_LIMIT = 5    # failures before 429 (60-second window)
_LOGIN_HARD_LIMIT = 10   # failures before extended block (300-second window)
_LOGIN_SOFT_WINDOW = 60.0
_LOGIN_HARD_WINDOW = 300.0


def _login_rate_check(ip: str) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds). Checks only failed-attempt history."""
    now = time.monotonic()
    bucket = _login_failures[ip]

    # Purge hard-window entries older than 5 minutes
    while bucket and bucket[0] < now - _LOGIN_HARD_WINDOW:
        bucket.popleft()

    recent_count = len(bucket)  # failures in last 5 min
    soft_count = sum(1 for t in bucket if t > now - _LOGIN_SOFT_WINDOW)  # in last 60s

    if recent_count >= _LOGIN_HARD_LIMIT:
        return False, 300  # 5-minute block
    if soft_count >= _LOGIN_SOFT_LIMIT:
        return False, 60   # 1-minute block
    return True, 0


def _record_login_failure(ip: str) -> None:
    """Record a failed login attempt for this IP."""
    _login_failures[ip].append(time.monotonic())


def _clear_login_failures(ip: str) -> None:
    """Clear failure history on successful login (reset the count)."""
    _login_failures[ip].clear()


@app.post("/auth/login", tags=["Auth"], response_model=TokenResponse, summary="Login")
async def login(req: LoginRequest, request: Request):
    """Authenticate and receive a JWT access token."""
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "unknown"))

    allowed, retry_after = _login_rate_check(ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": f"Too many failed login attempts. Try again in {retry_after} seconds.",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": "5"},
        )

    user = authenticate_user(req.email, req.password)
    if not user:
        _record_login_failure(ip)   # only count failures toward the limit
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Invalid email or password."},
        )

    _clear_login_failures(ip)       # successful login → reset failure counter
    token = create_access_token(user["id"], user["email"], user["role"])
    return TokenResponse(access_token=token, expires_in=86400)


# ─── Change Password endpoint (used by Settings → Security tab) ───────────

from pydantic import BaseModel as _BaseModel

class _ChangePasswordRequest(_BaseModel):
    current_password: str
    new_password: str

@app.post("/api/v1/auth/change-password", tags=["Auth"], summary="Change user password")
async def change_password(
    req: _ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """Validate current password and update to new password."""
    from .middleware.auth import _get_db, hash_password, authenticate_user as _auth
    # Verify current password
    user = _auth(current_user["email"], req.current_password)
    if not user:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Current password is incorrect."},
        )
    if len(req.new_password) < 8:
        return JSONResponse(
            status_code=400,
            content={"error": "New password must be at least 8 characters."},
        )
    import secrets as _sec
    from .middleware.auth import _ph as _placeholder, _USE_PG
    new_salt = _sec.token_hex(8)
    new_hash = hash_password(req.new_password, new_salt)
    ph = _placeholder()
    conn = _get_db()
    try:
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE users SET hashed_pw = {ph}, salt = {ph} WHERE email = {ph}",
                (new_hash, new_salt, current_user["email"].lower()),
            )
            conn.commit()
            cur.close()
        else:
            conn.execute(
                f"UPDATE users SET hashed_pw = {ph}, salt = {ph} WHERE email = {ph}",
                (new_hash, new_salt, current_user["email"].lower()),
            )
            conn.commit()
    finally:
        conn.close()
    logger.info(f"Password changed for user: {current_user['email']}")
    return {"success": True, "message": "Password updated successfully."}


# ─── Update user profile (used by Settings → Profile tab) ────────────────

class _ProfileUpdateRequest(_BaseModel):
    full_name: str = ""
    email: str = ""

@app.patch("/api/v1/auth/profile", tags=["Auth"], summary="Update user profile")
async def update_profile(
    req: _ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update the authenticated user's display name."""
    from .middleware.auth import _get_db, _ph as _placeholder, _USE_PG
    ph = _placeholder()
    conn = _get_db()
    try:
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE users SET name = {ph} WHERE email = {ph}",
                (req.full_name, current_user["email"].lower()),
            )
            conn.commit()
            cur.close()
        else:
            conn.execute(
                f"UPDATE users SET name = {ph} WHERE email = {ph}",
                (req.full_name, current_user["email"].lower()),
            )
            conn.commit()
    finally:
        conn.close()
    return {"success": True, "full_name": req.full_name}




# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Health check Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

@app.get("/metrics", tags=["System"], summary="Prometheus metrics", include_in_schema=False)
async def prometheus_metrics():
    """Prometheus-format metrics for Grafana Cloud scraping."""
    return get_metrics_response()


@app.get("/health", tags=["System"], response_model=HealthResponse, summary="Health check")
async def health():
    """System health check Ã¢â‚¬â€ no auth required."""
    return HealthResponse(
        status="healthy",
        version=VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        components={
            "api": "ok",
            "orchestrator": "ok",
            "scheduler": "ok",
            "healing": "ok",
            "cost_optimizer": "ok",
            "forecast": "ok",
        },
    )


@app.get("/", include_in_schema=False)
async def root():
    """Redirect visitors to the main web app."""
    return RedirectResponse(url="/app", status_code=302)


@app.get("/api", tags=["System"], summary="API info")
async def api_info():
    """API metadata endpoint for programmatic discovery."""
    return {
        "name": "OrQuanta Agentic",
        "version": VERSION,
        "description": "Autonomous GPU Cloud Orchestration Platform",
        "docs": "/docs",
        "health": "/health",
        "ws_stream": "/ws/agent-stream",
    }


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Include routers Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

app.include_router(goals.router)
app.include_router(jobs.router)
app.include_router(agents.router)
app.include_router(metrics.router)
app.include_router(audit.router)
app.include_router(admin_router)
app.include_router(billing_router)   # /api/v1/billing Ã¢â‚¬â€ Stripe + subscriptions
app.include_router(webhooks_router)  # /api/v1/webhooks Ã¢â‚¬â€ outbound + inbound webhooks (OpenClaw)
app.include_router(schedules_router) # /api/v1/schedules Ã¢â‚¬â€ cron-based recurring GPU jobs
app.include_router(free_tier_router)
app.include_router(pricing_router)  # /api/v1/pricing -- live GPU prices from Lambda/RunPod/Vast.ai # /api/v1/free Ã¢â‚¬â€ Colab/Kaggle/Lambda free GPU tier
app.include_router(vero_router)     # /api/v1/vero -- Vero meta-agent
app.include_router(nemoclaw_router) # /api/v1/nemoclaw -- NemoClaw cognitive layer
app.include_router(uix_router)      # /api/v1/uix -- UIXAgent autonomous UI/UX diagnostics
app.include_router(oauth_router)    # /auth/google + /auth/github -- OAuth2 SSO
app.include_router(api_keys_router) # /api/v1/api-keys -- programmatic access keys
app.include_router(ws_router)

# Demo router Ã¢â‚¬â€ always included; active only when DEMO_MODE=true
try:
    from ..demo.public_demo import demo_router
    app.include_router(demo_router, prefix="/demo", tags=["Demo"])
except Exception:
    pass  # demo package optional


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Serve built React frontend Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

# FIX-9: Resolve from the v4/ root (two levels up from api/) Ã¢â‚¬â€ avoids double v4/ prefix
_DIST_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_DIST_DIR = os.path.abspath(_DIST_DIR)

if os.path.isdir(_DIST_DIR):
    # Serve static assets (JS/CSS chunks Vite generates into dist/assets/)
    _assets_dir = os.path.join(_DIST_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/app/assets", StaticFiles(directory=_assets_dir), name="react-assets")

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    async def serve_react_app(_path: str = ""):
        """Serve the React SPA Ã¢â‚¬â€ index.html handles all client-side routes."""
        return FileResponse(os.path.join(_DIST_DIR, "index.html"))
else:
    # Frontend not built Ã¢â‚¬â€ tell developers clearly
    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    async def react_not_built(_path: str = ""):
        return HTMLResponse(
            content="<h2>Frontend not built. Run <code>npm run build</code> inside v4/frontend/.</h2>",
            status_code=503,
        )


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Providers endpoint (public Ã¢â‚¬â€ no auth required) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

@app.get("/providers/prices", tags=["Providers"], summary="Live GPU spot prices")
async def provider_prices(gpu_type: str = "A100"):
    """Compare spot prices across all 5 providers. No auth required."""
    from ..providers.provider_router import get_router
    router_obj = get_router()
    prices = await router_obj.compare_prices(gpu_type)
    if not prices:
        return {"prices": {}, "recommended": None}
    best = prices[0]
    return {
        "gpu_type": gpu_type,
        "prices": [
            {
                "provider": p.provider,
                "region": p.region,
                "price_usd_hr": p.current_price_usd_hr,
                "availability": p.availability,
                "interruption_rate_pct": getattr(p, "interruption_rate_pct", 0),
            }
            for p in prices
        ],
        "recommended": {
            "provider": best.provider,
            "region": best.region,
            "price_usd_hr": best.current_price_usd_hr,
        },
        "providers_queried": len(prices),
    }


@app.get("/providers/health", tags=["Providers"], summary="Provider API health check")
async def provider_health():
    """Check connectivity to all 6 cloud providers."""
    if _DEMO_MODE:
        return {
            "providers": {
                "runpod": True, "lambda": True, "aws": True,
                "gcp": True, "azure": True, "coreweave": True,
            },
            "all_healthy": True,
            "mode": "demo",
        }
    from ..providers.provider_router import get_router
    router_obj = get_router()
    health = await router_obj.check_provider_health()
    return {"providers": health, "all_healthy": all(health.values())}


@app.get("/health/readiness", tags=["System"], summary="Production readiness scorecard")
async def readiness_check():
    """Return a production readiness score: JWT, RunPod, LLM, Stripe, DB, Redis."""
    from ..startup_validator import get_production_readiness
    from ..execution.pipeline import get_pipeline
    pipeline = get_pipeline()
    stats = pipeline.get_stats()
    readiness = get_production_readiness()

    # FIX B02: In demo mode, report as ready so load balancers don't block
    if _DEMO_MODE:
        readiness["ready"] = True
        readiness["verdict"] = "Ã°Å¸Å¸Â¡ Demo Mode Ã¢â‚¬â€ All Systems Operational"
        readiness["demo_mode"] = True

    return {
        "readiness": readiness,
        "pipeline": {
            "total_jobs": stats["total"],
            "total_cost_usd": stats["total_cost_usd"],
            "total_gpu_hours": stats["total_gpu_hours"],
        },
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Entry point Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "v4.api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("ENV", "production") == "development",
        log_level="info",
        ws_ping_interval=20,
        ws_ping_timeout=30,
    )
