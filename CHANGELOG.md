# Changelog

All notable changes to OrQuanta are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
OrQuanta uses [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

## [Unreleased]

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
