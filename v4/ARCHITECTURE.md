# OrQuanta Agentic v1.0 — Complete Architecture

**Codename:** NEXUS  
**Version:** 4.0.0  
**Date:** February 2026  
**Status:** Production Architecture

---

## 1. System Overview

OrQuanta Agentic v1.0 ("NEXUS") is an LLM-powered, multi-agent cloud GPU
orchestration platform. It wraps and supersedes the v3.8 OrMind kernel
with a full agentic layer: natural-language goal intake, autonomous
task decomposition, specialized sub-agents, vector memory, and a real-time
React dashboard — all communicating via Redis message queues.

---

## 2. Folder / File Structure

```
v4/
├── agents/
│   ├── __init__.py
│   ├── master_orchestrator.py       # Central LLM brain
│   ├── scheduler_agent.py           # GPU job queue + bin-packing
│   ├── cost_optimizer_agent.py      # Cost monitoring + spot negotiation
│   ├── healing_agent.py             # Health monitoring + auto-recovery
│   ├── forecast_agent.py            # Demand forecasting (LSTM/Prophet)
│   ├── memory_manager.py            # ChromaDB vector memory
│   ├── tool_registry.py             # All callable tools for agents
│   ├── safety_governor.py           # Guardrails + audit trail
│   ├── llm_reasoning_engine.py      # Unified LLM interface
│   └── orquanta_kernel_bridge.py       # v3.8 compatibility bridge
│
├── api/
│   ├── __init__.py
│   ├── main.py                      # FastAPI entry point
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── goals.py                 # POST /goals
│   │   ├── jobs.py                  # CRUD /jobs
│   │   ├── agents.py                # Agent status + control
│   │   ├── metrics.py               # Real-time metrics
│   │   └── audit.py                 # Audit trail
│   ├── websocket/
│   │   ├── __init__.py
│   │   └── agent_stream.py          # Real-time WS reasoning stream
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py                  # JWT authentication
│   │   └── rate_limit.py            # API rate limiting
│   └── models/
│       ├── __init__.py
│       └── schemas.py               # All Pydantic models
│
├── frontend/
│   ├── package.json
│   ├── tailwind.config.js
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── index.css
│       ├── pages/
│       │   ├── Dashboard.jsx
│       │   ├── GoalSubmit.jsx
│       │   ├── AgentMonitor.jsx
│       │   ├── JobManager.jsx
│       │   ├── CostAnalytics.jsx
│       │   └── AuditLog.jsx
│       └── components/
│           ├── AgentCard.jsx
│           ├── GPUMetricsChart.jsx
│           └── GoalProgressTracker.jsx
│
├── infra/
│   ├── docker-compose.yml
│   ├── Dockerfile.api
│   ├── Dockerfile.frontend
│   ├── Dockerfile.agents
│   ├── prometheus.yml
│   ├── nginx/
│   │   └── nginx.conf
│   ├── grafana/
│   │   └── dashboard.json
│   └── kubernetes/
│       ├── deployment.yaml
│       └── service.yaml
│
├── tests/
│   ├── __init__.py
│   ├── test_orchestrator.py
│   ├── test_agents.py
│   ├── test_api.py
│   ├── test_safety.py
│   └── test_memory.py
│
├── .env.example
├── LAUNCH_GATE_V4.py
├── load_test.py
├── README.md
├── API_DOCS.md
├── AGENT_GUIDE.md
├── DEPLOYMENT_GUIDE.md
└── ROADMAP.md
```

---

## 3. Technology Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Agent Orchestration | LangChain 0.3 | Mature ReAct + tool-calling support |
| LLM Backbone | OpenAI GPT-4o / Anthropic Claude 3.5 | Best reasoning + structured output |
| Vector Memory | ChromaDB | Lightweight, embedded, no infra overhead |
| Message Queue | Redis Streams | Low-latency agent comms, native pub/sub |
| API Framework | FastAPI 0.115 | Async-native, WebSocket, auto OpenAPI |
| Frontend | React 18 + Tailwind CSS | Fast dev, rich ecosystem |
| Database | PostgreSQL 16 | ACID, JSONB for flexible job metadata |
| Async Tasks | Celery 5 | Distributed task execution |
| Containers | Docker + Compose | Reproducible deployments |
| Metrics | Prometheus + Grafana | Industry standard, rich GPU dashboards |
| Auth | JWT (PyJWT) | Stateless, scalable |

---

## 4. Data Flow Diagram

