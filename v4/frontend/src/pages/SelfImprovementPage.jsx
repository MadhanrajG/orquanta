import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../App.jsx'
import {
  Brain, TrendingUp, TrendingDown, Minus, Zap, RefreshCw,
  ChevronDown, ChevronUp, History, FlaskConical, Cpu, ArrowUpRight,
  RotateCcw, AlertTriangle, CheckCircle, Loader2, Activity
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Legend
} from 'recharts'

const API = import.meta.env.VITE_API_URL || ''

/* ── Hooks ────────────────────────────────────────────────────── */
function useImprovementStatus(interval = 8000) {
  const { token } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchData = async () => {
    try {
      const res = await fetch(`${API}/api/v1/vero/self-improvement/status`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(10000),
      })
      if (res.ok) {
        setData(await res.json())
        setError(null)
      }
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const t = setInterval(fetchData, interval)
    return () => clearInterval(t)
  }, [token])

  return { data, loading, error, refetch: fetchData }
}

function useHistory() {
  const { token } = useAuth()
  const [data, setData] = useState(null)
  useEffect(() => {
    fetch(`${API}/api/v1/vero/self-improvement/history`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then(r => r.ok ? r.json() : null).then(d => d && setData(d)).catch(() => {})
  }, [token])
  return data
}

/* ── Helpers ──────────────────────────────────────────────────── */
function HealthBadge({ status }) {
  const cfg = {
    excellent: { color: '#10B981', bg: 'rgba(16,185,129,0.1)', border: 'rgba(16,185,129,0.25)', icon: CheckCircle, label: 'Excellent' },
    good:      { color: '#7C6BF0', bg: 'rgba(124,107,240,0.1)', border: 'rgba(124,107,240,0.25)', icon: TrendingUp, label: 'Good' },
    learning:  { color: '#F59E0B', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.25)', icon: Brain, label: 'Learning' },
    stagnant:  { color: '#94A3B8', bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.25)', icon: Minus, label: 'Stagnant' },
    regressing:{ color: '#EF4444', bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.25)', icon: TrendingDown, label: 'Regressing' },
    initializing: { color: '#F59E0B', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.25)', icon: Loader2, label: 'Initializing' },
  }
  const c = cfg[status] || cfg.learning
  const Icon = c.icon
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 12px', borderRadius: 999,
      background: c.bg, border: `1px solid ${c.border}`,
      color: c.color, fontSize: 12, fontWeight: 700,
    }}>
      <Icon size={12} />
      {c.label}
    </span>
  )
}

