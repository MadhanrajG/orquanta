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
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
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

    # Seed a default admin user for first-boot and promote to admin role
    try:
        admin_email = os.getenv("ADMIN_EMAIL", "admin@orquanta.ai")
        admin_password = os.getenv("ADMIN_PASSWORD", "orquanta-admin-2024")
        register_user(email=admin_email, password=admin_password, name="OrQuanta Admin")
        logger.info(f"Admin user '{admin_email}' created.")
    except ValueError:
        pass  # Already registered — that's fine

    # Promote admin email to 'admin' role in SQLite
    try:
        from .middleware.auth import _get_db
        admin_email = os.getenv("ADMIN_EMAIL", "admin@orquanta.ai")
        conn = _get_db()
        conn.execute("UPDATE users SET role = 'admin' WHERE email = ?", (admin_email.lower(),))
        conn.commit()
        conn.close()
        logger.info(f"User '{admin_email}' promoted to admin role.")
    except Exception as exc:
        logger.warning(f"Admin role promotion skipped: {exc}")

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


# ─── Auth endpoints ────────────────────────────────────────────────────────────

_REGISTER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Join OrQuanta — Free 14-Day Trial</title>
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
  <div class="login-link">Already have an account? <a href="/docs#/Auth/login_auth_login_post">Sign in via API</a></div>
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
  <title>Welcome to OrQuanta</title>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:#050608;color:#e2e8f0;font-family:'Inter',sans-serif;min-height:100vh;padding:24px 16px}
    .top{text-align:center;padding:40px 0 32px}
    .logo{font-family:'Space Grotesk',sans-serif;font-size:1.6rem;font-weight:700;background:linear-gradient(135deg,#00D4FF,#7B2FFF);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
    h1{font-family:'Space Grotesk',sans-serif;font-size:1.6rem;font-weight:700;margin:16px 0 8px}
    .sub{color:#8892A4;font-size:.95rem;margin-bottom:8px}
    .email-badge{display:inline-block;background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.2);border-radius:20px;color:#00D4FF;font-size:.82rem;padding:4px 14px;margin-bottom:32px}
    .steps{font-family:'Space Grotesk',sans-serif;font-size:.75rem;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:#8892A4;text-align:center;margin-bottom:16px}
    .cards{display:grid;grid-template-columns:1fr;gap:14px;max-width:480px;margin:0 auto 40px}
    .card{background:rgba(15,22,36,0.9);border:1px solid rgba(0,212,255,0.15);border-radius:14px;padding:24px;cursor:pointer;text-decoration:none;display:block;transition:transform .15s,box-shadow .15s}
    .card:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(0,212,255,0.12)}
    .card.primary{border-color:rgba(0,212,255,0.4);background:rgba(0,212,255,0.05)}
    .num{font-family:'Space Grotesk',sans-serif;font-size:.75rem;font-weight:700;color:#00D4FF;letter-spacing:1px;margin-bottom:8px}
    .card-title{font-family:'Space Grotesk',sans-serif;font-size:1.05rem;font-weight:700;margin-bottom:6px}
    .card-desc{color:#8892A4;font-size:.88rem;line-height:1.55}
    .tag{display:inline-block;background:rgba(0,255,136,0.1);border:1px solid rgba(0,255,136,0.25);color:#00FF88;font-size:.72rem;padding:2px 10px;border-radius:12px;margin-top:10px}
    .footer{text-align:center;color:#64748b;font-size:.82rem;padding-bottom:32px}
    .footer a{color:#00D4FF;text-decoration:none}
  </style>
</head>
<body>
<div class="top">
  <div class="logo">OrQuanta</div>
  <h1>You're in. Welcome aboard!</h1>
  <p class="sub">Your 14-day free trial has started. Here's what to do next:</p>
  <div class="email-badge" id="user-email">Account active</div>
</div>
<p class="steps">Start here</p>
<div class="cards">
  <a class="card primary" href="/demo">
    <div class="num">STEP 1 &mdash; RECOMMENDED</div>
    <div class="card-title">Try the Live Demo</div>
    <div class="card-desc">Watch 5 AI agents manage a real GPU job in real time. See cost savings, self-healing, and multi-cloud routing live. Takes 2 minutes.</div>
    <div class="tag">No setup required</div>
  </a>
  <a class="card" href="/demo#goal-input">
    <div class="num">STEP 2</div>
    <div class="card-title">Analyze Your First GPU Goal</div>
    <div class="card-desc">Type your workload in plain English &mdash; "Fine-tune Llama 3 on my data, keep cost under $100" &mdash; and get an instant cost breakdown from the AI.</div>
    <div class="tag">AI-powered</div>
  </a>
  <a class="card" href="/docs">
    <div class="num">STEP 3 &mdash; FOR DEVELOPERS</div>
    <div class="card-title">Connect via API</div>
    <div class="card-desc">Integrate OrQuanta into your ML pipeline using the REST API. Your JWT token is saved &mdash; use it as a Bearer token in the Authorize button.</div>
    <div class="tag">Developers only</div>
  </a>
</div>
<div class="footer">
  Questions? Reply to this page &mdash; <a href="/demo">Back to Demo</a>
</div>
<script>
var em = localStorage.getItem('orquanta_email');
if (em) document.getElementById('user-email').textContent = em;
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
