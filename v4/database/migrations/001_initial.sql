-- BomaX Agentic v4.0 — PostgreSQL Schema
-- Run: psql -U bomax -d bomax -f 001_initial.sql
-- Or via Alembic: alembic upgrade head

-- =====================================
-- Extensions
-- =====================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search on goals

-- =====================================
-- Organizations (multi-tenant)
-- =====================================
CREATE TABLE IF NOT EXISTS organizations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(200) NOT NULL,
    slug            VARCHAR(100) UNIQUE NOT NULL,      -- URL-safe name
    plan            VARCHAR(50) NOT NULL DEFAULT 'starter',  -- starter/pro/enterprise
    daily_budget_usd NUMERIC(12, 4) DEFAULT 5000.00,
    monthly_quota_usd NUMERIC(12, 4) DEFAULT 50000.00,
    stripe_customer_id VARCHAR(100),
    stripe_subscription_id VARCHAR(100),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================
-- Users
-- =====================================
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    email           VARCHAR(320) UNIQUE NOT NULL,
    hashed_password VARCHAR(200) NOT NULL,
    name            VARCHAR(200),
    role            VARCHAR(50) NOT NULL DEFAULT 'operator',  -- admin/operator/viewer
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS users_email_idx ON users(email);
CREATE INDEX IF NOT EXISTS users_org_idx ON users(organization_id);