function WeightBar({ label, value, color }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 12, color: '#475569', fontWeight: 600, textTransform: 'capitalize' }}>{label}</span>
        <span style={{ fontSize: 12, color, fontWeight: 800, fontFamily: "'JetBrains Mono', monospace" }}>
          {(value * 100).toFixed(1)}%
        </span>
      </div>
      <div style={{ height: 6, background: '#E2E8F0', borderRadius: 999, overflow: 'hidden' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value * 100}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          style={{ height: '100%', background: color, borderRadius: 999, boxShadow: `0 0 8px ${color}50` }}
        />
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, sub, color = '#7C6BF0', trend = null }) {
  return (
    <div style={{
      background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 14,
      padding: '18px 20px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      borderLeft: `3px solid ${color}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{
          width: 34, height: 34, borderRadius: 9,
          background: `${color}15`, border: `1px solid ${color}25`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon size={16} color={color} />
        </div>
        {trend !== null && (
          <span style={{ fontSize: 11, fontWeight: 700, color: trend >= 0 ? '#10B981' : '#EF4444', display: 'flex', alignItems: 'center', gap: 2 }}>
            {trend >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
            {Math.abs(trend)}
          </span>
        )}
      </div>
      <div style={{ fontSize: 24, fontWeight: 800, color: '#0F172A', fontFamily: "'JetBrains Mono', monospace", marginBottom: 2 }}>
        {value ?? '—'}
      </div>
      <div style={{ fontSize: 11, fontWeight: 600, color: '#64748B' }}>{label}</div>
      {sub && <div style={{ fontSize: 10, color: '#94A3B8', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

/* ── Policy Evolution Chart ───────────────────────────────────── */
function PolicyEvolutionChart({ history }) {
  if (!history || history.length < 2) {
    return (
      <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94A3B8', fontSize: 13 }}>
        <Brain size={20} style={{ marginRight: 8 }} />
        Waiting for first policy mutation...
      </div>
    )
  }

  const chartData = [...history].reverse().map((s, i) => ({
    v: `v${s.version}`,
    cost: Math.round(s.weights.cost * 100),
    perf: Math.round(s.weights.perf * 100),
    risk: Math.round(s.weights.risk * 100),
    score: Math.round(s.performance_score * 100),
  }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={chartData} margin={{ left: -20, right: 8, top: 4 }}>
        <defs>
          {[['cost','#7C6BF0'], ['perf','#10B981'], ['risk','#F59E0B']].map(([k, c]) => (
            <linearGradient key={k} id={`g-si-${k}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={c} stopOpacity={0.2} />
              <stop offset="95%" stopColor={c} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <XAxis dataKey="v" tick={{ fill: '#94A3B8', fontSize: 10 }} tickLine={false} />
        <YAxis domain={[0, 100]} tick={{ fill: '#94A3B8', fontSize: 10 }} tickLine={false} tickFormatter={v => `${v}%`} />
        <Tooltip
          contentStyle={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 10, fontSize: 12 }}
          formatter={(v, name) => [`${v}%`, name.charAt(0).toUpperCase() + name.slice(1)]}
        />
        {[['cost','#7C6BF0','Cost Priority'], ['perf','#10B981','Perf Priority'], ['risk','#F59E0B','Risk Weight']].map(([k, c, l]) => (
          <Area key={k} type="monotone" dataKey={k} stroke={c} strokeWidth={2}
            fill={`url(#g-si-${k})`} dot={false} name={l} />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}

/* ── Template Performance Table ──────────────────────────────── */
function TemplateStats({ stats }) {
  if (!stats || stats.length === 0) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: '#94A3B8', fontSize: 13 }}>
        <FlaskConical size={20} style={{ marginBottom: 8, display: 'block', margin: '0 auto 8px' }} />
        No LLM calls recorded yet. Template stats appear after first goal.
      </div>
    )
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #E2E8F0' }}>
            {['Template', 'Calls', 'Success Rate', 'Completion', 'Latency', 'Evolutions', 'Variant'].map(h => (
              <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: '#64748B', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {stats.map((s, i) => {
            const rateColor = s.success_rate >= 0.9 ? '#10B981' : s.success_rate >= 0.7 ? '#F59E0B' : '#EF4444'
            return (
              <tr key={s.template} style={{ borderBottom: '1px solid #F1F5F9', background: i % 2 === 0 ? 'transparent' : 'rgba(248,250,252,0.5)' }}>
                <td style={{ padding: '10px 12px', fontWeight: 600, color: '#0F172A', fontFamily: 'monospace', fontSize: 11 }}>
                  {s.template}
                </td>
                <td style={{ padding: '10px 12px', color: '#475569', fontFamily: "'JetBrains Mono', monospace" }}>
                  {s.total_calls}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ flex: 1, height: 4, background: '#E2E8F0', borderRadius: 999, overflow: 'hidden', minWidth: 60 }}>
                      <div style={{ width: `${s.success_rate * 100}%`, height: '100%', background: rateColor, borderRadius: 999 }} />
                    </div>
                    <span style={{ color: rateColor, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
                      {(s.success_rate * 100).toFixed(0)}%
                    </span>
                  </div>
                </td>
                <td style={{ padding: '10px 12px', color: '#475569', fontFamily: "'JetBrains Mono', monospace" }}>
                  {(s.completion_rate * 100).toFixed(0)}%
                </td>
                <td style={{ padding: '10px 12px', color: '#475569', fontFamily: "'JetBrains Mono', monospace" }}>
                  {s.avg_latency_ms.toFixed(0)}ms
                </td>
                <td style={{ padding: '10px 12px' }}>
                  {s.evolution_count > 0 ? (
                    <span style={{ background: 'rgba(124,107,240,0.1)', color: '#7C6BF0', padding: '2px 8px', borderRadius: 999, fontSize: 10, fontWeight: 700 }}>
                      {s.evolution_count}×
                    </span>
                  ) : (
                    <span style={{ color: '#CBD5E1', fontSize: 10 }}>none</span>
                  )}
                </td>
                <td style={{ padding: '10px 12px', fontSize: 10, color: '#7C6BF0', fontFamily: 'monospace' }}>
                  {s.active_variant}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* ── Reflection Feed ─────────────────────────────────────────── */
function ReflectionFeed({ reflections }) {
  if (!reflections || reflections.length === 0) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: '#94A3B8', fontSize: 13 }}>
        <Brain size={20} style={{ display: 'block', margin: '0 auto 8px' }} />
        Reflection log is empty. Submit a goal to generate the first reflection.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {reflections.map((r, i) => {
        const outcomeColor = r.outcome === 'completed' ? '#10B981' : '#EF4444'
        const age = new Date() - new Date(r.timestamp)
        const ageStr = age < 60000 ? `${Math.round(age/1000)}s ago` : age < 3600000 ? `${Math.round(age/60000)}m ago` : `${Math.round(age/3600000)}h ago`
        return (
          <motion.div
            key={r.reflection_id}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            style={{
              padding: '14px 16px', borderRadius: 12,
              background: i === 0 ? 'rgba(124,107,240,0.04)' : 'rgba(248,250,252,0.8)',
              border: `1px solid ${i === 0 ? 'rgba(124,107,240,0.15)' : '#E2E8F0'}`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 10, fontFamily: 'monospace', color: '#7C6BF0', fontWeight: 700 }}>
                #{r.reflection_id}
              </span>
              <span style={{ fontSize: 10, padding: '1px 8px', borderRadius: 999, background: `${outcomeColor}15`, color: outcomeColor, fontWeight: 700 }}>
                {r.outcome}
              </span>
              <span style={{ fontSize: 10, color: '#94A3B8', marginLeft: 'auto' }}>{ageStr}</span>
            </div>
            <div style={{ fontSize: 11, color: '#0F172A', fontWeight: 600, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {r.goal_text}
            </div>
            {r.reflection_summary && (
              <div style={{ fontSize: 11, color: '#64748B', lineHeight: 1.5, marginBottom: 4 }}>
                {r.reflection_summary}
              </div>
            )}
            <div style={{ display: 'flex', gap: 12, fontSize: 10, color: '#94A3B8' }}>
              <span>Cost: ${r.cost_usd?.toFixed(4)}</span>
              {r.mutations_applied > 0 && (
                <span style={{ color: '#7C6BF0', fontWeight: 700 }}>
                  {r.mutations_applied} mutation{r.mutations_applied > 1 ? 's' : ''} applied
                </span>
              )}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}

/* ── Radar Chart for Policy Weights ──────────────────────────── */
function PolicyRadar({ weights }) {
  const data = [
    { subject: 'Cost Priority', value: Math.round((weights?.cost ?? 0.6) * 100), fullMark: 100 },
    { subject: 'Performance', value: Math.round((weights?.perf ?? 0.25) * 100), fullMark: 100 },
    { subject: 'Risk Mgmt', value: Math.round((weights?.risk ?? 0.15) * 100), fullMark: 100 },
  ]
  return (
    <ResponsiveContainer width="100%" height={200}>
      <RadarChart data={data}>
        <PolarGrid stroke="#E2E8F0" />
        <PolarAngleAxis dataKey="subject" tick={{ fill: '#64748B', fontSize: 11 }} />
        <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 9, fill: '#94A3B8' }} />
        <Radar name="Current Policy" dataKey="value" stroke="#7C6BF0" fill="#7C6BF0" fillOpacity={0.2} strokeWidth={2} />
        <Tooltip formatter={v => [`${v}%`]} contentStyle={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 8, fontSize: 11 }} />
      </RadarChart>
    </ResponsiveContainer>
  )
}

/* ── Main Page ───────────────────────────────────────────────── */
export default function SelfImprovementPage() {
  const { token } = useAuth()
  const { data, loading, error, refetch } = useImprovementStatus()
  const history = useHistory()
  const [triggering, setTriggering] = useState(false)
  const [triggerResult, setTriggerResult] = useState(null)
  const [expandedSection, setExpandedSection] = useState(null)

  const triggerImprovement = async () => {
    setTriggering(true)
    setTriggerResult(null)
    try {
      const res = await fetch(`${API}/api/v1/vero/self-improvement/trigger`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      const json = await res.json()
      if (res.ok) {
        setTriggerResult({ success: true, msg: `Policy v${json.policy_version_after} active. Weights updated.` })
        refetch()
      } else {
        setTriggerResult({ success: false, msg: json.detail || 'Trigger failed (admin role required)' })
      }
    } catch {
      setTriggerResult({ success: false, msg: 'Connection error' })
    } finally {
      setTriggering(false)
    }
  }

  const policy = data?.policy
  const health = data?.health
  const reflections = data?.reflections
  const prompts = data?.prompt_evolution

  const toggleSection = (s) => setExpandedSection(prev => prev === s ? null : s)

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
      style={{ maxWidth: 1200 }}
    >
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 10,
            background: 'linear-gradient(135deg, rgba(124,107,240,0.15), rgba(155,139,244,0.1))',
            border: '1px solid rgba(124,107,240,0.2)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Brain size={20} color="#7C6BF0" />
          </div>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', margin: 0 }}>
              Recursive AI Self-Improvement
            </h1>
            <p style={{ fontSize: 12, color: '#64748B', margin: 0 }}>
              Policy mutation · Prompt evolution · Agent reflection — all running live
            </p>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 10, alignItems: 'center' }}>
            {health && <HealthBadge status={health.status} />}
            <button
              onClick={triggerImprovement}
              disabled={triggering}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer',
                background: 'linear-gradient(135deg, #7C6BF0, #9B8BF4)',
                color: '#fff', fontSize: 12, fontWeight: 600,
                boxShadow: '0 2px 12px rgba(124,107,240,0.3)',
                opacity: triggering ? 0.7 : 1,
              }}
            >
              {triggering ? <Loader2 size={13} style={{ animation: 'spin 0.8s linear infinite' }} /> : <Zap size={13} />}
              Trigger Reflection
            </button>
          </div>
        </div>

        {triggerResult && (
          <div style={{
            padding: '10px 16px', borderRadius: 8, marginTop: 10,
            background: triggerResult.success ? 'rgba(16,185,129,0.06)' : 'rgba(239,68,68,0.06)',
            border: `1px solid ${triggerResult.success ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
            color: triggerResult.success ? '#059669' : '#DC2626',
            fontSize: 13, display: 'flex', alignItems: 'center', gap: 8,
          }}>
            {triggerResult.success ? <CheckCircle size={14} /> : <AlertTriangle size={14} />}
            {triggerResult.msg}
          </div>
        )}
      </div>

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14, marginBottom: 24 }}>
        <StatCard icon={History} label="Policy Version" value={`v${policy?.version ?? 1}`}
          sub={`${policy?.total_mutations ?? 0} mutations total`} color="#7C6BF0" />
        <StatCard icon={Activity} label="Learning Velocity"
          value={`${health?.learning_velocity_per_hr?.toFixed(1) ?? 0}/hr`}
          sub="Policy mutations per hour" color="#10B981" />
        <StatCard icon={Brain} label="Reflections"
          value={reflections?.total_reflections ?? 0}
          sub={`+${reflections?.avg_improvement_per_reflection?.toFixed(2) ?? 0} avg improvement`}
          color="#F59E0B" />
        <StatCard icon={FlaskConical} label="Template Evolutions"
          value={prompts?.total_evolutions ?? 0}
          sub={`${prompts?.templates_evolved?.length ?? 0} templates improved`}
          color="#F472B6" />
      </div>

      {/* Main grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 20, marginBottom: 20 }}>

        {/* Policy Weights */}
        <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 14, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Cpu size={16} color="#7C6BF0" />
            <span style={{ fontWeight: 700, fontSize: 14, color: '#0F172A' }}>Current Policy Weights</span>
            {policy && (
              <span style={{ marginLeft: 'auto', fontSize: 10, color: '#94A3B8', fontFamily: 'monospace' }}>
                v{policy.version}
              </span>
            )}
          </div>
          <PolicyRadar weights={policy?.weights} />
          <div style={{ marginTop: 16 }}>
            <WeightBar label="Cost Priority" value={policy?.weights?.cost ?? 0.6} color="#7C6BF0" />
            <WeightBar label="Performance" value={policy?.weights?.perf ?? 0.25} color="#10B981" />
            <WeightBar label="Risk Management" value={policy?.weights?.risk ?? 0.15} color="#F59E0B" />
          </div>
          {policy?.last_mutation_cause && policy.last_mutation_cause !== 'none' && (
            <div style={{ marginTop: 12, padding: '8px 12px', borderRadius: 8, background: 'rgba(124,107,240,0.05)', border: '1px solid rgba(124,107,240,0.1)' }}>
              <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 2 }}>Last mutation cause</div>
              <div style={{ fontSize: 11, color: '#7C6BF0', fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {policy.last_mutation_cause}
              </div>
            </div>
          )}
        </div>

        {/* Policy Evolution Chart */}
        <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 14, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <TrendingUp size={16} color="#10B981" />
            <span style={{ fontWeight: 700, fontSize: 14, color: '#0F172A' }}>Policy Evolution Timeline</span>
          </div>
          <PolicyEvolutionChart history={history?.history ?? policy?.history} />
          <div style={{ display: 'flex', gap: 16, marginTop: 8, justifyContent: 'center' }}>
            {[['Cost Priority', '#7C6BF0'], ['Performance', '#10B981'], ['Risk Weight', '#F59E0B']].map(([l, c]) => (
              <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#64748B' }}>
                <div style={{ width: 12, height: 2, background: c, borderRadius: 999 }} />
                {l}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Expandable sections */}
      {[
        {
          key: 'templates',
          icon: FlaskConical,
          color: '#F472B6',
          title: 'Prompt Template Performance',
          sub: `${prompts?.template_stats?.length ?? 0} templates tracked`,
          content: <TemplateStats stats={prompts?.template_stats} />,
        },
        {
          key: 'reflections',
          icon: Brain,
          color: '#7C6BF0',
          title: 'Agent Reflection Log',
          sub: `${reflections?.total_reflections ?? 0} total reflections`,
          content: <ReflectionFeed reflections={reflections?.recent} />,
        },
      ].map(({ key, icon: Icon, color, title, sub, content }) => (
        <div key={key}
          style={{
            background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 14,
            marginBottom: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.05)', overflow: 'hidden',
          }}
        >
          <button
            onClick={() => toggleSection(key)}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: 10,
              padding: '16px 20px', background: 'none', border: 'none', cursor: 'pointer',
              textAlign: 'left', borderBottom: expandedSection === key ? '1px solid #E2E8F0' : 'none',
            }}
          >
            <div style={{ width: 32, height: 32, borderRadius: 8, background: `${color}12`, border: `1px solid ${color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Icon size={15} color={color} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: '#0F172A' }}>{title}</div>
              <div style={{ fontSize: 11, color: '#94A3B8' }}>{sub}</div>
            </div>
            {expandedSection === key ? <ChevronUp size={16} color="#94A3B8" /> : <ChevronDown size={16} color="#94A3B8" />}
          </button>
          <AnimatePresence>
            {expandedSection === key && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25 }}
                style={{ overflow: 'hidden', padding: '0 20px 20px' }}
              >
                <div style={{ paddingTop: 16 }}>{content}</div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      ))}

      {/* Loading state */}
      {loading && !data && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#94A3B8' }}>
          <Loader2 size={28} style={{ animation: 'spin 0.8s linear infinite', marginBottom: 12, display: 'block', margin: '0 auto 12px' }} />
          <div style={{ fontSize: 14 }}>Loading self-improvement status...</div>
        </div>
      )}

      {/* Info panel */}
      <div style={{
        marginTop: 20, padding: '16px 20px', borderRadius: 12,
        background: 'rgba(124,107,240,0.04)', border: '1px solid rgba(124,107,240,0.1)',
      }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#7C6BF0', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Brain size={13} /> How Recursive Self-Improvement Works
        </div>
        <div style={{ fontSize: 11, color: '#64748B', lineHeight: 1.7 }}>
          After each goal completes, the LLM reflects on the outcome and adjusts 3 routing weights (cost/perf/risk) via gradient descent.
          LLM prompt templates that underperform (&lt;70% parse success) get automatically rewritten and A/B tested over 20 calls.
          Policy weights decay toward baseline every 30 minutes to prevent overfitting.
          All mutations are persisted to SQLite and visible in the evolution timeline above.
        </div>
      </div>
    </motion.div>
  )
}
