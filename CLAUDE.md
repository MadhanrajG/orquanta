# OrQuanta — Claude Code Master Context

**Product:** Autonomous GPU Cloud Orchestration Platform  
**Version:** 1.0.0 (Production)  
**Stack:** FastAPI (Python 3.11) + React 18 (Vite) + Neon PostgreSQL  
**Infra:** Cloudflare Edge Worker → Render Singapore → Neon DB (AWS ap-southeast-1)

---

## Architecture Overview

```
Browser
  └─► Cloudflare Worker (orquanta.com)   ← CDN edge, keeps Render warm (5-min cron)
        └─► Render Web Service (Singapore) ← FastAPI + React SPA served together
              └─► Neon PostgreSQL           ← users table only (pg via psycopg2)
                                             jobs/goals are IN-MEMORY (restart loses data)
```

**Critical:** Goals and jobs live entirely in Python dicts inside running process. A Render restart wipes all jobs. DB stores only user accounts and audit log entries.

---

## Production URLs

| Resource | URL |
|---|---|
| App | https://orquanta.com/app |
| API docs | https://orquanta.com/docs |
| Health | https://orquanta.com/health |
| Demo | https://orquanta.com/demo |
| Register | https://orquanta.com/auth/register |

---

## Local Development

### Start backend (port 8000)
```bash
cd c:/ai-gpu-cloud
PYTHONPATH=c:/ai-gpu-cloud \
  JWT_SECRET_KEY=dev-secret-key-local \
  LLM_PROVIDER=mock \
  USE_REAL_PROVIDERS=false \
  python -m uvicorn v4.api.main:app --reload --port 8000
```

### Start frontend dev server (port 3000, proxies to :8000)
```bash
cd c:/ai-gpu-cloud/v4/frontend
npm install
npm run dev
```

### Build frontend (required before deploy or serving via FastAPI)
```bash
cd c:/ai-gpu-cloud/v4/frontend
npm run build
# Output goes to v4/frontend/dist/ — FastAPI serves it at /app/*
```

### Start local services (Redis + ChromaDB)
```bash
# Requires Docker Desktop running
docker-compose -f docker-compose.dev.yml up -d
# Redis: localhost:6379  |  ChromaDB: localhost:8200
```

### Run tests
```bash
cd c:/ai-gpu-cloud
PYTHONPATH=c:/ai-gpu-cloud \
  JWT_SECRET_KEY=test-secret \
  USE_REAL_PROVIDERS=false \
  python -m pytest v4/tests/ -v --tb=short
```

Tests use SQLite in-memory (conftest.py patches DATABASE_URL before any import). Never need a live DB or provider credentials to run the test suite.

---

## File Map — Backend

