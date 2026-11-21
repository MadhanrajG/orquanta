// OrQuanta AI Trust Centre — Phase 4H
// Enterprise security overview for models, agents, tools, policies and risk.
// No decorative security indicators — all data from real backend APIs.
import React, { useState, useEffect, useCallback } from 'react'

const API = import.meta.env.VITE_API_BASE_URL || ''

// ── Minimal fetch helper ──────────────────────────────────────────────────
async function apiFetch(path, opts = {}) {
  const token = localStorage.getItem('orquanta_token') || ''
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    ...opts,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// ── Tab definitions ───────────────────────────────────────────────────────
const TABS = [
  { id: 'overview',    label: 'Security Overview' },
  { id: 'policies',   label: 'Policy Engine' },
  { id: 'identities', label: 'Identity & Access' },
  { id: 'models',     label: 'Model Security' },
  { id: 'mcp',        label: 'MCP & Tools' },
  { id: 'governance', label: 'Governance' },
  { id: 'risks',      label: 'Risk Register' },
  { id: 'audit',      label: 'Audit Log' },
]

// ── Shared components ─────────────────────────────────────────────────────
function Badge({ value, map }) {
  const cfg = map?.[value] || { color: '#6b7280', bg: '#f3f4f6' }
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 4,
      fontSize: 11, fontWeight: 600, letterSpacing: '0.03em',
      color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.color}22`,
    }}>
      {value}
    </span>
  )
}

const DECISION_BADGE = {
  ALLOW:            { color: '#16a34a', bg: '#f0fdf4' },
  DENY:             { color: '#dc2626', bg: '#fef2f2' },
  REQUIRE_APPROVAL: { color: '#d97706', bg: '#fffbeb' },
  RESTRICTED:       { color: '#7c3aed', bg: '#f5f3ff' },
  REVIEW_REQUIRED:  { color: '#0284c7', bg: '#f0f9ff' },
}
const SEVERITY_BADGE = {
  CRITICAL: { color: '#7f1d1d', bg: '#fef2f2' },
  HIGH:     { color: '#dc2626', bg: '#fef2f2' },
  MEDIUM:   { color: '#d97706', bg: '#fffbeb' },
  LOW:      { color: '#16a34a', bg: '#f0fdf4' },
  INFO:     { color: '#6b7280', bg: '#f3f4f6' },
  UNKNOWN:  { color: '#6b7280', bg: '#f3f4f6' },
}
const STATUS_BADGE = {
  APPROVED:       { color: '#16a34a', bg: '#f0fdf4' },
  PENDING_REVIEW: { color: '#d97706', bg: '#fffbeb' },
  REJECTED:       { color: '#dc2626', bg: '#fef2f2' },
  SUSPENDED:      { color: '#6b7280', bg: '#f3f4f6' },
  PENDING:        { color: '#d97706', bg: '#fffbeb' },
  EXPIRED:        { color: '#6b7280', bg: '#f3f4f6' },
}

function Card({ title, children, action }) {
  return (
    <div style={{ background: '#fff', borderRadius: 8, border: '1px solid #e5e7eb', marginBottom: 16 }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #f3f4f6', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, fontSize: 14, color: '#111827' }}>{title}</span>
        {action}
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  )
}

function Table({ cols, rows, keyField }) {
  if (!rows || rows.length === 0) return <div style={{ color: '#9ca3af', fontSize: 13, padding: '8px 0' }}>No records.</div>
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            {cols.map(c => (
              <th key={c.key} style={{ textAlign: 'left', padding: '6px 10px', borderBottom: '2px solid #f3f4f6', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row[keyField] || i} style={{ borderBottom: '1px solid #f9fafb' }}>
              {cols.map(c => (
                <td key={c.key} style={{ padding: '7px 10px', color: '#374151', maxWidth: 260, wordBreak: 'break-word' }}>
                  {c.render ? c.render(row[c.key], row) : (row[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Stat({ label, value, sub, color }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '16px 20px', flex: 1, minWidth: 140 }}>
      <div style={{ fontSize: 24, fontWeight: 700, color: color || '#111827', marginBottom: 2 }}>{value}</div>
      <div style={{ fontSize: 12, color: '#6b7280', fontWeight: 600 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function Notice({ text, type = 'info' }) {
  const colors = { info: '#1d4ed8', warn: '#d97706', error: '#dc2626' }
  const bgs    = { info: '#eff6ff', warn: '#fffbeb', error: '#fef2f2' }
  return (
    <div style={{ background: bgs[type], border: `1px solid ${colors[type]}33`, borderRadius: 6, padding: '8px 12px', fontSize: 12, color: colors[type], marginBottom: 12 }}>
      {text}
    </div>
  )
}

function useApi(path, deps = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    apiFetch(path)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, deps)

  return { data, loading, error, reload: () => { setLoading(true); apiFetch(path).then(setData).catch(e => setError(e.message)).finally(() => setLoading(false)) } }
}

// ── Tab: Overview ─────────────────────────────────────────────────────────
function OverviewTab() {
  const { data: auditStats, loading: lA } = useApi('/api/v1/trust/audit/stats')
  const { data: risks, loading: lR }      = useApi('/api/v1/trust/risks')
  const { data: queue, loading: lQ }      = useApi('/api/v1/trust/governance/queue?status=PENDING')

  const critical = risks?.filter(r => r.severity === 'CRITICAL' && r.status === 'OPEN').length || 0
  const high     = risks?.filter(r => r.severity === 'HIGH'     && r.status === 'OPEN').length || 0
  const pending  = Array.isArray(queue) ? queue.length : 0

  return (
    <div>
      <Notice
        type="info"
        text="Security controls are enforced server-side. This dashboard reflects live policy decisions and audit data."
      />
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
        <Stat label="Total Audit Events"  value={lA ? '…' : auditStats?.total_events ?? 0} />
        <Stat label="DENY Decisions"      value={lA ? '…' : auditStats?.decision_breakdown?.DENY ?? 0}             color="#dc2626" />
        <Stat label="Pending Approvals"   value={lQ ? '…' : pending}                                               color="#d97706" />
        <Stat label="Critical Open Risks" value={lR ? '…' : critical}                                              color="#7f1d1d" />
        <Stat label="High Open Risks"     value={lR ? '…' : high}                                                  color="#dc2626" />
      </div>

      <Card title="Recent Policy Decisions">
        <AuditMiniTable />
      </Card>

      <Card title="Open Risk Summary">
        {lR ? <div>Loading…</div> : (
          <Table
            cols={[
              { key: 'severity',  label: 'Severity', render: v => <Badge value={v} map={SEVERITY_BADGE} /> },
              { key: 'category',  label: 'Category' },
              { key: 'title',     label: 'Title' },
              { key: 'asset_type', label: 'Asset Type' },
              { key: 'status',    label: 'Status',   render: v => <Badge value={v} map={STATUS_BADGE} /> },
            ]}
            rows={(risks || []).filter(r => r.status === 'OPEN').slice(0, 8)}
            keyField="risk_id"
          />
        )}
      </Card>
    </div>
  )
}

function AuditMiniTable() {
  const { data, loading } = useApi('/api/v1/trust/audit?limit=10')
  if (loading) return <div>Loading…</div>
  return (
    <Table
      cols={[
        { key: 'timestamp',     label: 'Time',     render: v => v?.slice(0, 19).replace('T', ' ') || '—' },
        { key: 'actor_id',      label: 'Actor' },
        { key: 'resource_type', label: 'Resource' },
        { key: 'action',        label: 'Action' },
        { key: 'decision',      label: 'Decision', render: v => <Badge value={v} map={DECISION_BADGE} /> },
      ]}
      rows={data || []}
      keyField="event_id"
    />
  )
}

// ── Tab: Policies ─────────────────────────────────────────────────────────
function PoliciesTab() {
  const { data, loading, reload } = useApi('/api/v1/trust/policies')
  const [evalForm, setEvalForm] = useState({ actor_id: '', actor_type: 'human', resource_type: 'model', resource_id: '', action: 'deploy' })
  const [evalResult, setEvalResult] = useState(null)
  const [evalLoading, setEvalLoading] = useState(false)

  const runEval = async () => {
    setEvalLoading(true)
    try {
      const r = await apiFetch('/api/v1/trust/policies/evaluate', { method: 'POST', body: JSON.stringify(evalForm) })
      setEvalResult(r)
    } catch (e) {
      setEvalResult({ error: e.message })
    } finally {
      setEvalLoading(false)
    }
  }

  return (
    <div>
      <Card title="Policy Catalogue">
        {loading ? <div>Loading…</div> : (
          <Table
            cols={[
              { key: 'name',          label: 'Policy Name' },
              { key: 'resource_type', label: 'Resource' },
              { key: 'action_pattern', label: 'Action Pattern' },
              { key: 'decision',      label: 'Decision', render: v => <Badge value={v} map={DECISION_BADGE} /> },
              { key: 'risk_level',    label: 'Risk',     render: v => <Badge value={v} map={SEVERITY_BADGE} /> },
              { key: 'version',       label: 'Version' },
            ]}
            rows={data || []}
            keyField="policy_id"
          />
        )}
      </Card>

      <Card title="Policy Evaluation Sandbox">
        <Notice type="info" text="Test a policy decision against the live enforcement engine." />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 12 }}>
          {['actor_id', 'actor_type', 'resource_type', 'resource_id', 'action'].map(field => (
            <div key={field}>
              <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 2 }}>{field}</label>
              <input
                value={evalForm[field]}
                onChange={e => setEvalForm(f => ({ ...f, [field]: e.target.value }))}
                style={{ width: '100%', padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13, boxSizing: 'border-box' }}
              />
            </div>
          ))}
        </div>
        <button
          onClick={runEval}
          disabled={evalLoading}
          style={{ padding: '7px 18px', background: '#1d4ed8', color: '#fff', border: 'none', borderRadius: 5, cursor: 'pointer', fontSize: 13 }}
        >
          {evalLoading ? 'Evaluating…' : 'Evaluate'}
        </button>
        {evalResult && (
          <div style={{ marginTop: 12, background: '#f9fafb', borderRadius: 6, padding: 12, fontSize: 12, fontFamily: 'monospace' }}>
            {evalResult.error
              ? <span style={{ color: '#dc2626' }}>{evalResult.error}</span>
              : <>
                  <div>Decision: <strong><Badge value={evalResult.decision} map={DECISION_BADGE} /></strong></div>
                  <div style={{ marginTop: 4 }}>Policy: {evalResult.policy_name} v{evalResult.policy_version}</div>
                  <div style={{ marginTop: 4 }}>Reason: {evalResult.reason}</div>
                  <div style={{ marginTop: 4 }}>Context hash: {evalResult.context_hash}</div>
                </>
            }
          </div>
        )}
      </Card>
    </div>
  )
}

// ── Tab: Identity & Access ────────────────────────────────────────────────
function IdentitiesTab() {
  const { data, loading, reload } = useApi('/api/v1/trust/identities')
  const [form, setForm] = useState({ name: '', identity_type: 'agent' })
  const [creating, setCreating] = useState(false)

  const create = async () => {
    setCreating(true)
    try {
      await apiFetch('/api/v1/trust/identities', { method: 'POST', body: JSON.stringify(form) })
      reload()
    } catch (e) {
      alert(e.message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div>
      <Card title="Create Identity" action={
        <div style={{ display: 'flex', gap: 8 }}>
          <input placeholder="Name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            style={{ padding: '5px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13, width: 160 }} />
          <select value={form.identity_type} onChange={e => setForm(f => ({ ...f, identity_type: e.target.value }))}
            style={{ padding: '5px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }}>
            {['human', 'agent', 'api_key', 'service_account', 'mcp_server'].map(t => <option key={t}>{t}</option>)}
          </select>
          <button onClick={create} disabled={creating || !form.name}
            style={{ padding: '5px 14px', background: '#1d4ed8', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 13 }}>
            {creating ? '…' : 'Create'}
          </button>
        </div>
      }>
        <Notice type="info" text="Agents default to minimal permissions (agent role). Permissions are explicitly scoped at delegation time. An agent never inherits unrestricted access." />
      </Card>

      <Card title="Identity Registry">
        {loading ? <div>Loading…</div> : (
          <Table
            cols={[
              { key: 'name',          label: 'Name' },
              { key: 'identity_type', label: 'Type' },
              { key: 'roles',         label: 'Roles', render: v => Array.isArray(v) ? v.join(', ') : v },
              { key: 'is_active',     label: 'Active', render: v => v ? 'Yes' : 'No' },
              { key: 'is_revoked',    label: 'Revoked', render: v => v ? <Badge value="REVOKED" map={{ REVOKED: { color: '#dc2626', bg: '#fef2f2' } }} /> : '—' },
              { key: 'created_at',    label: 'Created', render: v => v?.slice(0, 10) },
              { key: 'expires_at',    label: 'Expires', render: v => v ? v.slice(0, 10) : 'Never' },
            ]}
            rows={data || []}
            keyField="identity_id"
          />
        )}
      </Card>
    </div>
  )
}

// ── Tab: Model Security ───────────────────────────────────────────────────
function ModelSecurityTab() {
  const { data: assessments, loading, reload } = useApi('/api/v1/trust/models/assessments')
  const { data: risks } = useApi('/api/v1/trust/models/risks')
  const [form, setForm] = useState({ model_id: '', publisher: '', source_url: '', revision: 'main', licence: 'unknown', file_extensions: '.safetensors' })
  const [assessing, setAssessing] = useState(false)
  const [result, setResult] = useState(null)

  const assess = async () => {
    setAssessing(true)
    try {
      const payload = { ...form, file_extensions: form.file_extensions.split(',').map(s => s.trim()) }
      const r = await apiFetch('/api/v1/trust/models/assess', { method: 'POST', body: JSON.stringify(payload) })
      setResult(r)
      reload()
    } catch (e) {
      alert(e.message)
    } finally {
      setAssessing(false)
    }
  }

  return (
    <div>
      <Notice type="warn" text="A model is never marked safe solely because it comes from a popular repository. All assessments require human reviewer clearance before production deployment." />

      <Card title="Run Supply Chain Assessment">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 12 }}>
          {Object.entries(form).map(([k, v]) => (
            <div key={k}>
              <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 2 }}>{k}</label>
              <input value={v} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))}
                style={{ width: '100%', padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13, boxSizing: 'border-box' }} />
            </div>
          ))}
        </div>
        <button onClick={assess} disabled={assessing || !form.model_id}
          style={{ padding: '7px 18px', background: '#1d4ed8', color: '#fff', border: 'none', borderRadius: 5, cursor: 'pointer', fontSize: 13 }}>
          {assessing ? 'Assessing…' : 'Run Assessment'}
        </button>
        {result && (
          <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
              <Stat label="Overall Risk"   value={result.overall_risk}  color={SEVERITY_BADGE[result.overall_risk]?.color} />
              <Stat label="Format Risk"    value={result.format_risk}   color={result.format_risk === 'UNSAFE' ? '#dc2626' : '#16a34a'} />
              <Stat label="Findings"       value={result.findings?.length || 0} />
              <Stat label="Cleared"        value={result.is_cleared_for_deployment ? 'YES' : 'NO — Requires Reviewer'} color={result.is_cleared_for_deployment ? '#16a34a' : '#dc2626'} />
            </div>
            {result.findings?.map((f, i) => (
              <div key={i} style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, padding: '8px 12px', marginBottom: 6, fontSize: 12 }}>
                <strong><Badge value={f.severity} map={SEVERITY_BADGE} /></strong> {f.title}
                <div style={{ color: '#6b7280', marginTop: 2 }}>{f.description}</div>
                <div style={{ color: '#1d4ed8', marginTop: 2 }}>Recommendation: {f.recommendation}</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Assessment History">
        {loading ? <div>Loading…</div> : (
          <Table
            cols={[
              { key: 'model_id',       label: 'Model' },
              { key: 'overall_risk',   label: 'Risk',   render: v => <Badge value={v} map={SEVERITY_BADGE} /> },
              { key: 'format_risk',    label: 'Format' },
              { key: 'licence',        label: 'Licence' },
              { key: 'is_cleared_for_deployment', label: 'Cleared', render: v => v ? 'Yes' : 'No — Requires Review' },
              { key: 'assessed_at',    label: 'Date',   render: v => v?.slice(0, 10) },
            ]}
            rows={assessments || []}
            keyField="assessment_id"
          />
        )}
      </Card>
    </div>
  )
}

// ── Tab: MCP & Tools ──────────────────────────────────────────────────────
function MCPTab() {
  const { data: servers, loading: lS, reload: rS } = useApi('/api/v1/trust/mcp/servers')
  const { data: tools,   loading: lT, reload: rT } = useApi('/api/v1/trust/mcp/tools')
  const { data: execs,   loading: lE }              = useApi('/api/v1/trust/mcp/executions')

  return (
    <div>
      <Notice type="info" text="Only approved MCP servers and tools may execute. Unregistered tools are denied. High-impact tools require human approval before each execution." />

      <Card title="MCP Servers">
        {lS ? <div>Loading…</div> : (
          <Table
            cols={[
              { key: 'name',    label: 'Server Name' },
              { key: 'version', label: 'Version' },
              { key: 'status',  label: 'Status', render: v => <Badge value={v} map={STATUS_BADGE} /> },
              { key: 'approved_by', label: 'Approved By', render: v => v || '—' },
              { key: 'registered_at', label: 'Registered', render: v => v?.slice(0, 10) },
            ]}
            rows={servers || []}
            keyField="server_id"
          />
        )}
      </Card>

      <Card title="Registered Tools">
        {lT ? <div>Loading…</div> : (
          <Table
            cols={[
              { key: 'name',          label: 'Tool Name' },
              { key: 'status',        label: 'Status',    render: v => <Badge value={v} map={STATUS_BADGE} /> },
              { key: 'risk_level',    label: 'Risk',      render: v => <Badge value={v} map={SEVERITY_BADGE} /> },
              { key: 'is_high_impact', label: 'High Impact', render: v => v ? <Badge value="YES" map={{ YES: { color: '#dc2626', bg: '#fef2f2' } }} /> : 'No' },
              { key: 'required_scopes', label: 'Scopes',  render: v => Array.isArray(v) ? v.join(', ') : v },
              { key: 'approved_by',   label: 'Approved By', render: v => v || '—' },
            ]}
            rows={tools || []}
            keyField="tool_id"
          />
        )}
      </Card>

      <Card title="Tool Execution Records">
        {lE ? <div>Loading…</div> : (
          <Table
            cols={[
              { key: 'tool_name',    label: 'Tool' },
              { key: 'agent_id',     label: 'Agent' },
              { key: 'permitted',    label: 'Permitted', render: v => v ? 'Yes' : 'No' },
              { key: 'approval_required', label: 'Approval Req', render: v => v ? 'Yes' : '—' },
              { key: 'approved_by',  label: 'Approved By', render: v => v || '—' },
              { key: 'blocked_reason', label: 'Block Reason', render: v => v || '—' },
              { key: 'timestamp',    label: 'Time', render: v => v?.slice(0, 19).replace('T', ' ') },
            ]}
            rows={execs || []}
            keyField="execution_id"
          />
        )}
      </Card>
    </div>
  )
}

// ── Tab: Governance ───────────────────────────────────────────────────────
function GovernanceTab() {
  const { data: queue, loading, reload } = useApi('/api/v1/trust/governance/queue')
  const { data: policies } = useApi('/api/v1/trust/governance/policies')
  const [approveId, setApproveId]   = useState('')
  const [approverId, setApproverId] = useState('')
  const [approving, setApproving]   = useState(false)

  const doApprove = async (requestId) => {
    if (!approverId.trim()) { alert('Enter approver ID — must be a named human, not "system".'); return }
    setApproving(true)
    try {
      await apiFetch(`/api/v1/trust/governance/queue/${requestId}/approve`, {
        method: 'POST', body: JSON.stringify({ approver_id: approverId }),
      })
      reload()
    } catch (e) {
      alert(e.message)
    } finally {
      setApproving(false)
    }
  }

  return (
    <div>
      <Notice type="warn" text="Governance approvals require a named human approver. System actors are explicitly forbidden from approving any operation." />

      <Card title="Approval Queue">
        {loading ? <div>Loading…</div> : (
          <>
            <div style={{ marginBottom: 10, display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: '#6b7280' }}>Approver ID:</span>
              <input value={approverId} onChange={e => setApproverId(e.target.value)} placeholder="Named human approver (not 'system')"
                style={{ padding: '5px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13, width: 260 }} />
            </div>
            <Table
              cols={[
                { key: 'operation_type', label: 'Operation' },
                { key: 'resource_id',    label: 'Resource' },
                { key: 'actor_id',       label: 'Requested By' },
                { key: 'risk_level',     label: 'Risk',   render: v => <Badge value={v} map={SEVERITY_BADGE} /> },
                { key: 'status',         label: 'Status', render: v => <Badge value={v} map={STATUS_BADGE} /> },
                { key: 'expires_at',     label: 'Expires', render: v => v?.slice(0, 16).replace('T', ' ') },
                { key: 'request_id',     label: 'Action', render: (v, row) => row.status === 'PENDING' ? (
                  <button onClick={() => doApprove(v)} disabled={approving}
                    style={{ padding: '3px 10px', background: '#16a34a', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}>
                    Approve
                  </button>
                ) : '—' },
              ]}
              rows={queue || []}
              keyField="request_id"
            />
          </>
        )}
      </Card>

      <Card title="Governance Policies">
        {!policies ? <div>Loading…</div> : (
          <Table
            cols={[
              { key: 'name',           label: 'Policy' },
              { key: 'operation_types', label: 'Operations', render: v => Array.isArray(v) ? v.join(', ') : v },
              { key: 'decision',       label: 'Decision', render: v => <Badge value={v} map={DECISION_BADGE} /> },
              { key: 'required_approver_role', label: 'Approver Role', render: v => v || '—' },
              { key: 'version',        label: 'Version' },
            ]}
            rows={policies || []}
            keyField="policy_id"
          />
        )}
      </Card>
    </div>
  )
}

// ── Tab: Risk Register ────────────────────────────────────────────────────
function RisksTab() {
  const { data, loading, reload } = useApi('/api/v1/trust/risks')
  const { data: report } = useApi('/api/v1/trust/risks/report')

  return (
    <div>
      <Notice type="info" text="This risk register reflects technical controls and documented procedures. It does not constitute regulatory compliance certification or independent audit." />

      {report && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
          <Stat label="Total Risks"      value={report.total_risks || 0} />
          <Stat label="Open Risks"       value={report.open_risks || 0}  color="#dc2626" />
          <Stat label="Evidence Items"   value={report.evidence_count || 0} color="#16a34a" />
          {Object.entries(report.severity_breakdown || {}).map(([k, v]) => (
            <Stat key={k} label={k} value={v} color={SEVERITY_BADGE[k]?.color} />
          ))}
        </div>
      )}

      <Card title="Risk Register">
        {loading ? <div>Loading…</div> : (
          <Table
            cols={[
              { key: 'severity',  label: 'Severity',  render: v => <Badge value={v} map={SEVERITY_BADGE} /> },
              { key: 'category',  label: 'Category' },
              { key: 'title',     label: 'Title' },
              { key: 'asset_type', label: 'Asset Type' },
              { key: 'likelihood', label: 'Likelihood' },
              { key: 'status',    label: 'Status',    render: v => <Badge value={v} map={STATUS_BADGE} /> },
              { key: 'review_date', label: 'Review',  render: v => v?.slice(0, 10) },
            ]}
            rows={data || []}
            keyField="risk_id"
          />
        )}
      </Card>
    </div>
  )
}

// ── Tab: Audit Log ────────────────────────────────────────────────────────
function AuditTab() {
  const [filters, setFilters] = useState({ actor_id: '', resource_type: '', decision: '', limit: 100 })
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchAudit = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams()
    if (filters.actor_id)     params.set('actor_id', filters.actor_id)
    if (filters.resource_type) params.set('resource_type', filters.resource_type)
    if (filters.decision)     params.set('decision', filters.decision)
    params.set('limit', String(filters.limit))
    try {
      const r = await apiFetch(`/api/v1/trust/audit?${params}`)
      setData(r)
    } finally {
      setLoading(false)
    }
  }, [filters.actor_id, filters.resource_type, filters.decision, filters.limit])

  useEffect(() => { fetchAudit() }, [fetchAudit])

  return (
    <div>
      <Notice type="info" text="Audit records are append-only and protected from deletion. Sensitive content is redacted before logging." />
      <Card title="Audit Log" action={
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {['actor_id', 'resource_type', 'decision'].map(f => (
            <input key={f} placeholder={f} value={filters[f]}
              onChange={e => setFilters(fs => ({ ...fs, [f]: e.target.value }))}
              style={{ padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 12, width: 130 }} />
          ))}
          <button onClick={fetchAudit}
            style={{ padding: '4px 12px', background: '#1d4ed8', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}>
            Filter
          </button>
        </div>
      }>
        {loading ? <div>Loading…</div> : (
          <Table
            cols={[
              { key: 'timestamp',     label: 'Timestamp',  render: v => v?.slice(0, 19).replace('T', ' ') },
              { key: 'actor_id',      label: 'Actor' },
              { key: 'actor_type',    label: 'Actor Type' },
              { key: 'resource_type', label: 'Resource' },
              { key: 'resource_id',   label: 'Resource ID' },
              { key: 'action',        label: 'Action' },
              { key: 'decision',      label: 'Decision', render: v => <Badge value={v} map={DECISION_BADGE} /> },
              { key: 'outcome',       label: 'Outcome' },
              { key: 'policy_id',     label: 'Policy' },
            ]}
            rows={data || []}
            keyField="event_id"
          />
        )}
      </Card>
    </div>
  )
}

// ── Root component ────────────────────────────────────────────────────────
const TAB_COMPONENTS = {
  overview:    OverviewTab,
  policies:    PoliciesTab,
  identities:  IdentitiesTab,
  models:      ModelSecurityTab,
  mcp:         MCPTab,
  governance:  GovernanceTab,
  risks:       RisksTab,
  audit:       AuditTab,
}

export default function TrustCentrePage() {
  const [activeTab, setActiveTab] = useState('overview')
  const ActiveComponent = TAB_COMPONENTS[activeTab] || OverviewTab

  return (
    <div style={{ padding: 24, fontFamily: 'Inter, system-ui, sans-serif', maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: '#111827', margin: 0 }}>AI Trust Centre</h1>
        <p style={{ color: '#6b7280', fontSize: 13, marginTop: 4 }}>
          Security controls, governance, model supply chain, identity and audit for OrQuanta AI infrastructure.
        </p>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 2, borderBottom: '2px solid #e5e7eb', marginBottom: 20, flexWrap: 'wrap' }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '8px 16px', border: 'none', background: 'transparent',
              cursor: 'pointer', fontSize: 13, fontWeight: activeTab === tab.id ? 700 : 400,
              color: activeTab === tab.id ? '#1d4ed8' : '#6b7280',
              borderBottom: activeTab === tab.id ? '2px solid #1d4ed8' : '2px solid transparent',
              marginBottom: -2,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <ActiveComponent />
    </div>
  )
}
