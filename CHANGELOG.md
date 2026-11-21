# Changelog

All notable changes to OrQuanta are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
OrQuanta uses [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

## [Unreleased]

## [0.5.0] — 2026-11-21

### Added — Phase 2: Production Reliability Engineering

#### Database-Persisted Job Management
- PostgreSQL is now the authoritative source of job state; in-memory `pipeline._jobs` dict kept for backward compatibility only
- New columns on `jobs` table: `celery_task_id`, `idempotency_key`, `provider_job_id`, `failure_reason`, `retry_count`, `script`, `region`, `hourly_rate_usd`
- New tables: `job_events` (append-only history), `outbox_events` (transactional outbox), `provider_health` (provider status snapshots)
- Schema migration script: `v4/phase2_migrate_schema.py` (run against production PostgreSQL before deploy)

#### Celery Execution Engine (`v4/execution/`)
- `celery_app.py` — Celery app with Redis broker, JSON serialization, `task_acks_late=True`, `reject_on_worker_lost=True`; two queues: `orquanta.jobs`, `orquanta.ops`
- `job_db.py` — synchronous psycopg2/sqlite job DB layer for Celery workers with enforced state machine (`VALID_TRANSITIONS`)
- `tasks.py` — `execute_gpu_job` Celery task with idempotency guard (aborts if `status != queued`), exponential backoff with jitter, `cancel_job` task
- `durable_pipeline.py` — bridge: `submit_durable_job` (DB create → Celery dispatch → outbox fallback → asyncio fallback)
- `reconciler.py` — Celery beat task (`reconcile_stuck_jobs` every 60s, `flush_outbox` every 10s); marks jobs stuck >30 min as failed after provider reconciliation
- `provider_health.py` — Celery beat task (`check_all_providers` every 120s); monitors RunPod, Lambda; never exposes API credentials; `is_real=false` when no key configured

#### Job State Machine
- Explicit `VALID_TRANSITIONS` dict enforcing legal state changes
- Terminal states (`completed`, `failed`, `cancelled`) are immutable
- Idempotency key prevents duplicate billable GPU workload execution
- Retries only permitted before `instance_id` is assigned

#### New API Endpoints
- `POST /api/v1/jobs/durable` — submit a durable, DB-persisted job
- `GET /api/v1/jobs/{id}/events` — full event history timeline for a job
- `GET /api/v1/jobs/{id}/status` — live job status with Celery correlation
- `GET /api/v1/provider-health` — all provider health snapshots
- `GET /api/v1/provider-health/{provider}` — single provider health detail

#### Observability
- Job event history: every status transition recorded in `job_events` with timestamp, detail, actor
- Real-time status available via existing WebSocket stream (authenticated)
- Provider health dashboard endpoint with auth_ok, latency_ms, gpu_available, is_real flags

#### New Environment Variables
- `CELERY_ENABLED` — enable/disable Celery worker (default: `true` when `REDIS_URL` set)
- `REDIS_URL` — required for Celery broker and result backend

### Changed
- Job submission path extended with durable pipeline while preserving legacy sync path
- Celery beat schedule wired: reconciler (60s), provider health (120s), outbox flush (10s)

### Security
- Idempotency key enforced at task level: same billable GPU workload cannot be submitted twice
- Provider API credentials never logged or returned in health API responses
- Job ownership and tenant association enforced on all new endpoints

## [0.4.1] — 2026-11-21

### Security

- **[CRITICAL FIX]** WebSocket endpoint `/ws/agent-stream` now requires JWT authentication via `?token=<jwt>` query parameter. Unauthenticated connections are rejected with code 4001. Connections without a valid token are rejected before the WebSocket is accepted.
- **[CRITICAL FIX]** Password reset token is no longer logged at INFO level. Reset link is now only emitted at DEBUG level to prevent token leakage in production logs.
- **[HIGH FIX]** Stripe webhook endpoint now hard-fails when `STRIPE_WEBHOOK_SECRET` is not set in production (`ENVIRONMENT=production`), preventing fraudulent subscription activation via spoofed webhook events.
- **[HIGH FIX]** Safety governor high-cost action gate now blocks and raises `PermissionError` instead of auto-approving. High-cost actions require an administrator to approve. Set `REQUIRE_HIGH_COST_APPROVAL=false` to disable (not recommended).
- Hardcoded default database credentials (`orquanta:orquanta`) removed from `database/models.py`. Missing `DATABASE_URL` now warns and falls back to SQLite in development only.
- All `bomax` branding references removed from `.env.example` and replaced with `orquanta` or `change-me-in-production` placeholders.
- Rate limiter now correctly reads client IP from `X-Forwarded-For` / `X-Real-IP` headers when behind a reverse proxy (nginx, Cloudflare, AWS ALB). Previously all proxied clients shared the proxy IP, breaking per-user rate limiting.
- Rate limiter stale IP eviction added to prevent unbounded memory growth under high unique-IP load.
- Safety governor Slack notification support added: set `SLACK_WEBHOOK_URL` to receive alerts when high-cost actions are blocked.
- `WS_AUTH_REQUIRED` env var added (default `true`). Set to `false` only for local development.

### Added

- `LICENSE` — Apache License 2.0
- `CONTRIBUTING.md` — development setup, code style, branch naming, PR process
- `SECURITY.md` — responsible disclosure policy, in-scope vulnerabilities, production hardening checklist
- `CHANGELOG.md` — this file
- `docker-compose.dev.yml` — full local development stack (API, frontend, PostgreSQL, Redis, ChromaDB)
- Password reset flow: `POST /auth/forgot-password` and `POST /auth/reset-password` with JWT-based token, 1-hour expiry, anti-enumeration (always returns 200), optional SMTP delivery
- Skeleton UI loading components (`SkeletonStat`, `SkeletonStatGrid`, `SkeletonTable`, `SkeletonCard`, `SkeletonPage`, `SkeletonChart`) with shimmer animation
- Forgot Password page with 2-step form, password strength indicator, show/hide toggle
- "Forgot password?" link on login form
- LivePricing fallback mock data (10 real-world GPU prices) with amber DEMO banner when API returns empty
- FAQ entry: "How do I reset my password?" in HelpPage

### Changed

- JobManager table now responsive with horizontal scroll on mobile
- JobManager stat grid: 2 columns on mobile, 4 on desktop
- BillingPage: skeleton loading guard prevents flash of empty content
- Production Dockerfile: `VITE_API_BASE_URL` baked at build time via `ARG`/`ENV`
- `render.yaml`: plan set to `starter`, CORS origins, Postgres from Render add-on
- `.github/workflows/deploy.yml`: build-args pass `VITE_API_BASE_URL=https://orquanta.com`
- `docker-compose.prod.yml`: Coolify-ready with Traefik labels

### Fixed

- `AgentMonitor.jsx` truncated file (missing closing `}`) repaired
- `localhost` reference removed from production frontend bundle
- PowerShell `&&` incompatibility resolved throughout deployment scripts

---

## [0.4.0] — 2026-11-01

### Added

- Initial public release of OrQuanta Agentic v4.0
- Multi-agent orchestration: Vero, NemoClaw, Research, Infrastructure, GPU Optimisation, Model, Security, Cost, Developer, Observability agents
- Unified GPU provider adapter architecture (RunPod, Lambda, AWS, GCP, Azure, CoreWeave, Kaggle, Colab)
- Real-time WebSocket agent reasoning stream
- FastAPI backend with async PostgreSQL (SQLAlchemy 2.0 / asyncpg)
- React/Vite frontend with Tailwind CSS and Lucide icons
- Stripe billing integration with checkout, portal and webhook handling
- Safety governor: rate limiting, daily spend cap, emergency stop, audit trail
- API key management with SHA-256 hashing
- Demo mode: clearly labelled simulated data, never presented as real execution
- Prometheus metrics and Grafana dashboard
- Full SDK (`orquanta_sdk.py`) and CLI (`orquanta_cli.py`)
- Five test suites: API, agents, E2E, orchestrator, safety
- Production deployment: Render, Coolify/Traefik, GitHub Actions CI/CD