```
v4/
  api/
    main.py              ← FastAPI app, lifespan, auth endpoints, SPA serving
    prometheus_metrics.py
    middleware/
      auth.py            ← JWT, PBKDF2-SHA256, register_user, authenticate_user
      rate_limit.py
    models/
      schemas.py         ← All Pydantic request/response models
    routers/
      goals.py           ← POST/GET /api/v1/goals — MasterOrchestrator entry point
      jobs.py            ← CRUD /api/v1/jobs — routes through JobPipeline
      agents.py          ← GET/POST /api/v1/agents — emergency stop, status
      metrics.py         ← /api/v1/metrics/* — cost/GPU/platform dashboards
      audit.py           ← /api/v1/audit — AuditAgent log
      billing.py         ← /api/v1/billing — Stripe (warning mode if no key)
      pricing.py         ← /api/v1/pricing — live GPU prices (Lambda/RunPod/Vast)
      schedules.py       ← /api/v1/schedules — cron recurring jobs
      webhooks.py        ← /api/v1/webhooks
      admin.py           ← /api/v1/admin (role=admin only)
      free_tier.py       ← /api/v1/free — Colab/Kaggle free GPU
      vero.py            ← /api/v1/vero — Vero meta-agent API
      nemoclaw.py        ← /api/v1/nemoclaw — NemoClaw cognitive layer
      uix.py             ← /api/v1/uix — UIXAgent diagnostics
    websocket/
      agent_stream.py    ← WebSocket /ws/agent-stream + broadcast_to_all()

  agents/
    master_orchestrator.py  ← ReAct loop: natural-language goals → tasks
    scheduler_agent.py      ← Bin-packing priority queue, preemption; get_scheduler()
    cost_optimizer_agent.py ← Cost analysis + recommendations; get_cost_optimizer()
    healing_agent.py        ← Auto-retry, instance recovery; get_healing_agent()
    forecast_agent.py       ← Cost/usage prediction; get_forecast_agent()
    audit_agent.py          ← Immutable audit trail
    vero_agent.py           ← Meta-agent: oversight(15s) + user intelligence(60s) + market(300s); get_vero()
    nemoclaw_engine.py      ← ContextGraph, CostWatcher, PredictivePrefetch; get_nemoclaw()
    safety_governor.py      ← Hard budget caps, emergency stop
    llm_reasoning_engine.py ← LLM abstraction (OpenAI/Anthropic/mock)
    recommendation_agent.py
    memory_manager.py
    tool_registry.py
    uix_agent.py
    orquanta_kernel_bridge.py

  execution/
    pipeline.py          ← JobPipeline: provision→SSH→billing→terminate; get_pipeline()
    job_runner.py        ← SSH execution + log streaming
    docker_runner.py
    kubernetes_runner.py

  providers/
    provider_router.py   ← Selects cheapest provider, failover; get_router()
    runpod_provider.py   ← RunPod REST API ($2.49/hr H100 — primary choice)
    lambda_labs_provider.py
    aws_provider.py
    gcp_provider.py
    azure_provider.py
    coreweave_provider.py
    base_provider.py     ← Abstract base class

  database/
    models.py            ← SQLAlchemy ORM (users, audit_log)
    repositories.py

  billing/
    stripe_integration.py ← StripeBilling; works in warning mode without key

  security/
    input_validator.py
    rate_limiter.py
    secrets_manager.py
    security_headers.py   ← CSP, HSTS, X-Frame-Options

  monitoring/
    alerting.py
    cost_tracker.py
    gpu_telemetry.py
    metrics_exporter.py

  intelligence/
    carbon_tracker.py
    market_trend_analyzer.py
    user_analytics.py

  demo/
    demo_mode.py
    demo_scenario.py
    metrics_simulator.py
    public_demo.py        ← /demo route (server-rendered)

  tests/
    conftest.py          ← SQLite patch, env vars for tests
    test_api.py          ← API route tests
    test_e2e.py          ← End-to-end flow tests
    test_agents.py
    test_orchestrator.py
    test_safety.py

  startup_validator.py   ← Env var validation, readiness score
  start_orquanta.py
  db_init.py
```

---

## File Map — Frontend

```
v4/frontend/
  src/
    App.jsx              ← SPA root: all routes, auth, sidebar, all page components
                           BrowserRouter basename="/app" — all routes relative to /app
  index.html
  vite.config.js         ← base: '/app/', dev proxy → :8000
  package.json
  dist/                  ← Built output; FastAPI serves assets at /app/assets/
```

App.jsx contains everything in one file: auth context, all page components (Dashboard, Goals, Jobs, Agents, Metrics, Audit, Settings, Pricing), sidebar, `useLiveSavings()` hook.

---

## Agent Architecture

**Startup order** (lifespan in main.py):
1. `MasterOrchestrator.start()` — ReAct orchestrator
2. `SchedulerAgent.start()` — bin-packing scheduler
3. `CostOptimizerAgent.start()` — cost analysis
4. `HealingAgent.start()` — self-healing
5. `ForecastAgent.start()` — predictions
6. `VeroAgent.start(orchestrator)` — meta-agent (oversight/intelligence/market loops)
7. `NemoClawEngine.start(vero, orchestrator)` — cognitive layer
8. `JobPipeline.set_ws_broadcaster(broadcast_to_all)` — wire WebSocket

**Singleton pattern** — every agent uses module-level getter:
```python
_instance: AgentClass | None = None
def get_agent() -> AgentClass:
    global _instance
    if _instance is None:
        _instance = AgentClass()
    return _instance
```
All routers and main.py must use `get_xyz()` — never instantiate directly.

---

## Provider Hierarchy

**Selection order** (cheapest first):
1. RunPod — `$2.49/hr` H100 SXM5 80GB (primary)
2. Lambda Labs — `$2.49/hr` H100
3. CoreWeave — `$2.76/hr` H100
4. AWS — `$12.29/hr` p4d.24xlarge (fallback)
5. GCP — `$10.00/hr` a2-highgpu
6. Azure — `$10.06/hr` Standard_ND96asr_v4

**Mock mode**: `USE_REAL_PROVIDERS=false` (default) — no credentials needed, all providers return simulated data.

---

