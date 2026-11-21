# Changelog

All notable changes to OrQuanta are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
OrQuanta uses [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

## [Unreleased]

## [0.8.0] — 2026-11-21

### Added — Phase 4: AI Security, Governance and Trust Platform

**Phase 4A — Central Policy Decision and Enforcement Engine**
- `v4/security/policy_engine.py` — `PolicyEngine` (PDP), `Enforcer` (PEP), `PolicyStore`, `AuditBus`
- `Decision` enum: ALLOW / DENY / REQUIRE_APPROVAL / RESTRICTED / REVIEW_REQUIRED
- 8 default policies seeded at startup (model infer, model deploy, GPU provision, budget enforcement, etc.)
- Cross-tenant resource access is always DENY — evaluated before any other policy
- `context_hash` on every `PolicyResult` for immutable audit evidence
- `AuditBus` is append-only; no delete/clear/remove capability exposed
- `PolicyDeniedError` / `ApprovalRequiredError` for clean exception propagation

**Phase 4B — AI Identity and Access Management**
- `v4/security/iam.py` — `IAMStore`, `Identity`, `DelegatedCredential`
- 7 `IdentityType` values: human, agent, model, api_key, service_account, mcp_server, service
- RBAC with `Permission` enum (25 permissions) and role→permission mapping for 6 roles
- Delegation uses strict permission intersection — agent can never exceed delegating user's permissions
- Cross-tenant delegation raises `PermissionError` (tenant isolation enforced)
- `revoke_identity()` immediately sets `is_active=False` on the identity record
- Short-lived credentials with configurable `ttl_hours`; negative TTL produces an immediately-expired credential

**Phase 4C — Agent Runtime Security**
- `v4/security/agent_runtime.py` — `AgentRuntimeSecurity`, `AgentSession`, `InjectionAssessment`, `OutputValidationResult`
- Tool allowlist per session — calls to tools not in the allowlist are blocked and recorded
- Per-session spend limit (`max_spend_usd`); enforced on `authorize_tool_call` after `record_tool_execution`
- `InputSource` enum: USER_DIRECT, MODEL_OUTPUT, TOOL_RESPONSE, RAG_DOCUMENT, EXTERNAL_API, SYSTEM_PROMPT
- Multi-signal injection assessment (not keyword-only); `is_heuristic=True` always; `limitation` disclaimer always present
- Output validation with pattern-based sensitive-data redaction (`sk-`, API keys, tokens); `limitation` disclaimer present
- All `ToolCallRecord` events stored for audit; execution blocked on terminated sessions

**Phase 4D — Model Security and Supply Chain**
- `v4/security/model_supply_chain.py` — `ModelSupplyChainSecurity`, `ModelSecurityAssessment`, `ModelRiskRecord`
- `assess_model()` evaluates: format risk (pickle=UNSAFE, safetensors=SAFE), revision hash verification, licence risk, custom code detection, publisher provenance
- Revision mismatch → CRITICAL finding with MITRE ATLAS references (AML.T0010, AML.T0049)
- `custom_code_detected=True` for any config containing `trust_remote_code`, `auto_map`, `custom_pipelines`
- `is_cleared_for_deployment=False` by default; `clear_for_deployment()` raises `PermissionError` for system actors
- CRITICAL overall_risk models cannot be cleared by any single reviewer — raises `PermissionError`
- Assessment carries a `limitation` disclaimer: not a security certification

**Phase 4E — MCP and Tool Security**
- `v4/security/mcp_tool_security.py` — `MCPToolSecurityRegistry`, `MCPServer`, `RegisteredTool`, `ToolExecutionRecord`
- Server and tool registration with explicit human `registered_by` / `approver_id` (system actors raise `PermissionError`)
- Tools remain `PENDING_REVIEW` until explicitly approved; unapproved tools block all execution
- Scope-based authorization: agent must hold all `required_scopes` for the tool
- Tenant isolation enforced on every `authorize_execution()` call
- HIGH_IMPACT_SCOPE tools set `approval_required=True` on execution records
- Cross-tenant tool access always blocked; `blocked_reason` recorded on every rejected execution

**Phase 4F — Governance and Human Approvals**
- `v4/security/governance_approvals.py` — `GovernanceApprovalEngine`, `ApprovalRequest`, `GovDecisionResult`, `GovPolicy`
- 8 default governance policies: high-risk model deploy, low-risk model deploy, agent execute, external API access, sensitive data access, high GPU spend (≥\$100), normal GPU spend, high-impact tool execute
- `evaluate()` auto-creates an `ApprovalRequest` when decision is REQUIRE_APPROVAL
- `SYSTEM_ACTOR_IDS` check: `{"system", "auto", "automated", "orquanta", ""}` are rejected on all approve/reject calls
- Approval creates an immutable audit log entry via `_audit_log`
- `get_audit_log()` returns all governance decisions and approval actions

**Phase 4G — AI Risk Register and Compliance Evidence**
- `v4/security/risk_register.py` — `AIRiskRegister`, `RiskEntry`, `EvidenceItem`, `CONTROL_CATALOGUE`
- 4 seed risks pre-loaded on init: prompt injection, supply chain poisoning, data exfiltration, bias and fairness
- `CONTROL_CATALOGUE` covers: NIST AI RMF (GOVERN/MAP/MEASURE/MANAGE), OWASP LLM Top 10 (LLM01–LLM10), MITRE ATLAS (AML.T*), ISO 42001, EU AI Act
- `add_evidence()` validates `control_id` against catalogue; unknown controls return `None` (never auto-approved)
- Every `EvidenceItem` carries a `disclaimer` field: not a compliance certification
- `generate_risk_report()` includes explicit non-certification disclaimer in all outputs
- `export_evidence_json()` for structured compliance export per tenant

**Phase 4H — AI Trust Centre Frontend**
- `v4/frontend/src/pages/TrustCentrePage.jsx` — 8-tab enterprise security dashboard
- Tabs: Overview, Policy Engine, Identity & Access, Model Security, MCP & Tools, Governance, Risk Register, Audit Log
- No decorative security indicators; no fake "protected" status badges
- Route: `/trust`
- API router: `v4/api/routers/trust_centre.py` — `trust_router` at `/api/v1/trust/*` with 40+ endpoints
- Registered in `v4/api/main.py` via try/except injection block (graceful degradation on import error)

### Tests
- `v4/phase4_tests.py` — 66 new synchronous tests; all pass
- **Total test count: 153 / 153 pass** (87 existing Phase 3 + 66 Phase 4)
- Coverage: PolicyEngine (10), IAM (7), AgentRuntime (10), ModelSupplyChain (10), MCPToolSecurity (8), GovernanceApprovals (8), RiskRegister (10), Apache headers (3)

### Security Guarantees
- Cross-tenant access: DENY always, checked first before any policy
- System actor IDs rejected on all human-approval-required operations: `system`, `auto`, `automated`, `orquanta`, `""`
- Injection detection: always multi-signal, `is_heuristic=True` always, limitation disclaimer always present
- Supply chain clearance: CRITICAL risk → `PermissionError`; system actor → `PermissionError`
- Delegation: strict subset intersection — agent can never hold permissions the delegating user does not have

### Environment Variables
- No new environment variables required for Phase 4

## [0.7.0] — 2026-11-21

### Added — Phase 3E–3H: Inference Engine Completion, Deployment Wizard, Benchmarking, Governance & Security

**Phase 3E — Unified Inference Engine Interface**
- `v4/inference/engine_interface.py` — `InferenceEngine` ABC standardising vLLM and SGLang behind one interface
- `VLLMEngine` and `SGLangEngine` with `build_startup_command()`, `health_check()`, `verify_model_loaded()`, `wait_for_ready()`, `cleanup_resources()`
- `DeploymentLifecycle` state machine: PENDING → PROVISIONING → STARTING → MODEL_LOADING → HEALTH_CHECK → READY → STOPPING → STOPPED / FAILED
- State transitions are strictly validated; terminal states (FAILED, STOPPED) are immutable
- Deployment cannot be marked READY without passing health check and model verification

**Phase 3F — 5-Step Deployment Wizard**
- `v4/api/routers/deployment_wizard.py` — `wizard_router` with full session lifecycle
  - `POST /api/v1/wizard/sessions` — create session
  - `GET  /api/v1/wizard/sessions/{id}` — get session state
  - `POST /api/v1/wizard/sessions/{id}/step/model` — select and validate model
  - `POST /api/v1/wizard/sessions/{id}/step/engine` — select engine + GPU, run compatibility check
  - `POST /api/v1/wizard/sessions/{id}/step/provider` — select provider + region, compute cost estimate
  - `POST /api/v1/wizard/sessions/{id}/step/review` — governance evaluation (PolicyDecisionResult)
  - `POST /api/v1/wizard/sessions/{id}/step/deploy` — explicit confirmed=true required; respects governance BLOCKED
  - `DELETE /api/v1/wizard/sessions/{id}` — cancel session
- Tenant isolation: session locked to creating `user_id`; cross-user access returns HTTP 403
- Step ordering enforced: each step requires the prior step to be completed (HTTP 409 if violated)
- Sessions expire after 2 hours; expired sessions return HTTP 410
- Never auto-deploys: deploy step requires explicit `confirmed: true`
- `v4/frontend/src/pages/DeploymentWizardPage.jsx` — 5-step React wizard with live backend integration, compat check, governance decision display, status polling

**Phase 3G — Benchmarking Engine**
- `v4/inference/benchmark_engine.py` — `BenchmarkRunner` with live HTTP and synthetic mock modes
  - `BenchmarkConfig` dataclass: model, engine, quant, GPU, context length, num_requests, concurrency, prompt_tokens, revision, software_version, test_dataset_hash
  - `BenchmarkResult` dataclass: TTFT, TPS, E2E latency, P50/P95/P99, throughput_rps, GPU util, GPU mem, cost/1M tokens, cost/task, failure_rate, `is_measured` (bool — true only for live endpoint), `is_mock` (bool), test_methodology, raw_latencies_ms (capped at 100)
  - `is_measured` and `is_mock` are never mixed — synthetic data is always clearly labelled
  - `load_test_prompts(seed, count, tokens)` — reproducible prompt generation from fixed seed
  - `compare_benchmarks(a_id, b_id)` — structured diff with `winner_latency`, `winner_throughput`, statistical significance flag
  - `get_leaderboard(model_id)` — TPS-ranked results
- `v4/api/routers/benchmark.py` — `bench_router`
  - `POST /api/v1/benchmarks` — start benchmark (validates deployment status)
  - `GET  /api/v1/benchmarks` — list runs (filter by model_id)
  - `GET  /api/v1/benchmarks/{id}` — get result
  - `GET  /api/v1/benchmarks/compare?a=&b=` — compare two runs
  - `GET  /api/v1/benchmarks/leaderboard?model_id=` — ranked leaderboard

**Phase 3H — Model Governance**
- `v4/inference/governance.py` — `GovernanceEngine` with full audit trail
  - `verify_licence()` — records licence, commercial permissions, sharealike constraints
  - `evaluate_deployment()` — returns `PolicyDecisionResult` (APPROVED / REQUIRES_REVIEW / BLOCKED)
  - Unknown models always return REQUIRES_REVIEW; NC licences + commercial use = BLOCKED
  - `approve_deployment()` — requires non-system `approver_id`; raises `ValueError` for `approver_id="system"`
  - `revoke_approval()` — records revoker and reason in audit trail
  - `get_audit_trail(model_id)` — full immutable event log
- Governance gate integrated into wizard step/review and step/deploy

**Objective 6 — Hardened API Key Manager**
- `v4/inference/api_key_manager.py` — `APIKeyManager`
  - SHA-256 hash-only storage: raw key returned once at generation, never stored
  - `generate_key()` returns `(raw_key, InferenceAPIKey)` — raw key has `sk-orq-` prefix
  - Keys expire after configurable TTL (default 90 days, env `INFERENCE_KEY_TTL_DAYS`)
  - `validate_key()` checks hash, revocation, activity, expiry
  - `has_scope(record_or_id, scope)` — accepts record or key_id string
  - `check_and_deduct_budget(record_or_id, cost_usd)` — thread-safe via `threading.Lock`; accepts record or key_id string
  - `check_rate(record)` — sliding-window rate limiter (60s window)
  - `revoke_key(key_id)` — sets `is_revoked=True`, `is_active=False`

**Objective 7 — AI Security Foundation**
- `v4/inference/security_foundation.py` — `SecurityEvaluator`
  - `check_tenant_isolation(request_tenant_id, resource_tenant_id)` — cross-tenant access logs HIGH severity event and returns False
  - `evaluate_prompt(prompt, user_id)` — heuristic prompt injection detection; always returns `is_heuristic=True` and `limitation` disclaimer
  - `evaluate_supply_chain(model_id, revision, expected_revision)` — revision and checksum verification; mismatch logs HIGH severity
  - `get_security_events(severity, limit)` — structured audit event retrieval
  - All security decisions include explicit methodology disclaimers

**Developer Ecosystem — CLI Upgrade**
- `orquanta_cli.py` — added three new subcommand groups:
  - `orquanta models list/search/compat` — list registry, search HF, check GPU compatibility
  - `orquanta deploy start/list/status/stop` — deploy and manage model deployments
  - `orquanta benchmark run/results` — start benchmarks and list results
  - All CLI commands display `is_mock` indicator (🧪) to prevent mock/real confusion

**Router Registration**
- `v4/api/main.py` — Phase 3E-H routers registered via try/except block:
  - `/api/v1/wizard/sessions` — deployment wizard
  - `/api/v1/benchmarks` — benchmark API
- `v4/frontend/src/App.jsx` — `/deploy` route added for `DeploymentWizardPage`

### Changed
- `v4/inference/api_key_manager.py` — `has_scope()` and `check_and_deduct_budget()` now accept either a record object or a key_id string for ergonomic API use

### Environment Variables
- `INFERENCE_KEY_TTL_DAYS` — API key lifetime in days (default: 90)

### Tests
- `v4/phase3eh_tests.py` — 50 new tests covering Phase 3E–3H: 50/50 pass
- Full regression: **87/87 tests pass** (37 Phase 3A–3D + 50 Phase 3E–3H)
- Frontend build: **2800 modules transformed, 0 errors**

## [0.6.0] — 2026-11-21

### Added — Phase 3: Open-Source Model Platform & Inference Infrastructure

#### Phase 3A — LiteLLM Inference Gateway (`v4/inference/gateway.py`)
- Unified OpenAI-compatible inference proxy with multi-provider routing
- Virtual API key system: `sk-orq-...` keys with per-tenant budget limits, rate limits, and model permissions
- Provider routing table: Groq (LLaMA 3.1 70B/8B, Mixtral), OpenAI (GPT-4o), Anthropic (Claude 3.5 Sonnet)
- Token accounting: input/output token counting → USD cost estimation
- Request logging with provider credential redaction (never logged or returned)
- Mock mode: `USE_REAL_INFERENCE=false` returns labelled `[MOCK]` responses for testing
- Fallback chain: multi-provider fallback on failure

#### Phase 3A — OpenAI-Compatible Inference API (`v4/api/routers/inference.py`)
- `POST /v1/chat/completions` — OpenAI-compatible chat completions
- `GET /v1/models` — list routed models with OrQuanta metadata
- `POST /v1/embeddings` — embedding endpoint (mock; real via vLLM deployment in 3D)
- Authenticates `sk-orq-...` inference keys and user JWTs
- Rate limiting per tenant via sliding window
- Budget enforcement blocks requests when tenant budget exhausted

#### Phase 3B — Model Registry & Hugging Face Integration (`v4/inference/model_registry.py`)
- Curated registry of 10 models: LLaMA 3.1 (405B/70B/8B), DeepSeek-V3/R1, Qwen 2.5 72B, Mixtral 8×7B, Gemma 2 27B, Phi-4, BGE-M3
- Full metadata: publisher, family, revision, context length, parameter count, quantisation options, VRAM estimates, GPU requirements
- Licence database: 14 licences mapped (MIT, Apache-2.0, LLaMA 3, Gemma, DeepSeek, OpenRAIL, CC variants, etc.)
- `commercial_ok` field populated from licence database; unknown licences explicitly flagged
- `GET /api/v1/models` — registry listing with family/engine/commercial filters and search
- `GET /api/v1/models/{id}` — model detail with GPU recommendations
- `GET /api/v1/models/search/hf` — real-time Hugging Face Hub search (read-only metadata only)
- `GET /api/v1/models/fetch/hf` — single HF model metadata fetch
- Runtime model registration API for custom models
- Never downloads model weights or executes untrusted model code

#### Phase 3C — GPU Compatibility Engine (`v4/inference/gpu_compatibility.py`)
- Hardware database: 20 GPU models (H100, A100, A40, A30, A10, L40S, L4, RTX 4090/3090, T4, V100, P100)
- Quantisation VRAM factors: FP32, FP16, BF16, INT8, INT4, AWQ, GPTQ, GGUF
- Engine-to-architecture compatibility enforcement (vLLM sm_70+, SGLang sm_80+)
- Status: `compatible` | `compatible_with_constraints` | `incompatible` | `insufficient_information`
- Constraint suggestions: automatically proposes lower quantisation if model doesn't fit
- KV-cache overhead modelling (15% overhead + long-context scaling)
- Rough throughput estimation in tokens/second (explicitly labelled as estimate)
- `POST /api/v1/models/check-compatibility` — API endpoint
- `GET /api/v1/models/gpus` — GPU hardware database endpoint
- `recommend_gpus_for_model()` — sorted list of compatible GPU configs for a model

#### Phase 3D — vLLM/SGLang Deployment Adapter (`v4/inference/vllm_adapter.py`)
- vLLM startup command builder: tensor parallelism, quantisation flags, context length cap
- SGLang startup command builder
- Deployment spec builder (JSON-serialisable for Celery)
- Health check waiter: polls `/health` until HTTP 200 (never marks ready on non-200)
- Mock deployment clearly labelled `[MOCK]`; `is_real=false` without real providers
- `POST /api/v1/deployments` — one-click deployment with compatibility pre-check
- `GET /api/v1/deployments` — list deployments
- `GET /api/v1/deployments/{id}` — deployment detail
- `DELETE /api/v1/deployments/{id}` — stop and clean up

#### Frontend — Model Hub Upgrade (`v4/frontend/src/pages/ModelHubPage.jsx`)
- Live backend integration: fetches real registry from `/api/v1/models` with static fallback
- `LiveBadge` component: green "Live Registry" / amber "Demo Data"
- HF Hub search panel: real-time search with licence display and in-registry check
- GPU Compatibility modal: interactive GPU/count/quantisation/engine selector
- Compatibility result display: status, VRAM breakdown, constraints, warnings, TPS estimate
- Licence badge: Commercial OK / Non-Commercial / Unknown with accurate display
- Engine chips: vLLM / SGLang / transformers
- Filter by family, commercial-only toggle, full-text search
- Error banner when API unavailable (shows curated fallback with explicit label)

### New Environment Variables (Phase 3)
| Variable | Default | Description |
|---|---|---|
| `USE_REAL_INFERENCE` | `false` | Enable real LLM inference via provider keys |
| `LITELLM_BASE_URL` | — | External LiteLLM proxy URL (optional) |
| `LITELLM_MASTER_KEY` | — | LiteLLM master key (never exposed to clients) |
| `GROQ_API_KEY` | — | Groq API key for Llama/Mixtral inference |
| `HF_TOKEN` | — | Read-only Hugging Face token for model metadata |
| `VLLM_DOCKER_IMAGE` | `vllm/vllm-openai:v0.6.4` | vLLM Docker image for deployments |
| `SGLANG_DOCKER_IMAGE` | `lmsysorg/sglang:v0.4.1-cu121` | SGLang Docker image |
| `VLLM_STARTUP_TIMEOUT_SECONDS` | `600` | Max wait time for model loading |
| `INFERENCE_DEFAULT_BUDGET_USD` | `10.0` | Default per-key inference budget |
| `INFERENCE_TIMEOUT_SECONDS` | `120` | Inference request timeout |

### Test Results — Phase 3
- **37/37 Phase 3 tests PASS** (pytest, Python 3.11, 0.22s)
- **Frontend build: 2799 modules, 0 errors**

### Open-Source Compliance (Phase 3)
- Apache 2.0 header on all Phase 3 source files
- Third-party licence obligations documented in requirements.txt
- vLLM (Apache 2.0), SGLang (Apache 2.0), HuggingFace Hub (Apache 2.0)
- Licence obligations for deployed models tracked per-deployment

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