-- =====================================
-- API Keys
-- =====================================
CREATE TABLE IF NOT EXISTS api_keys (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,               -- Human-readable label
    key_prefix      VARCHAR(20) NOT NULL,                -- First 8 chars for lookup
    key_hash        VARCHAR(200) NOT NULL UNIQUE,        -- SHA-256 of full key
    scopes          TEXT[] NOT NULL DEFAULT '{"read"}',  -- read / write / admin
    expires_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS api_keys_prefix_idx ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS api_keys_org_idx ON api_keys(organization_id);

-- =====================================
-- Goals (natural language goals)
-- =====================================
CREATE TABLE IF NOT EXISTS goals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    raw_text        TEXT NOT NULL,
    status          VARCHAR(50) NOT NULL DEFAULT 'accepted',
    budget_usd      NUMERIC(12, 4),
    cost_incurred_usd NUMERIC(12, 4) NOT NULL DEFAULT 0,
    plan            JSONB,              -- Decomposed task plan
    reasoning_log   JSONB NOT NULL DEFAULT '[]',
    completed_tasks UUID[] NOT NULL DEFAULT '{}',
    failed_tasks    UUID[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS goals_org_idx ON goals(organization_id);
CREATE INDEX IF NOT EXISTS goals_user_idx ON goals(user_id);
CREATE INDEX IF NOT EXISTS goals_status_idx ON goals(status);
CREATE INDEX IF NOT EXISTS goals_created_idx ON goals(created_at DESC);
-- Fuzzy text search on goal descriptions
CREATE INDEX IF NOT EXISTS goals_text_trgm_idx ON goals USING GIN(raw_text gin_trgm_ops);

-- =====================================
-- GPU Instances
-- =====================================
CREATE TABLE IF NOT EXISTS instances (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    provider_instance_id VARCHAR(200) UNIQUE NOT NULL,   -- AWS instance-id / GCP VM name / etc.
    provider        VARCHAR(50) NOT NULL,
    region          VARCHAR(100) NOT NULL,
    gpu_type        VARCHAR(100) NOT NULL,
    gpu_count       INTEGER NOT NULL DEFAULT 1,
    vram_gb         INTEGER NOT NULL,
    hourly_rate_usd NUMERIC(10, 6) NOT NULL,
    spot            BOOLEAN NOT NULL DEFAULT TRUE,
    status          VARCHAR(50) NOT NULL DEFAULT 'running',
    public_ip       INET,
    private_ip      INET,
    tags            JSONB NOT NULL DEFAULT '{}',
    launched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    terminated_at   TIMESTAMPTZ,
    total_cost_usd  NUMERIC(12, 6) NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS instances_org_idx ON instances(organization_id);
CREATE INDEX IF NOT EXISTS instances_provider_idx ON instances(provider, status);
CREATE INDEX IF NOT EXISTS instances_status_idx ON instances(status);
CREATE INDEX IF NOT EXISTS instances_gpu_idx ON instances(gpu_type);

-- =====================================
-- Jobs
-- =====================================
CREATE TABLE IF NOT EXISTS jobs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    goal_id         UUID REFERENCES goals(id) ON DELETE SET NULL,
    instance_id     UUID REFERENCES instances(id) ON DELETE SET NULL,
    intent          TEXT NOT NULL,
    gpu_type        VARCHAR(100) NOT NULL,
    gpu_count       INTEGER NOT NULL DEFAULT 1,
    provider        VARCHAR(50),
    required_vram_gb INTEGER,
    max_cost_usd    NUMERIC(12, 4),
    max_runtime_minutes INTEGER,
    priority_score  NUMERIC(5, 4) NOT NULL DEFAULT 0.5,
    status          VARCHAR(50) NOT NULL DEFAULT 'queued',  -- queued/running/completed/failed/cancelled
    exit_code       INTEGER,
    cost_incurred_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    duration_seconds NUMERIC(10, 2),
    logs_url        TEXT,                -- S3/GCS URL to stored logs
    artifacts       JSONB NOT NULL DEFAULT '[]',
    gpu_peak_util_pct NUMERIC(5, 2),
    gpu_peak_mem_gb  NUMERIC(8, 2),
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_org_idx ON jobs(organization_id);
CREATE INDEX IF NOT EXISTS jobs_user_idx ON jobs(user_id);
CREATE INDEX IF NOT EXISTS jobs_goal_idx ON jobs(goal_id);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_created_idx ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_gpu_type_idx ON jobs(gpu_type);

-- =====================================
-- Agent Decisions / Audit Log
-- =====================================
CREATE TABLE IF NOT EXISTS audit_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    goal_id         UUID REFERENCES goals(id) ON DELETE SET NULL,
    job_id          UUID REFERENCES jobs(id) ON DELETE SET NULL,
    agent_name      VARCHAR(100) NOT NULL,
    action          VARCHAR(200) NOT NULL,
    reasoning       TEXT,
    payload         JSONB NOT NULL DEFAULT '{}',
    outcome         VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending/success/error_*/denied
    cost_impact_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    duration_ms     NUMERIC(10, 2),
    safety_approved BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS audit_org_idx ON audit_log(organization_id);
CREATE INDEX IF NOT EXISTS audit_agent_idx ON audit_log(agent_name);
CREATE INDEX IF NOT EXISTS audit_outcome_idx ON audit_log(outcome);
CREATE INDEX IF NOT EXISTS audit_created_idx ON audit_log(created_at DESC);

-- =====================================
-- Cost Records (billing events)
-- =====================================
CREATE TABLE IF NOT EXISTS cost_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    job_id          UUID REFERENCES jobs(id) ON DELETE SET NULL,
    instance_id     UUID REFERENCES instances(id) ON DELETE SET NULL,
    provider        VARCHAR(50) NOT NULL,
    gpu_type        VARCHAR(100) NOT NULL,
    gpu_count       INTEGER NOT NULL DEFAULT 1,
    cost_usd        NUMERIC(12, 6) NOT NULL,
    duration_seconds NUMERIC(12, 2) NOT NULL,
    hourly_rate_usd NUMERIC(10, 6) NOT NULL,
    billing_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS cost_org_idx ON cost_records(organization_id);
CREATE INDEX IF NOT EXISTS cost_date_idx ON cost_records(billing_date DESC);
CREATE INDEX IF NOT EXISTS cost_provider_idx ON cost_records(provider);
CREATE INDEX IF NOT EXISTS cost_job_idx ON cost_records(job_id);

-- =====================================
-- Spot Price History (cache + analytics)
-- =====================================
CREATE TABLE IF NOT EXISTS spot_price_history (
    id              BIGSERIAL PRIMARY KEY,
    provider        VARCHAR(50) NOT NULL,
    region          VARCHAR(100) NOT NULL,
    gpu_type        VARCHAR(100) NOT NULL,
    instance_type   VARCHAR(100) NOT NULL,
    price_usd_hr    NUMERIC(10, 6) NOT NULL,
    availability    VARCHAR(20),
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS spot_provider_gpu_idx ON spot_price_history(provider, gpu_type, recorded_at DESC);

-- =====================================
-- Triggers: updated_at auto-update
-- =====================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER organizations_updated_at BEFORE UPDATE ON organizations FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER goals_updated_at BEFORE UPDATE ON goals FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =====================================
-- Default admin organization
-- =====================================
INSERT INTO organizations (id, name, slug, plan, daily_budget_usd)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'BomaX Admin', 'bomax-admin', 'enterprise', 50000.00
) ON CONFLICT (slug) DO NOTHING;
