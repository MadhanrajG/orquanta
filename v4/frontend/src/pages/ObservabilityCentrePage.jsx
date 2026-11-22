// Copyright 2026 OrQuanta — Apache License 2.0
import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  Activity, Shield, DollarSign, Cpu, Brain,
  AlertTriangle, CheckCircle, Eye, BarChart2,
  RefreshCw, Clock, Server, Zap, FileText,
  TrendingUp, TrendingDown, Info
} from 'lucide-react'
import { useAuth } from '../App.jsx'

const API = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || ''

// Data quality badge — always shown when data is estimated or heuristic
function DataQualityBadge({ isReal, isHeuristic, isEstimated, isDemo }) {
  if (isDemo) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
      <Info size={10} /> DEMO
    </span>
  )
  if (isReal) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300">
      <CheckCircle size={10} /> REAL
    </span>
  )
  if (isHeuristic) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
      <AlertTriangle size={10} /> HEURISTIC
    </span>
  )
  if (isEstimated) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
      <Info size={10} /> ESTIMATED
    </span>
  )
  return null
}

function DisclaimerBox({ text }) {
  if (!text) return null
  return (
    <div className="mt-3 p-3 rounded-lg bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
      <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
        <Info size={11} className="inline mr-1 opacity-70" />
        {text}
      </p>
    </div>
  )
}