## Key Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `JWT_SECRET_KEY` | YES | none | HMAC-SHA256 signing key |
| `DATABASE_URL` | YES prod | SQLite fallback | PostgreSQL connection string |
| `ENV` | no | `production` | `development` unlocks CORS `*` |
| `USE_REAL_PROVIDERS` | no | `false` | Enable real cloud API calls |
| `RUNPOD_API_KEY` | no | `""` | RunPod v2 REST API key |
| `OPENAI_API_KEY` | no | `""` | GPT-4 reasoning |
| `ANTHROPIC_API_KEY` | no | `""` | Claude reasoning |
| `GROQ_API_KEY` | no | `""` | Groq — Llama3-70B/Mixtral at 200+ tok/s; AUTO mode picks this first |
| `GROQ_MODEL` | no | `llama3-70b-8192` | Groq model to use |
| `SENTRY_DSN` | no | `""` | Sentry error tracking + performance (no-op if absent) |
| `STRIPE_SECRET_KEY` | no | `""` | Billing (warning mode if absent) |
| `ADMIN_EMAIL` | no | `admin@orquanta.com` | Auto-seeded admin |
| `ADMIN_PASSWORD` | no | `""` | Skip seed if not set |
| `CORS_ORIGINS` | no | prod default | Comma-separated allowed origins |
| `ORQUANTA_DEMO_MODE` | no | `false` | Enable demo scenario engine |

Production CORS default: `https://orquanta.com,https://orquanta-app.pages.dev`  
Development CORS: `*`

---

## Auth System

- **Algorithm:** PBKDF2-HMAC-SHA256, 260000 iterations, 16-byte random salt
- **JWT:** HS256, 24-hour expiry (`exp` claim), `sub`=user_id, `email`, `role`
- **Roles:** `user` (default), `admin` (set via DB UPDATE)
- **Login rate limit:** 5 failures/60s → 429 soft block; 10 failures/300s → hard block
- **DB backend:** Neon PostgreSQL in production, SQLite fallback for local dev

Auth middleware: `v4/api/middleware/auth.py`  
- `get_current_user()` — FastAPI dependency, raises 401 if invalid token  
- `authenticate_user(email, password)` → user dict or None  
- `register_user(email, password, name)` → user dict  
- `create_access_token(user_id, email, role)` → JWT string

---

## Security Invariants

**Never break these:**

1. **Shell injection** — user-controlled strings in bash scripts MUST go through `_shell_quote()`:
   ```python
   def _shell_quote(s: str) -> str:
       return "'" + s.replace("'", "'\"'\"'") + "'"
   ```
   Used in `jobs.py:_intent_to_script()` and `pipeline.py:_default_script()`.

2. **CSP** — `script-src 'self'` for all non-demo routes. Demo page uses `'unsafe-inline'`. Never weaken the non-demo CSP.

3. **SQL** — All DB queries use parameterized `?` (SQLite) or `%s` (PostgreSQL). `_ph()` in auth.py returns the correct placeholder based on `_USE_PG`.

4. **XSS** — `intent`, `raw_text`, `name`, `email` fields in schemas.py all have `field_validator` stripping HTML tags and dangerous chars.

5. **CORS** — Production is NOT `*`. Changing `_DEFAULT_ORIGINS` to `*` in production is a security bug.

---

## WebSocket Streaming

- **Endpoint:** `GET /ws/agent-stream` (WebSocket upgrade)
- **Manager:** `ConnectionManager` in `agent_stream.py` — broadcasts to all connected clients
- **Pipeline wiring:** `pipeline.set_ws_broadcaster(broadcast_to_all)` called in lifespan
- **Message format:** `{"event": "job_update", "job_id": "...", "status": "...", "log": "..."}`

If the import fails at startup, job streaming silently breaks. The `broadcast_to_all` function MUST exist in `agent_stream.py`.

---

## React SPA Routing

```
/app                → Dashboard (requires auth)
/app/goals          → Goals page
/app/jobs           → Jobs page
/app/agents         → Agents page
/app/metrics        → Metrics page
/app/audit          → Audit log
/app/settings       → Settings (profile, security, notifications)
/app/pricing        → Live pricing comparator
```

FastAPI catches all `/app` and `/app/{path:path}` and serves `dist/index.html`. React Router handles client-side routing.

Vite `base: '/app/'` means all built assets are at `/app/assets/chunk.js`, not `/assets/chunk.js`.

---

## CI/CD Pipeline

File: `.github/workflows/ci.yml`

**On push to main:**
1. Deploy Cloudflare Worker + Pages (builds React, deploys CF Worker with `wrangler`)
2. Run Python tests (pytest with SQLite, no cloud creds needed)
3. Build Docker image (optional AWS ECR path)

**Deploy to Render:** Auto-deploy via GitHub integration on push to main.

**Cloudflare Worker** (`infra/cloudflare/worker.js` or similar): Proxies API calls to Render, serves Pages, runs keepalive cron every 5 minutes.

---

## MCP Servers Available

All configured in `.mcp.json` at project root. Secrets are prompted once per session.