```
USER / CLIENT
     │
     │  HTTP / WebSocket
     ▼
┌─────────────────────┐
│   NGINX Reverse     │
│   Proxy (:80/443)   │
└─────────┬───────────┘
          │
     ┌────┴────┐
     │         │
     ▼         ▼
┌─────────┐ ┌──────────────┐
│ React   │ │  FastAPI     │
│ Frontend│ │  REST/WS API │
│ :3000   │ │  :8000       │
└─────────┘ └──────┬───────┘
                   │
          ┌────────┼────────┐
          │        │        │
          ▼        ▼        ▼
    ┌─────────┐ ┌──────┐ ┌──────────┐
    │Postgres │ │Redis │ │ChromaDB  │
    │(Jobs,   │ │Stream│ │(Vector   │
    │ Users,  │ │Queue │ │ Memory)  │
    │ Audit)  │ │      │ │          │
    └─────────┘ └──┬───┘ └──────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
    ▼              ▼              ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│Master    │ │Scheduler │ │Cost Opt  │
│Orchestr. │ │Agent     │ │Agent     │
└──────────┘ └──────────┘ └──────────┘
    │
    ├──────────────────────┐
    ▼                      ▼
┌──────────┐          ┌──────────┐
│Healing   │          │Forecast  │
│Agent     │          │Agent     │
└──────────┘          └──────────┘
    │
    ▼
┌─────────────────────┐
│OrQuanta v3.8 Kernel   │
│(Legacy Bridge)      │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│GPU Cloud Providers  │
│AWS / GCP / Azure /  │
│CoreWeave (Mock API) │
└─────────────────────┘
```

---

## 5. Agent Communication Diagram

```
Goal Input (NL)
      │
      ▼
┌─────────────────────────────────────────┐
│          MasterOrchestrator             │
│  LLM: GPT-4o                           │
│  Pattern: ReAct (Reason→Act→Observe)   │
│  Publishes tasks to Redis Stream        │
└────────┬────────────────────────────────┘
         │  Redis Streams (topic per agent)
    ┌────┼────────────────────┐
    │    │    │    │          │
    ▼    ▼    ▼    ▼          ▼
  SCH  COST HEAL  FORE    SAFETY
  Agent Agent Agent Agent  Governor
    │    │    │    │          │
    └────┴────┴────┴──────────┘
                  │
          All agents publish
          results back to
       "orchestrator:results" stream
                  │
          MasterOrchestrator
          aggregates + decides
          next action
                  │
         Memory Manager persists
         all events to ChromaDB
```

---

## 6. Database Schema (PostgreSQL)

```sql
-- Users
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    hashed_pw   TEXT NOT NULL,
    role        TEXT DEFAULT 'user',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Goals (natural-language inputs)
CREATE TABLE goals (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    raw_text    TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',  -- pending/decomposing/running/done/failed
    plan        JSONB,                   -- LLM-generated task decomposition
    result      JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Jobs
CREATE TABLE jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id     UUID REFERENCES goals(id),
    user_id     UUID REFERENCES users(id),
    provider    TEXT NOT NULL,           -- aws/gcp/azure/coreweave
    gpu_type    TEXT NOT NULL,           -- H100/A100/T4
    gpu_count   INT NOT NULL,
    status      TEXT DEFAULT 'pending',  -- pending/running/completed/failed/cancelled
    cost_usd    NUMERIC(12,4),
    metadata    JSONB,
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Audit Trail
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    agent_name  TEXT NOT NULL,
    action      TEXT NOT NULL,
    reasoning   TEXT,
    payload     JSONB,
    outcome     TEXT,
    cost_impact NUMERIC(12,4),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Agent State
CREATE TABLE agent_state (
    agent_name  TEXT PRIMARY KEY,
    status      TEXT DEFAULT 'idle',     -- idle/thinking/acting/error
    last_action TEXT,
    metrics     JSONB,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 7. API Design Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/goals | Submit NL goal |
| GET | /api/v1/goals/{id} | Get goal status + plan |
| GET | /api/v1/jobs | List all jobs |
| POST | /api/v1/jobs | Create job directly |
| GET | /api/v1/jobs/{id} | Job detail |
| DELETE | /api/v1/jobs/{id} | Cancel job |
| GET | /api/v1/agents | All agent statuses |
| POST | /api/v1/agents/{name}/pause | Pause an agent |
| POST | /api/v1/agents/{name}/resume | Resume an agent |
| GET | /api/v1/metrics | Platform metrics |
| GET | /api/v1/audit | Audit log (paginated) |
| WS | /ws/agent-stream | Live agent reasoning feed |
| POST | /auth/register | Register user |
| POST | /auth/login | Get JWT token |

---

## 8. Backward Compatibility

`orquanta_kernel_bridge.py` wraps `orquanta_kernel_final.py` (v3.8) as a registered
LangChain tool named `legacy_or_mind`. Any agent can call it via the tool
registry. This provides a graceful deprecation window while the new agents
accumulate learning history in ChromaDB.

Migration timeline:
- v4.0: Bridge active, all new work goes through v4 agents
- v4.2: Bridge deprecated, v3.8 policy weights imported into v4 memory
- v5.0: v3.8 kernel retired