function MetricCard({ title, value, unit = '', icon: Icon, color = 'blue', badge, trend }) {
  const colors = {
    blue: 'from-blue-500/10 to-blue-600/5 border-blue-200 dark:border-blue-800/50',
    green: 'from-green-500/10 to-green-600/5 border-green-200 dark:border-green-800/50',
    amber: 'from-amber-500/10 to-amber-600/5 border-amber-200 dark:border-amber-800/50',
    red: 'from-red-500/10 to-red-600/5 border-red-200 dark:border-red-800/50',
    purple: 'from-purple-500/10 to-purple-600/5 border-purple-200 dark:border-purple-800/50',
  }
  return (
    <div className={`p-4 rounded-xl border bg-gradient-to-br ${colors[color]} backdrop-blur-sm`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">{title}</span>
        <div className="flex items-center gap-2">
          {badge}
          {Icon && <Icon size={16} className="opacity-50" />}
        </div>
      </div>
      <div className="flex items-end gap-1">
        <span className="text-2xl font-bold text-slate-800 dark:text-slate-100 tabular-nums">
          {value ?? '—'}
        </span>
        {unit && <span className="text-sm text-slate-500 dark:text-slate-400 mb-0.5">{unit}</span>}
      </div>
    </div>
  )
}

function SeverityBadge({ severity }) {
  const cfg = {
    CRITICAL: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
    HIGH: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
    MEDIUM: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    LOW: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    INFO: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  }
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${cfg[severity] || cfg.INFO}`}>
      {severity}
    </span>
  )
}

// Tab definitions
const TABS = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'inference', label: 'Inference', icon: Brain },
  { id: 'agents', label: 'Agents', icon: Zap },
  { id: 'security', label: 'Security', icon: Shield },
  { id: 'gpu', label: 'GPU', icon: Cpu },
  { id: 'cost', label: 'Cost', icon: DollarSign },
  { id: 'governance', label: 'Governance', icon: FileText },
  { id: 'telemetry', label: 'Telemetry', icon: Eye },
]

function useObsApi(endpoint, interval = 15000) {
  const { token } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetch_ = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch(`${API}${endpoint}`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(10000),
      })
      if (r.ok) {
        setData(await r.json())
        setError(null)
      } else {
        setError(`HTTP ${r.status}`)
      }
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [endpoint, token])

  useEffect(() => {
    fetch_()
    const t = setInterval(fetch_, interval)
    return () => clearInterval(t)
  }, [fetch_, interval])

  return { data, loading, error, refresh: fetch_ }
}

// ── Tab: Overview ─────────────────────────────────────────────────────────────
function OverviewTab() {
  const { data, loading, error, refresh } = useObsApi('/api/v1/observability/ops-centre/overview')

  if (loading) return <div className="text-slate-500 p-8 text-center">Loading operations overview...</div>
  if (error) return <div className="p-8 text-red-500 text-center">Error: {error}</div>
  if (!data) return null

  const { inference, agents, security, gpu, cost, data_quality, telemetry: tel } = data

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">AI Operations Centre</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Real-time telemetry and intelligence across all AI systems
          </p>
        </div>
        <button onClick={refresh} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
          <RefreshCw size={16} className="text-slate-500" />
        </button>
      </div>

      {/* Data quality banner */}
      {data_quality && !data_quality.real_gpu_metrics && (
        <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50 flex items-start gap-2">
          <AlertTriangle size={14} className="text-amber-500 mt-0.5 shrink-0" />
          <p className="text-xs text-amber-700 dark:text-amber-300">
            {data_quality.limitation}
          </p>
        </div>
      )}

      {/* Metric grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          title="LLM Calls"
          value={inference?.total_llm_calls ?? 0}
          icon={Brain}
          color="blue"
          badge={<DataQualityBadge isEstimated />}
        />
        <MetricCard
          title="Agent Executions"
          value={agents?.total_executions ?? 0}
          icon={Zap}
          color="purple"
        />
        <MetricCard
          title="Open Security Events"
          value={security?.open_events ?? 0}
          icon={Shield}
          color={security?.open_events > 0 ? 'amber' : 'green'}
          badge={<DataQualityBadge isHeuristic />}
        />
        <MetricCard
          title="Avg GPU Util"
          value={gpu?.avg_gpu_utilization_pct ?? '—'}
          unit="%"
          icon={Cpu}
          color="blue"
          badge={<DataQualityBadge isEstimated={!data_quality?.real_gpu_metrics} isReal={data_quality?.real_gpu_metrics} />}
        />
      </div>

      {/* Telemetry status */}
      <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Telemetry Infrastructure</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${tel?.otel_enabled ? 'bg-green-500' : 'bg-slate-400'}`} />
            <span className="text-slate-600 dark:text-slate-400">OpenTelemetry</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${tel?.tracer_active ? 'bg-green-500' : 'bg-slate-400'}`} />
            <span className="text-slate-600 dark:text-slate-400">Tracer Active</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${data_quality?.langfuse_connected ? 'bg-green-500' : 'bg-slate-400'}`} />
            <span className="text-slate-600 dark:text-slate-400">Langfuse</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${data_quality?.otlp_connected ? 'bg-green-500' : 'bg-amber-400'}`} />
            <span className="text-slate-600 dark:text-slate-400">OTLP Endpoint</span>
          </div>
        </div>
        <p className="text-xs text-slate-400 mt-3 font-mono">{tel?.otlp_endpoint}</p>
      </div>

      <DisclaimerBox text={data_quality?.limitation} />
    </div>
  )
}

// ── Tab: Inference ────────────────────────────────────────────────────────────
function InferenceTab() {
  const { data, loading } = useObsApi('/api/v1/observability/llm/summary')
  const { data: records } = useObsApi('/api/v1/observability/llm/records?limit=20')

  if (loading) return <div className="text-slate-500 p-8 text-center">Loading inference data...</div>
  if (!data) return null

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">LLM Inference Observability</h2>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard title="Total Calls" value={data.total_calls ?? 0} icon={Brain} color="blue" badge={<DataQualityBadge isEstimated />} />
        <MetricCard title="Failed Calls" value={data.failed_calls ?? 0} icon={AlertTriangle} color={data.failed_calls > 0 ? 'red' : 'green'} />
        <MetricCard title="Avg Latency" value={data.avg_latency_ms} unit="ms" icon={Clock} color="purple" />
        <MetricCard title="Est. Cost" value={data.estimated_cost_usd?.toFixed(4)} unit="USD" icon={DollarSign} color="amber" badge={<DataQualityBadge isEstimated />} />
      </div>

      {data.by_model && Object.keys(data.by_model).length > 0 && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Usage by Model</h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <th className="text-left px-4 py-2 text-slate-500 font-medium">Model</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">Calls</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">Tokens</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">Est. Cost</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">Errors</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.by_model).map(([model, stats]) => (
                <tr key={model} className="border-b border-slate-50 dark:border-slate-800/50 hover:bg-slate-50 dark:hover:bg-slate-800/30">
                  <td className="px-4 py-2 font-mono text-xs text-slate-700 dark:text-slate-300">{model}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-600 dark:text-slate-400">{stats.calls}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-600 dark:text-slate-400">{stats.tokens?.toLocaleString()}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-600 dark:text-slate-400">${stats.cost_usd?.toFixed(4)}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-red-500">{stats.errors}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <DisclaimerBox text={data.disclaimer} />
    </div>
  )
}

// ── Tab: Agents ───────────────────────────────────────────────────────────────
function AgentsTab() {
  const { data: summary } = useObsApi('/api/v1/observability/agents/llm-summary')
  const { data: analytics } = useObsApi('/api/v1/observability/agents/analytics')

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Agent Intelligence</h2>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <MetricCard title="Total Executions" value={summary.total_executions ?? 0} icon={Zap} color="purple" />
          <MetricCard title="Completion Rate" value={summary.completion_rate_pct} unit="%" icon={CheckCircle} color="green" />
          <MetricCard title="Est. Total Cost" value={summary.total_estimated_cost_usd?.toFixed(4)} unit="USD" icon={DollarSign} color="amber" badge={<DataQualityBadge isEstimated />} />
        </div>
      )}

      {analytics?.by_agent && Object.keys(analytics.by_agent).length > 0 && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Agent Analytics</h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <th className="text-left px-4 py-2 text-slate-500 font-medium">Agent</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">Events</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">Failures</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">LLM Calls</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">Tool Calls</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(analytics.by_agent).map(([name, stats]) => (
                <tr key={name} className="border-b border-slate-50 dark:border-slate-800/50 hover:bg-slate-50 dark:hover:bg-slate-800/30">
                  <td className="px-4 py-2 font-medium text-slate-700 dark:text-slate-300">{name}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{stats.events}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-red-500">{stats.failures}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{stats.llm_calls}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{stats.tool_calls}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <DisclaimerBox text={analytics?.disclaimer} />
    </div>
  )
}

// ── Tab: Security ─────────────────────────────────────────────────────────────
function SecurityTab() {
  const { data: summary } = useObsApi('/api/v1/observability/security/summary')
  const { data: events } = useObsApi('/api/v1/observability/security/events?limit=50')

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Security Intelligence</h2>
        <DataQualityBadge isHeuristic />
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <MetricCard title="Total Events" value={summary.total_events ?? 0} icon={Shield} color="blue" />
          <MetricCard title="Open Events" value={summary.open_events ?? 0} icon={AlertTriangle} color={summary.open_events > 0 ? 'amber' : 'green'} />
          {summary.by_severity?.CRITICAL > 0 && (
            <MetricCard title="Critical" value={summary.by_severity.CRITICAL} icon={AlertTriangle} color="red" badge={<DataQualityBadge isHeuristic />} />
          )}
        </div>
      )}

      {summary && (
        <div className="p-4 rounded-xl border border-amber-200 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-900/20">
          <p className="text-xs text-amber-700 dark:text-amber-300 leading-relaxed">
            <AlertTriangle size={12} className="inline mr-1" />
            {summary.limitation}
          </p>
        </div>
      )}

      {events && events.length > 0 && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Recent Security Events</h3>
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {events.slice(0, 20).map(e => (
              <div key={e.event_id} className="px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/30">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <SeverityBadge severity={e.severity} />
                      <span className="text-xs text-slate-500 font-mono">{e.category}</span>
                      {e.is_heuristic && <span className="text-xs text-amber-500">heuristic</span>}
                    </div>
                    <p className="text-sm text-slate-700 dark:text-slate-300">{e.title}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{e.description?.slice(0, 120)}</p>
                  </div>
                  <span className="text-xs text-slate-400 whitespace-nowrap font-mono">
                    {e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : ''}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Tab: GPU ──────────────────────────────────────────────────────────────────
function GPUTab() {
  const { data: summary } = useObsApi('/api/v1/observability/gpu/summary')
  const { data: snapshots } = useObsApi('/api/v1/observability/gpu/snapshots?limit=20')

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">GPU and Model Performance</h2>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard title="Snapshots" value={summary.total_snapshots ?? 0} icon={Server} color="blue" />
          <MetricCard title="Real Measurements" value={summary.real_measurements ?? 0} icon={CheckCircle}
            color={summary.real_measurements > 0 ? 'green' : 'amber'}
            badge={<DataQualityBadge isReal={summary.real_measurements > 0} isEstimated={summary.real_measurements === 0} />}
          />
          <MetricCard title="Avg GPU Util" value={summary.avg_gpu_utilization_pct ?? '—'} unit="%" icon={Cpu} color="purple" />
          <MetricCard title="Avg Latency" value={summary.avg_inference_latency_ms ?? '—'} unit="ms" icon={Clock} color="blue" />
        </div>
      )}

      {summary?.real_measurements === 0 && (
        <div className="p-4 rounded-xl border border-blue-200 dark:border-blue-800/50 bg-blue-50 dark:bg-blue-900/20">
          <p className="text-xs text-blue-700 dark:text-blue-300">
            <Info size={12} className="inline mr-1" />
            No real GPU sensor readings available. Configure a running vLLM or SGLang instance
            with VLLM_INSTANCE_URL to enable real measurements. All current figures are estimates.
          </p>
        </div>
      )}

      {snapshots && snapshots.length > 0 && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Recent Snapshots</h3>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <th className="text-left px-4 py-2 text-slate-500 font-medium">Model</th>
                <th className="text-left px-4 py-2 text-slate-500 font-medium">Provider</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">GPU Util</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">VRAM</th>
                <th className="text-right px-4 py-2 text-slate-500 font-medium">Latency</th>
                <th className="text-center px-4 py-2 text-slate-500 font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.slice(0, 15).map(s => (
                <tr key={s.snapshot_id} className="border-b border-slate-50 dark:border-slate-800/50">
                  <td className="px-4 py-2 font-mono">{s.model_id || '—'}</td>
                  <td className="px-4 py-2">{s.provider || '—'}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{s.gpu_utilization_pct != null ? `${s.gpu_utilization_pct}%` : '—'}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{s.vram_utilization_pct != null ? `${s.vram_utilization_pct}%` : '—'}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{s.inference_latency_ms != null ? `${s.inference_latency_ms}ms` : '—'}</td>
                  <td className="px-4 py-2 text-center">
                    <DataQualityBadge isReal={s.is_real_measurement} isEstimated={s.is_estimated} isDemo={s.is_demo_data} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <DisclaimerBox text={summary?.disclaimer} />
    </div>
  )
}

// ── Tab: Cost ─────────────────────────────────────────────────────────────────
function CostTab() {
  const [tenantId, setTenantId] = useState('')
  const [submitted, setSubmitted] = useState('')
  const { data: breakdown } = useObsApi(submitted ? `/api/v1/observability/cost/by-tenant?tenant_id=${submitted}` : null)
  const { data: forecast } = useObsApi(submitted ? `/api/v1/observability/cost/forecast?tenant_id=${submitted}` : null)
  const { data: recs } = useObsApi(submitted ? `/api/v1/observability/cost/recommendations?tenant_id=${submitted}` : null)
  const { data: alerts } = useObsApi('/api/v1/observability/cost/alerts?limit=10')

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Cost Intelligence</h2>
        <DataQualityBadge isEstimated />
      </div>

      <div className="p-4 rounded-xl border border-blue-200 dark:border-blue-800/50 bg-blue-50 dark:bg-blue-900/20">
        <p className="text-xs text-blue-700 dark:text-blue-300">
          <Info size={12} className="inline mr-1" />
          All cost figures are internal estimates for resource planning. They do NOT represent
          actual provider billing. Refer to your provider invoices for authoritative billing data.
        </p>
      </div>

      <div className="flex gap-2">
        <input
          className="flex-1 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm"
          placeholder="Enter tenant ID..."
          value={tenantId}
          onChange={e => setTenantId(e.target.value)}
        />
        <button
          onClick={() => setSubmitted(tenantId)}
          className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          Analyse
        </button>
      </div>

      {breakdown && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <MetricCard title="Total (30d)" value={`$${breakdown.total_estimated_usd?.toFixed(2)}`} icon={DollarSign} color="blue" badge={<DataQualityBadge isEstimated />} />
          {Object.entries(breakdown.by_cost_type || {}).slice(0, 2).map(([type, cost]) => (
            <MetricCard key={type} title={type.replace('_', ' ')} value={`$${cost.toFixed(4)}`} icon={BarChart2} color="purple" />
          ))}
        </div>
      )}

      {forecast?.forecast_available && (
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">7-Day Budget Forecast</h3>
          <p className="text-xs text-slate-500 mb-3">Method: {forecast.forecast_method}</p>
          <div className="grid grid-cols-7 gap-1">
            {Object.entries(forecast.forecast_by_day || {}).map(([day, cost]) => (
              <div key={day} className="text-center">
                <div className="text-xs font-mono text-slate-500">{day.slice(5)}</div>
                <div className="text-xs font-semibold text-blue-600 dark:text-blue-400">${cost}</div>
              </div>
            ))}
          </div>
          <DisclaimerBox text={forecast.disclaimer} />
        </div>
      )}

      {recs && recs.length > 0 && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Optimization Recommendations</h3>
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {recs.map((rec, i) => (
              <div key={i} className="px-4 py-3">
                <div className="flex items-start gap-2">
                  <TrendingDown size={14} className="text-green-500 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm text-slate-700 dark:text-slate-300">{rec.recommendation}</p>
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                      <AlertTriangle size={10} className="inline mr-1" />
                      {rec.disclaimer}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {alerts && alerts.length > 0 && (
        <div className="rounded-xl border border-orange-200 dark:border-orange-800/50 bg-orange-50 dark:bg-orange-900/20 p-4">
          <h3 className="text-sm font-semibold text-orange-700 dark:text-orange-300 mb-2">Budget Alerts</h3>
          {alerts.map((a, i) => (
            <div key={i} className="text-xs text-orange-600 dark:text-orange-400 mb-1">
              {a.alert_type}: Tenant {a.tenant_id} — ${a.today_spend_usd} (est.)
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Tab: Governance ───────────────────────────────────────────────────────────
function GovernanceTab() {
  const { data: reports } = useObsApi('/api/v1/observability/governance/reports')

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Governance Reporting</h2>

      <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50">
        <p className="text-xs text-slate-500 leading-relaxed">
          Governance reports link to Phase 4 policy decisions, approval histories and the AI risk register.
          Reports do NOT constitute regulatory compliance certification or independent audit evidence.
          Formal compliance requires accredited third-party assessment.
        </p>
      </div>

      {reports && reports.length > 0 ? (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700">
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Generated Reports</h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <th className="text-left px-4 py-2 text-slate-500 font-medium">Type</th>
                <th className="text-left px-4 py-2 text-slate-500 font-medium">Tenant</th>
                <th className="text-left px-4 py-2 text-slate-500 font-medium">Generated</th>
              </tr>
            </thead>
            <tbody>
              {reports.map(r => (
                <tr key={r.report_id} className="border-b border-slate-50 dark:border-slate-800/50">
                  <td className="px-4 py-2 font-mono text-xs">{r.report_type}</td>
                  <td className="px-4 py-2 text-slate-600 dark:text-slate-400">{r.tenant_id}</td>
                  <td className="px-4 py-2 text-slate-500 font-mono text-xs">
                    {r.generated_at ? new Date(r.generated_at).toLocaleString() : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="p-8 text-center text-slate-400">
          No reports generated yet. Use the API endpoints to generate model usage, security, and policy enforcement reports.
        </div>
      )}
    </div>
  )
}

// ── Tab: Telemetry ─────────────────────────────────────────────────────────────
function TelemetryTab() {
  const { data: status } = useObsApi('/api/v1/observability/telemetry/status', 30000)

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">OpenTelemetry Configuration</h2>

      {status && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.entries(status).filter(([k]) => k !== 'limitation').map(([key, val]) => (
            <div key={key} className="p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50">
              <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">{key.replace(/_/g, ' ')}</div>
              <div className="text-sm font-mono text-slate-700 dark:text-slate-300">
                {typeof val === 'boolean'
                  ? <span className={val ? 'text-green-600' : 'text-slate-400'}>{val ? 'enabled' : 'disabled'}</span>
                  : String(val) || '—'}
              </div>
            </div>
          ))}
        </div>
      )}

      <DisclaimerBox text={status?.limitation} />
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function ObservabilityCentrePage() {
  const [activeTab, setActiveTab] = useState('overview')

  const tabContent = {
    overview: <OverviewTab />,
    inference: <InferenceTab />,
    agents: <AgentsTab />,
    security: <SecurityTab />,
    gpu: <GPUTab />,
    cost: <CostTab />,
    governance: <GovernanceTab />,
    telemetry: <TelemetryTab />,
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-4 md:p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            AI Operations Centre
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Unified observability, security intelligence and cost tracking for all AI systems
          </p>
        </div>

        {/* Tab nav */}
        <div className="flex gap-1 mb-6 overflow-x-auto pb-1">
          {TABS.map(tab => {
            const Icon = tab.icon
            const active = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                  active
                    ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 shadow-sm'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
                }`}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            )
          })}
        </div>

        {/* Tab content */}
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {tabContent[activeTab]}
        </motion.div>
      </div>
    </div>
  )
}
