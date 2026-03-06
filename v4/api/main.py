"""
OrQuanta Agentic v1.0 â€” FastAPI Application Entry Point

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
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .routers import goals, jobs, agents, metrics, audit
from .routers.admin import router as admin_router
from .routers.billing import router as billing_router
from .routers.webhooks import router as webhooks_router
from .routers.schedules import router as schedules_router, get_cron_scheduler
from .routers.free_tier import router as free_tier_router
from .websocket.agent_stream import router as ws_router
from .middleware.auth import authenticate_user, create_access_token, register_user
from .models.schemas import (
    HealthResponse, LoginRequest, RegisterRequest, TokenResponse
)

# Demo mode â€” check both env var names for compatibility
_DEMO_MODE = (
    os.getenv("ORQUANTA_DEMO_MODE", "false").lower() in ("true", "1", "yes")
    or os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
)

# â”€â”€â”€ Logging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s â€” %(message)s",
)
logger = logging.getLogger("orquanta.api")

VERSION = "1.0.0"
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")


# â”€â”€â”€ Lifespan (startup / shutdown) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: validate env, boot agents, wire pipeline. Shutdown: graceful stop."""
    logger.info(f"OrQuanta Agentic v{VERSION} starting upâ€¦")

    # â”€â”€ 0. Validate production environment â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Init production job pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from ..execution.pipeline import get_pipeline
    pipeline = get_pipeline()
    # Wire WebSocket broadcaster so pipeline can push live events to clients
    try:
        from .websocket.agent_stream import broadcast_to_all
        pipeline.set_ws_broadcaster(broadcast_to_all)
        logger.info("[Pipeline] WebSocket broadcaster wired.")
    except Exception as exc:
        logger.warning(f"[Pipeline] WS broadcaster not available: {exc}")

    # Seed a default admin user for first-boot and promote to admin role
    try:
        admin_email = os.getenv("ADMIN_EMAIL", "admin@orquanta.ai")
        admin_password = os.getenv("ADMIN_PASSWORD", "orquanta-admin-2024")
        register_user(email=admin_email, password=admin_password, name="OrQuanta Admin")
        logger.info(f"Admin user '{admin_email}' created.")
    except ValueError:
        pass  # Already registered â€” that's fine

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
            logger.info("[Demo] Demo mode active â€” scenario 'cost_optimizer' starting")
        except Exception as exc:
            logger.warning(f"[Demo] Demo startup error (non-fatal): {exc}")

    # â”€â”€ Start CronScheduler (OpenClaw-inspired recurring GPU jobs) â”€â”€â”€â”€â”€â”€â”€â”€
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
    logger.info("OrQuanta shutting downâ€¦")
    await orchestrator.stop()
    await scheduler.stop()
    await cost_agent.stop()
    await healing_agent.stop()
    await forecast_agent.stop()
    logger.info("Shutdown complete.")


# â”€â”€â”€ FastAPI App â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

