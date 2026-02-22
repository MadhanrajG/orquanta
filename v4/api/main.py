"""
OrQuanta Agentic v1.0 — FastAPI Application Entry Point

Wires together all routers, middleware, startup/shutdown hooks,
authentication, Prometheus metrics exposure, and WebSocket stream.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .routers import goals, jobs, agents, metrics, audit
from .routers.admin import router as admin_router
from .websocket.agent_stream import router as ws_router
from .middleware.auth import authenticate_user, create_access_token, register_user
from .models.schemas import (
    HealthResponse, LoginRequest, RegisterRequest, TokenResponse
)

# Demo mode — check both env var names for compatibility
_DEMO_MODE = (
    os.getenv("ORQUANTA_DEMO_MODE", "false").lower() in ("true", "1", "yes")
    or os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
)

# ─── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("orquanta.api")

VERSION = "1.0.0"
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")


# ─── Lifespan (startup / shutdown) ────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: boot agents. Shutdown: graceful stop."""
    logger.info(f"OrQuanta Agentic v{VERSION} starting up…")

    # Start MasterOrchestrator
    from .routers.goals import get_orchestrator
    orchestrator = get_orchestrator()
    await orchestrator.start()

    # Start specialist agents
    from ..agents.scheduler_agent import SchedulerAgent
    from ..agents.cost_optimizer_agent import CostOptimizerAgent
    from ..agents.healing_agent import HealingAgent
    from ..agents.forecast_agent import ForecastAgent

    scheduler = SchedulerAgent()
    await scheduler.start()

    cost_agent = CostOptimizerAgent()
    await cost_agent.start()

    healing_agent = HealingAgent()
    await healing_agent.start()

    forecast_agent = ForecastAgent()
    await forecast_agent.start()

    # Seed a default admin user for first-boot
    try:
        register_user(
            email=os.getenv("ADMIN_EMAIL", "admin@orquanta.ai"),
            password=os.getenv("ADMIN_PASSWORD", "orquanta-admin-2026"),
            name="OrQuanta Admin",
        )
        # Promote to admin role
        from .middleware.auth import _USERS
        admin_email = os.getenv("ADMIN_EMAIL", "admin@orquanta.ai")
        if admin_email in _USERS:
            _USERS[admin_email]["role"] = "admin"
        logger.info("Default admin user created.")
    except ValueError:
        pass  # Already registered

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
            logger.info("[Demo] Demo mode active — scenario 'cost_optimizer' starting")
        except Exception as exc:
            logger.warning(f"[Demo] Demo startup error (non-fatal): {exc}")

    logger.info("All agents started. Platform ready.")

    yield

    # Shutdown
    logger.info("OrQuanta shutting down…")
    await orchestrator.stop()
    await scheduler.stop()
    await cost_agent.stop()
    await healing_agent.stop()
    await forecast_agent.stop()
    logger.info("Shutdown complete.")


# ─── FastAPI App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="OrQuanta Agentic v1.0",
    description=(
        "Autonomous GPU Cloud Orchestration Platform. "
        "Submit natural-language goals — OrQuanta agents handle the rest."
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


# ─── Security Headers Middleware ──────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add production-grade security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        return response

app.add_middleware(SecurityHeadersMiddleware)


# ─── Global exception handler ─────────────────────────────────────────────

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


# ─── Auth endpoints ────────────────────────────────────────────────────────

@app.post("/auth/register", tags=["Auth"], summary="Register a new user")
async def register(req: RegisterRequest):
    """Create a new OrQuanta user account."""
    try:
        user = register_user(email=req.email, password=req.password, name=req.name)
        token = create_access_token(user["id"], user["email"], user["role"])
        return {
            "user_id": user["id"],
            "email": user["email"],
            "access_token": token,
            "token_type": "bearer",
        }
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/auth/login", tags=["Auth"], response_model=TokenResponse, summary="Login")
async def login(req: LoginRequest):
    """Authenticate and receive a JWT access token."""
    user = authenticate_user(req.email, req.password)
    if not user:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Invalid email or password."},
        )
    token = create_access_token(user["id"], user["email"], user["role"])
    return TokenResponse(access_token=token, expires_in=86400)


# ─── Health check ─────────────────────────────────────────────────────────

@app.get("/health", tags=["System"], response_model=HealthResponse, summary="Health check")
async def health():
    """System health check — no auth required."""
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
    """Redirect visitors to the demo landing page."""
    return RedirectResponse(url="/demo", status_code=302)


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


# ─── Include routers ──────────────────────────────────────────────────────

app.include_router(goals.router)
app.include_router(jobs.router)
app.include_router(agents.router)
app.include_router(metrics.router)
app.include_router(audit.router)
app.include_router(admin_router)
app.include_router(ws_router)

# Demo router — always included; active only when DEMO_MODE=true
try:
    from ..demo.public_demo import demo_router
    app.include_router(demo_router, prefix="/demo", tags=["Demo"])
except Exception:
    pass  # demo package optional


# ─── Providers endpoint (public — no auth required) ────────────────────────

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
    """Check connectivity to all 5 cloud providers."""
    if _DEMO_MODE:
        return {
            "providers": {
                "aws": True, "gcp": True, "azure": True,
                "coreweave": True, "lambda": True,
            },
            "all_healthy": True,
        }
    from ..providers.provider_router import get_router
    router_obj = get_router()
    health = await router_obj.check_provider_health()
    return {"providers": health, "all_healthy": all(health.values())}


# ─── Entry point ──────────────────────────────────────────────────────────

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
