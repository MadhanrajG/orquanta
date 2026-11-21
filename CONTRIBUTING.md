# Contributing to OrQuanta

Thank you for your interest in contributing to OrQuanta — the Universal Autonomous AI Infrastructure Platform. This document covers development setup, code standards, and the contribution process.

## Table of Contents

- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Branch Naming](#branch-naming)
- [Pull Request Process](#pull-request-process)
- [Issue Templates](#issue-templates)
- [Commit Convention](#commit-convention)
- [Architecture Overview](#architecture-overview)
- [Licence](#licence)

---

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker and Docker Compose
- `uv` (recommended) or `pip`

### Local Development with Docker Compose

The fastest way to run the full stack locally:

```bash
git clone https://github.com/MadhanrajG/orquanta.git
cd orquanta
cp v4/.env.example v4/.env
# Fill in required values (see .env.example comments)
docker compose -f docker-compose.dev.yml up
```

Services started:
- API: http://localhost:8000
- Frontend: http://localhost:3000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### Manual Setup (without Docker)

**Backend:**
```bash
cd v4
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

**Celery Workers (Phase 2 — required for durable job execution):**
```bash
cd v4
# Job execution worker
celery -A v4.execution.celery_app worker --loglevel=info -Q orquanta.jobs,orquanta.ops

# Beat scheduler (reconciler, provider health, outbox flush)
celery -A v4.execution.celery_app beat --loglevel=info
```

> **Note:** `REDIS_URL` must be set in `.env` for Celery to start. Set `CELERY_ENABLED=false` to disable Celery and fall back to asyncio execution.

**Frontend:**
```bash
cd v4/frontend
npm install
npm run dev
```

---

## Running Tests

```bash
# All tests
cd v4
pytest tests/ -v

# Specific test file
pytest tests/test_api.py -v

# With coverage
pytest tests/ --cov=. --cov-report=html
```

Frontend tests:
```bash
cd v4/frontend
npm run test
```

---

## Code Style

**Python:**
- Formatter: [Black](https://github.com/psf/black) (`black .`)
- Import sorter: [isort](https://pycqa.github.io/isort/) (`isort .`)
- Linter: [Ruff](https://docs.astral.sh/ruff/) (`ruff check .`)
- Type hints required on all public functions and methods

**JavaScript / TypeScript:**
- Linter: ESLint (config in `v4/frontend/.eslintrc`)
- Formatter: Prettier
- Run: `npm run lint` and `npm run format`

**General rules:**
- No hardcoded secrets or credentials in source
- No `print()` in production code — use `logging`
- All environment variables documented in `.env.example`
- New API endpoints must include Pydantic request/response models

---

## Branch Naming

| Type | Pattern | Example |
|---|---|---|
| Feature | `feat/<short-description>` | `feat/websocket-auth` |
| Bug fix | `fix/<issue-or-description>` | `fix/rate-limiter-proxy` |
| Chore | `chore/<task>` | `chore/update-dependencies` |
| Documentation | `docs/<what>` | `docs/api-reference` |
| Security | `security/<what>` | `security/token-denylist` |

---

## Pull Request Process

1. Fork the repository and create a branch from `main`.
2. Write tests covering your change.
3. Ensure all existing tests pass.
4. Run linters and formatters.
5. Update `.env.example` if you add new environment variables.
6. Update `CHANGELOG.md` under the `[Unreleased]` section.
7. Open a PR against `main` with a clear description of what changed and why.
8. A maintainer will review within 3 business days.

**PR checklist:**
- [ ] Tests added or updated
- [ ] Linters pass
- [ ] No new secrets or credentials
- [ ] `.env.example` updated if applicable
- [ ] `CHANGELOG.md` updated

---

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

[optional footer(s)]
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `security`, `perf`

Examples:
```
feat(websocket): add JWT authentication to agent stream endpoint
fix(billing): hard-fail stripe webhook when secret not configured in production
security(main): remove reset token from INFO-level log
chore: add Apache 2.0 LICENSE and CONTRIBUTING.md
```

---

## Issue Templates

When filing an issue, select one of:
- **Bug report** — something is broken
- **Feature request** — new capability or improvement
- **Security vulnerability** — please use our [responsible disclosure process](SECURITY.md) instead of a public issue

---

## Architecture Overview

```
orquanta/
└── v4/
    ├── agents/         # Autonomous agent implementations (Vero, NemoClaw, etc.)
    ├── api/            # FastAPI application, routers, middleware, WebSocket
    ├── providers/      # GPU provider adapters (RunPod, Lambda, etc.)
    ├── execution/      # Job pipeline and workload execution
    ├── security/       # Auth, secrets management, rate limiting, input validation
    ├── sdk/            # Python SDK and CLI for external integrations
    ├── monitoring/     # Prometheus metrics, Grafana dashboards, Sentry
    ├── notifications/  # Email, Discord, Telegram notifiers
    ├── database/       # SQLAlchemy models, repositories, persistence
    ├── billing/        # Stripe integration
    ├── intelligence/   # Market analysis, user analytics
    ├── demo/           # Demo mode — never presents simulated data as real
    ├── infra/          # Docker, Kubernetes, Nginx configs
    └── frontend/       # React/Vite frontend
```

Key design principles:
- **Mock by default, real when configured.** The `USE_REAL_PROVIDERS=true` env var enables real GPU provisioning. This is intentional — do not remove the safety check.
- **Never present simulated execution as real.** Demo mode data must always be clearly labelled.
- **Policy-first agent execution.** All agent actions flow through `safety_governor.py` before execution.
- **Fail loudly on misconfiguration.** Missing required secrets in production must raise errors, not silently degrade.

---

## Licence

By contributing to OrQuanta, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