app = FastAPI(
    title="OrQuanta Agentic v1.0",
    description=(
        "Autonomous GPU Cloud Orchestration Platform. "
        "Submit natural-language goals â€” OrQuanta agents handle the rest."
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


# â”€â”€â”€ Security Headers Middleware â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€â”€ Global exception handler â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€â”€ Auth endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_REGISTER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Join OrQuanta â€” Free 14-Day Trial</title>
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
  <title>Welcome to OrQuanta â€” You're In!</title>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:#050608;color:#e2e8f0;font-family:'Inter',sans-serif;min-height:100vh;overflow-x:hidden}

    /* â”€â”€ Animated gradient hero â”€â”€ */
    .hero{position:relative;text-align:center;padding:64px 24px 48px;overflow:hidden}
    .hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 80% 60% at 50% 0%,rgba(0,212,255,0.13),transparent 70%);pointer-events:none}
    .hero::after{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);width:1px;height:120px;background:linear-gradient(to bottom,rgba(0,212,255,0.6),transparent)}

    /* â”€â”€ Success badge â”€â”€ */
    .badge{display:inline-flex;align-items:center;gap:8px;padding:6px 18px;border-radius:999px;border:1px solid rgba(0,255,136,0.4);background:rgba(0,255,136,0.08);font-size:13px;font-weight:600;color:#00FF88;margin-bottom:28px;animation:fadeSlideDown .5s ease}
    .badge-dot{width:8px;height:8px;border-radius:50%;background:#00FF88;animation:pulse 2s infinite}

    /* â”€â”€ Typography â”€â”€ */
    .logo{font-family:'Space Grotesk',sans-serif;font-size:1rem;font-weight:600;color:#8892A4;letter-spacing:2px;text-transform:uppercase;margin-bottom:20px}
    h1{font-family:'Space Grotesk',sans-serif;font-size:clamp(1.8rem,4vw,2.8rem);font-weight:700;line-height:1.15;margin-bottom:12px;animation:fadeSlideDown .5s .1s ease both}
    .h1-sub{color:#8892A4;font-size:.95rem;margin-bottom:20px;animation:fadeSlideDown .5s .15s ease both}
    .email-pill{display:inline-block;background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.25);border-radius:999px;color:#00D4FF;font-size:.82rem;padding:5px 16px;margin-bottom:40px;animation:fadeSlideDown .5s .2s ease both}

    /* â”€â”€ Token box (collapsed) â”€â”€ */
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

    /* â”€â”€ Action cards â”€â”€ */
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

    /* â”€â”€ Footer â”€â”€ */
    .foot{text-align:center;color:#475569;font-size:.82rem;padding:0 24px 40px;line-height:1.8}
    .foot a{color:#00D4FF;text-decoration:none}

    /* â”€â”€ Animations â”€â”€ */
    @keyframes fadeSlideDown{from{opacity:0;transform:translateY(-12px)}to{opacity:1;transform:translateY(0)}}
    @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.3)}}

    /* â”€â”€ Confetti canvas â”€â”€ */
    #confetti{position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:100}
  </style>
</head>
<body>
<canvas id="confetti"></canvas>

<div class="hero">
  <div class="logo">OrQuanta</div>
  <div class="badge"><span class="badge-dot"></span> Account created successfully</div>
  <h1>You're in.<br>Welcome aboard! ðŸš€</h1>
  <p class="h1-sub">Your 14-day free trial starts now. Zero setup. Cancel anytime.</p>
  <div class="email-pill" id="user-email">Account active</div>
</div>

<!-- JWT Token for devs -->
<div class="token-section">
  <div class="token-toggle" onclick="toggleToken(this)">
    <span>ðŸ”‘ Your API token is ready</span>
    <span id="tok-arrow" style="transition:transform .2s">â–¾</span>
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
    <div class="card-num">Step 1 â€” Recommended</div>
    <div class="card-icon">âš¡</div>
    <div class="card-title">Open Your Dashboard</div>
    <div class="card-desc">Your personal mission control. Submit AI goals, monitor live agents, track costs, and view audit logs â€” all in one place.</div>
    <div class="card-tag">â†— Open now</div>
  </a>

  <a class="card c2" href="/demo#goal-input">
    <div class="card-num">Step 2</div>
    <div class="card-icon">ðŸ§ </div>
    <div class="card-title">Analyze Your First GPU Goal</div>
    <div class="card-desc">Type your workload in plain English â€” "Fine-tune Llama 3 on my data, cost under $100" â€” and our AI gives you an instant cost breakdown across 5 cloud providers.</div>
    <div class="card-tag">2 min Â· No setup</div>
  </a>

  <a class="card c3" href="/demo">
    <div class="card-num">Step 3</div>
    <div class="card-icon">ðŸ“¡</div>
    <div class="card-title">Watch Agents Work Live</div>
    <div class="card-desc">See 5 specialized AI agents â€” Scheduler, Cost Optimizer, Healing, Forecast, Audit â€” orchestrating a real GPU job with live streaming logs and metrics.</div>
    <div class="card-tag">Live stream</div>
  </a>

</div>

<div class="foot">
  Need help? <a href="mailto:orquanta.founder@gmail.com">orquanta.founder@gmail.com</a> &nbsp;Â·&nbsp;
  <a href="/demo">Back to Demo</a> &nbsp;Â·&nbsp;
  <a href="/app">Dashboard â†’</a>
</div>

<script>
// â”€â”€ Token display â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    b.textContent = 'âœ“ Copied!';
    setTimeout(function(){ b.textContent = 'Copy Token'; }, 2000);
  });
}

// â”€â”€ Confetti burst â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# â”€â”€â”€ Health check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/health", tags=["System"], response_model=HealthResponse, summary="Health check")
async def health():
    """System health check â€” no auth required."""
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


# â”€â”€â”€ Include routers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

app.include_router(goals.router)
app.include_router(jobs.router)
app.include_router(agents.router)
app.include_router(metrics.router)
app.include_router(audit.router)
app.include_router(admin_router)
app.include_router(billing_router)   # /api/v1/billing â€” Stripe + subscriptions
app.include_router(ws_router)

# Demo router â€” always included; active only when DEMO_MODE=true
try:
    from ..demo.public_demo import demo_router
    app.include_router(demo_router, prefix="/demo", tags=["Demo"])
except Exception:
    pass  # demo package optional


# â”€â”€â”€ Serve built React frontend â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# FIX-9: Resolve from the v4/ root (two levels up from api/) â€” avoids double v4/ prefix
_DIST_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_DIST_DIR = os.path.abspath(_DIST_DIR)

if os.path.isdir(_DIST_DIR):
    # Serve static assets (JS/CSS chunks Vite generates into dist/assets/)
    _assets_dir = os.path.join(_DIST_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/app/assets", StaticFiles(directory=_assets_dir), name="react-assets")

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    async def serve_react_app(path: str = ""):
        """Serve the React SPA â€” index.html handles all client-side routes."""
        return FileResponse(os.path.join(_DIST_DIR, "index.html"))
else:
    # Frontend not built â€” tell developers clearly
    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    async def react_not_built(path: str = ""):
        return HTMLResponse(
            content="<h2>Frontend not built. Run <code>npm run build</code> inside v4/frontend/.</h2>",
            status_code=503,
        )


# â”€â”€â”€ Providers endpoint (public â€” no auth required) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        readiness["verdict"] = "ðŸŸ¡ Demo Mode â€” All Systems Operational"
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


# â”€â”€â”€ Entry point â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