| Server | Usage |
|---|---|
| `playwright` | Browser automation — test UI flows, take screenshots |
| `github` | Manage PRs, check CI status, review issues |
| `postgres` | Direct Neon DB queries — inspect users, audit logs |
| `fetch` | HTTP requests — test live API endpoints |
| `sequential-thinking` | Multi-step reasoning for complex architecture decisions |
| `memory` | Persistent knowledge graph across sessions |
| `filesystem` | Read/write `v4/` and `.github/` directories |
| `brave-search` | Live web research — GPU pricing, provider APIs, ML framework docs (needs `BRAVE_API_KEY`) |
| `git` | Local git ops — blame, log, show, diff on `c:/ai-gpu-cloud` repo |
| `context7` | Library documentation lookup — FastAPI, Pydantic, ChromaDB, etc. (no auth needed) |

**Effective MCP usage patterns:**
```
# Test a live API endpoint
fetch: GET https://orquanta.com/health

# Check real DB state
postgres: SELECT id, email, role, created_at FROM users ORDER BY created_at DESC LIMIT 10;

# Verify UI after code change (rebuild first)
playwright: navigate to http://localhost:3000/app, take screenshot

# Check CI job status
github: get workflow runs for repository

# Research current GPU spot prices
brave-search: "RunPod H100 spot price 2025"

# Look up FastAPI docs inline
context7: resolve library FastAPI, then search "background tasks"

# Inspect git history for a specific file
git: log v4/agents/llm_reasoning_engine.py
```

---

## Known Technical Debt

| Item | Status | Notes |
|---|---|---|
| Goals/Jobs in-memory only | Active | Restart loses all data. Needs PostgreSQL persistence. |
| Stripe unconfigured | Active | `STRIPE_SECRET_KEY` not set — billing in warning mode |
| Oracle Cloud ARM64 | Planned | Scripts at `infra/oracle/` — replace Render free tier |
| Google/GitHub OAuth | v1.1 | Placeholder "SSO coming soon" in login page; `authlib` already installed |
| Redis/Celery | Optional | Use `docker-compose -f docker-compose.dev.yml up -d` to run locally; caching uses in-memory dict otherwise |
| SQLAlchemy/asyncpg | Unused | requirements.txt has async ORM but auth.py uses psycopg2 direct. Dead weight. |
| TurboQuant vLLM | Commented out | Python 3.12+ only; commented in requirements.txt |

---

## Common Task Patterns

### Adding a new API endpoint
1. Add Pydantic schema to `v4/api/models/schemas.py`
2. Add route to appropriate router in `v4/api/routers/`
3. Register router in `v4/api/main.py` if it's a new file
4. Add test to `v4/tests/test_api.py`

### Adding a new agent
1. Create `v4/agents/new_agent.py` with class + module-level `get_new_agent()` singleton
2. Import and start it in `lifespan()` in `main.py`
3. Stop it in the shutdown half of lifespan

### Debugging production issues
1. Check `/health` — should return `{"status": "healthy"}`
2. Check `/health/readiness` — shows env vars configured, providers available
3. Check Render logs for startup errors
4. Use postgres MCP to inspect user table if auth issues

### Frontend changes
1. Edit `v4/frontend/src/App.jsx`
2. `npm run build` in `v4/frontend/`
3. Restart FastAPI or it will serve new files immediately (FileResponse, no cache)
4. For dev: `npm run dev` hot-reloads at :3000, proxies API to :8000

### Running a subset of tests
```bash
# API tests only
PYTHONPATH=c:/ai-gpu-cloud JWT_SECRET_KEY=test python -m pytest v4/tests/test_api.py -v

# Single test
PYTHONPATH=c:/ai-gpu-cloud JWT_SECRET_KEY=test python -m pytest v4/tests/test_api.py::test_health -v
```

---

## Code Conventions

- No unnecessary comments. Only add one when the WHY is non-obvious.
- No premature abstractions. Three similar lines is better than a helper for two uses.
- Singleton getters (not module-level instantiation) for all agents.
- Pydantic validators on every user-input field — strip HTML, block injection chars.
- Shell-quote all user strings that go into bash scripts.
- `_` prefix for unused FastAPI path/dependency parameters to silence linter.
- All test env patching happens in `conftest.py` before any imports.

---

## Session Startup Checklist

When starting a new Claude Code session on this project:

1. Read `CLAUDE.md` (this file) — done
2. Check `git status` and recent `git log` to understand what changed
3. Check memory at `C:/Users/91979/.claude/projects/c--ai-gpu-cloud/memory/`
4. If debugging a production issue: use fetch MCP to hit live endpoints first
5. If making schema changes: update both `schemas.py` and the relevant router
6. Before claiming a fix works: run the test suite or use playwright MCP to verify UI
