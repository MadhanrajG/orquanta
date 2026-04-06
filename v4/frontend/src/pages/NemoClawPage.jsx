import { useState, useEffect, useCallback } from 'react'
import { Brain, Database, Shield, Zap, TrendingDown, AlertTriangle, CheckCircle, RefreshCw,
         ChevronRight, Activity, Server, DollarSign, Eye, Terminal } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || ''

const getAuthHeader = () => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${localStorage.getItem('orquanta_token') || ''}`,
})

const STATUS_COLOR = { active: '#00FF88', stopped: '#ff6b6b', unknown: '#94a3b8' }
const ACTION_COLOR = { halt: '#ff4444', throttle: '#FFB800', warn: '#00D4FF', prewarm: '#7B2FFF' }

function StatCard({ icon: Icon, label, value, sub, color = '#00D4FF', glow = false }) {
    return (
        <div className="glass-card p-5 flex items-start gap-4" style={{
            borderColor: glow ? color + '40' : undefined,
            boxShadow: glow ? `0 0 20px ${color}15` : undefined,
        }}>
            <div className="mt-0.5 p-2 rounded-lg" style={{ background: color + '15' }}>
                <Icon size={18} style={{ color }} />
            </div>
            <div>
                <p className="text-slate-400 text-xs font-medium uppercase tracking-wide mb-0.5">{label}</p>
                <p className="text-white text-xl font-bold font-mono">{value}</p>
                {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
            </div>
        </div>
    )
}

function TraceStep({ step, idx }) {
    const phaseColors = {
        CONTEXT: '#7B2FFF', ACT: '#00D4FF', SELF_EVAL: '#00FF88',
        ERROR: '#ff4444', OBSERVE: '#FFB800',
    }
    const color = phaseColors[step.phase] || '#94a3b8'
    return (
        <div className="flex gap-3 items-start py-2 border-b border-white/[0.04]">
            <span className="font-mono text-xs px-2 py-0.5 rounded" style={{ background: color + '20', color }}>{step.phase}</span>
            <div className="flex-1 min-w-0">
                <p className="text-xs text-slate-300 truncate">{step.action}</p>
                <p className="text-xs text-slate-500 mt-0.5 truncate">{step.result}</p>
            </div>
            <p className="text-xs text-slate-600 whitespace-nowrap">{new Date(step.ts).toLocaleTimeString()}</p>
        </div>
    )
}

export default function NemoClawPage() {
    const [status, setStatus] = useState(null)
    const [traces, setTraces] = useState([])
    const [selectedTrace, setSelectedTrace] = useState(null)
    const [brakes, setBrakes] = useState([])
    const [contextStats, setContextStats] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [goalText, setGoalText] = useState('')
    const [budgetUsd, setBudgetUsd] = useState(100)
    const [running, setRunning] = useState(false)
    const [runResult, setRunResult] = useState(null)
    const [tab, setTab] = useState('overview')

    const fetchAll = useCallback(async () => {
        try {
            const [s, t, b, c] = await Promise.all([
                fetch(`${API}/api/v1/nemoclaw/status`, { headers: getAuthHeader() }),
                fetch(`${API}/api/v1/nemoclaw/traces?limit=10`, { headers: getAuthHeader() }),
                fetch(`${API}/api/v1/nemoclaw/cost/brakes`, { headers: getAuthHeader() }),
                fetch(`${API}/api/v1/nemoclaw/context/stats`, { headers: getAuthHeader() }),
            ])
            if (s.ok) setStatus(await s.json())
            if (t.ok) { const td = await t.json(); setTraces(td.traces || []) }
            if (b.ok) { const bd = await b.json(); setBrakes(bd.brakes || []) }
            if (c.ok) setContextStats(await c.json())
            setError('')
        } catch (e) { setError('NemoClaw API unreachable — start the backend server.') }
        finally { setLoading(false) }
    }, [])

    useEffect(() => { fetchAll(); const t = setInterval(fetchAll, 15000); return () => clearInterval(t) }, [fetchAll])

    const loadTrace = async (id) => {
        const res = await fetch(`${API}/api/v1/nemoclaw/traces/${id}`, { headers: getAuthHeader() })
        if (res.ok) setSelectedTrace(await res.json())
    }

    const runGoal = async () => {
        if (!goalText.trim()) return
        setRunning(true); setRunResult(null)
        try {
            const res = await fetch(`${API}/api/v1/nemoclaw/run`, {
                method: 'POST', headers: getAuthHeader(),
                body: JSON.stringify({ goal_text: goalText, budget_usd: budgetUsd }),
            })
            const data = await res.json()
            setRunResult(data)
            setTimeout(fetchAll, 1000)
        } catch { setRunResult({ error: 'Failed to run goal' }) }
        finally { setRunning(false) }
    }

    const TABS = [
        { id: 'overview', label: 'Overview', Icon: Activity },
        { id: 'run', label: 'Run Goal', Icon: Zap },
        { id: 'traces', label: 'Traces', Icon: Terminal },
        { id: 'context', label: 'ContextGraph', Icon: Database },
        { id: 'cost', label: 'CostWatcher', Icon: DollarSign },
    ]

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-start justify-between">
                <div>
                    <div className="flex items-center gap-3 mb-1">
                        <div className="p-2 rounded-xl" style={{ background: 'rgba(123,47,255,0.15)' }}>
                            <Brain size={22} style={{ color: '#7B2FFF' }} />
                        </div>
                        <div>
                            <h1 className="text-2xl font-bold text-white">NemoClaw Engine</h1>
                            <p className="text-xs text-slate-500">OpenClaw Multi-Agent Cognitive Layer · v1.0.0</p>
                        </div>
                    </div>
                    <p className="text-sm text-slate-400 max-w-xl">
                        ContextGraph · AdaptiveReAct · PredictivePrefetch · CostWatcher — institutional memory for agentic GPU orchestration.
                    </p>
                </div>
                <button onClick={fetchAll} className="btn-ghost flex items-center gap-1.5 text-xs">
                    <RefreshCw size={12} /> Refresh
                </button>
            </div>

            {error && (
                <div className="glass-card p-3 border border-red-500/30 bg-red-500/10 flex items-center gap-2">
                    <AlertTriangle size={14} className="text-red-400" />
                    <p className="text-sm text-red-400">{error}</p>
                </div>
            )}

            {/* Status pill */}
            {status && (
                <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: STATUS_COLOR[status.engine_status] || '#94a3b8' }} />
                    <span className="text-sm" style={{ color: STATUS_COLOR[status.engine_status] }}>
                        {status.engine_status.toUpperCase()}
                    </span>
                    <span className="text-slate-600 text-sm">·</span>
                    <span className="text-slate-400 text-sm">{status.top_context_insight}</span>
                </div>
            )}

            {/* Tabs */}
            <div className="flex gap-1 border-b border-white/[0.08]">
                {TABS.map(({ id, label, Icon }) => (
                    <button key={id} onClick={() => setTab(id)}
                        className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-all"
                        style={{
                            color: tab === id ? '#7B2FFF' : '#94a3b8',
                            borderBottom: tab === id ? '2px solid #7B2FFF' : '2px solid transparent',
                            background: 'none', cursor: 'pointer',
                        }}>
                        <Icon size={13} /> {label}
                    </button>
                ))}
            </div>

            {/* ── Overview Tab ── */}
            {tab === 'overview' && (
                <div className="space-y-5">
                    <div className="grid grid-cols-2 gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
                        <StatCard icon={Database} label="Context Nodes" value={status?.context_nodes ?? '—'} sub="Persistent knowledge graph" color="#7B2FFF" glow />
                        <StatCard icon={Eye} label="Active Traces" value={status?.active_traces ?? '—'} sub="AdaptiveReAct traces" color="#00D4FF" />
                        <StatCard icon={Zap} label="Goals Processed" value={status?.total_goals_processed ?? '—'} sub="Through NemoClaw" color="#00FF88" />
                        <StatCard icon={CheckCircle} label="Avg Confidence" value={status ? `${(status.avg_confidence * 100).toFixed(0)}%` : '—'} sub="Self-eval score" color="#FFB800" />
                        <StatCard icon={Shield} label="Cost Brakes" value={status?.cost_brakes_fired ?? '—'} sub="Budget enforcements" color="#ff6b6b" />
                        <StatCard icon={Server} label="Prefetch Recs" value={status?.prefetch_recommendations?.length ?? '—'} sub="GPU pre-warm alerts" color="#A78BFA" />
                    </div>

                    {/* Prefetch recommendations */}
                    {status?.prefetch_recommendations?.length > 0 && (
                        <div className="glass-card p-5">
                            <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
                                <Zap size={14} style={{ color: '#A78BFA' }} /> PredictivePrefetch Recommendations
                            </h3>
                            <div className="space-y-2">
                                {status.prefetch_recommendations.map(rec => (
                                    <div key={rec.rec_id} className="flex items-center gap-3 p-3 rounded-lg" style={{ background: 'rgba(167,139,250,0.05)', border: '1px solid rgba(167,139,250,0.15)' }}>
                                        <div className="flex-1">
                                            <p className="text-sm text-white font-medium">{rec.predicted_gpu} via {rec.predicted_provider}</p>
                                            <p className="text-xs text-slate-500 mt-0.5">{rec.reasoning}</p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-xs font-mono" style={{ color: '#A78BFA' }}>{(rec.confidence * 100).toFixed(0)}% confident</p>
                                            <p className="text-xs text-slate-500">Save {rec.estimated_save_minutes}min cold-start</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* ── Run Goal Tab ── */}
            {tab === 'run' && (
                <div className="glass-card p-6 space-y-5">
                    <h3 className="text-white font-semibold">AdaptiveReAct Goal Execution</h3>
                    <p className="text-xs text-slate-500">Submit a goal through NemoClaw's enhanced ReAct engine with context retrieval and self-evaluation.</p>
                    <div>
                        <label className="block text-sm font-medium text-slate-300 mb-1.5">Goal Description</label>
                        <textarea
                            className="input-field resize-none"
                            placeholder="e.g. Fine-tune LLaMA 3 70B on my dataset, budget under $80, use cheapest A100 spot"
                            rows={3}
                            value={goalText}
                            onChange={e => setGoalText(e.target.value)}
                            style={{ fontFamily: 'inherit' }}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-300 mb-1.5">Budget (USD): ${budgetUsd}</label>
                        <input type="range" min={10} max={1000} step={10} value={budgetUsd}
                            onChange={e => setBudgetUsd(Number(e.target.value))}
                            style={{ width: '100%', accentColor: '#7B2FFF' }} />
                        <div className="flex justify-between text-xs text-slate-600 mt-0.5">
                            <span>$10</span><span>$1000</span>
                        </div>
                    </div>
                    <button className="btn-primary flex items-center gap-2" onClick={runGoal} disabled={running || !goalText.trim()}
                        style={{ background: 'linear-gradient(135deg, #7B2FFF, #00D4FF)' }}>
                        {running ? <RefreshCw size={14} className="animate-spin" /> : <Brain size={14} />}
                        {running ? 'Running NemoClaw...' : 'Execute with NemoClaw'}
                    </button>

                    {runResult && (
                        <div className="glass-card p-4 border border-violet-500/20 space-y-2">
                            {runResult.error ? (
                                <p className="text-red-400 text-sm">{runResult.error}</p>
                            ) : (
                                <>
                                    <div className="flex items-center gap-2 mb-2">
                                        <CheckCircle size={14} style={{ color: '#00FF88' }} />
                                        <span className="text-sm font-medium text-white">Goal Submitted via NemoClaw</span>
                                    </div>
                                    <p className="text-xs text-slate-400">Trace ID: <code className="text-violet-400">{runResult.trace_id}</code></p>
                                    <p className="text-xs text-slate-400">Confidence: <span className="text-white font-semibold">{((runResult.confidence || 0) * 100).toFixed(0)}%</span></p>
                                    <p className="text-xs text-slate-400">Context nodes used: <span className="text-white">{runResult.past_context_used}</span></p>
                                    {runResult.past_context_summary && (
                                        <p className="text-xs text-slate-500 italic">"{runResult.past_context_summary}"</p>
                                    )}
                                    {runResult.prefetch_recommendations?.length > 0 && (
                                        <p className="text-xs text-violet-400">
                                            💡 Prefetch: Pre-warm {runResult.prefetch_recommendations[0].predicted_gpu} on {runResult.prefetch_recommendations[0].predicted_provider}
                                        </p>
                                    )}
                                </>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* ── Traces Tab ── */}
            {tab === 'traces' && (
                <div className="grid gap-5" style={{ gridTemplateColumns: selectedTrace ? '1fr 1fr' : '1fr' }}>
                    <div className="glass-card p-5">
                        <h3 className="text-white font-semibold mb-3">Recent AdaptiveReAct Traces</h3>
                        {traces.length === 0 ? (
                            <p className="text-slate-500 text-sm">No traces yet. Run a goal to generate a trace.</p>
                        ) : (
                            <div className="space-y-2">
                                {traces.map(t => (
                                    <button key={t.trace_id} onClick={() => loadTrace(t.trace_id)}
                                        className="w-full text-left p-3 rounded-lg transition-all hover:bg-white/5"
                                        style={{ border: `1px solid ${selectedTrace?.trace_id === t.trace_id ? 'rgba(123,47,255,0.4)' : 'rgba(255,255,255,0.05)'}` }}>
                                        <div className="flex justify-between items-center">
                                            <code className="text-xs text-violet-400">{t.trace_id}</code>
                                            <span className="text-xs" style={{ color: t.status === 'completed' ? '#00FF88' : '#FFB800' }}>{t.status}</span>
                                        </div>
                                        <p className="text-xs text-slate-400 mt-1">{t.steps_count} steps · {(t.final_confidence * 100).toFixed(0)}% confidence</p>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {selectedTrace && (
                        <div className="glass-card p-5">
                            <h3 className="text-white font-semibold mb-1">Trace Detail</h3>
                            <p className="text-xs text-slate-500 mb-3">
                                Confidence: <span className="text-white">{(selectedTrace.final_confidence * 100).toFixed(0)}%</span>
                                {' · '}Replans: <span className="text-white">{selectedTrace.replans_triggered}</span>
                            </p>
                            <div className="space-y-0 max-h-64 overflow-y-auto pr-1" style={{ scrollbarWidth: 'thin' }}>
                                {selectedTrace.steps.map((step, i) => <TraceStep key={i} step={step} idx={i} />)}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* ── ContextGraph Tab ── */}
            {tab === 'context' && (
                <div className="space-y-4">
                    <div className="glass-card p-5">
                        <h3 className="text-white font-semibold mb-3">ContextGraph Statistics</h3>
                        {contextStats ? (
                            <div className="grid grid-cols-2 gap-4">
                                <div className="glass-card p-4 bg-white/[0.02]">
                                    <p className="text-xs text-slate-500 mb-1">Total Nodes</p>
                                    <p className="text-2xl font-bold text-white font-mono">{contextStats.total_nodes}</p>
                                </div>
                                <div className="glass-card p-4 bg-white/[0.02]">
                                    <p className="text-xs text-slate-500 mb-1">Unique Users</p>
                                    <p className="text-2xl font-bold text-white font-mono">{contextStats.total_users}</p>
                                </div>
                                {Object.entries(contextStats.by_type || {}).map(([type, count]) => (
                                    <div key={type} className="glass-card p-3 bg-white/[0.02]">
                                        <p className="text-xs text-slate-500 mb-0.5 capitalize">{type.replace('_', ' ')}</p>
                                        <p className="text-lg font-bold text-violet-400 font-mono">{count}</p>
                                    </div>
                                ))}
                            </div>
                        ) : <p className="text-slate-500 text-sm">Loading...</p>}
                    </div>
                    <div className="glass-card p-5 border border-violet-500/20">
                        <h3 className="text-white font-semibold mb-2 text-sm">About the ContextGraph</h3>
                        <p className="text-xs text-slate-400 leading-relaxed">
                            The NemoClaw ContextGraph stores every goal, decision, and outcome as a weighted semantic node.
                            It enables cross-session institutional memory — the more goals you run, the smarter OrQuanta gets
                            at recommending GPUs, providers, and cost-saving strategies. Nodes decay over time if not accessed
                            and are evicted when the 10,000 node limit is reached. Production upgrade: pgvector for true
                            cosine similarity search at scale.
                        </p>
                    </div>
                </div>
            )}

            {/* ── CostWatcher Tab ── */}
            {tab === 'cost' && (
                <div className="glass-card p-5">
                    <h3 className="text-white font-semibold mb-3">CostWatcher — Budget Enforcement Events</h3>
                    {brakes.length === 0 ? (
                        <div className="text-center py-8">
                            <TrendingDown size={32} className="mx-auto mb-2 opacity-20 text-white" />
                            <p className="text-slate-500 text-sm">No budget enforcement events yet.</p>
                            <p className="text-xs text-slate-600 mt-1">CostWatcher fires at 50% (warn), 80% (throttle), 95% (halt).</p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {brakes.map(b => (
                                <div key={b.brake_id} className="flex items-center gap-4 p-3 rounded-lg"
                                    style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                                    <span className="font-mono text-xs px-2 py-0.5 rounded" style={{ background: ACTION_COLOR[b.action_taken] + '20', color: ACTION_COLOR[b.action_taken] }}>
                                        {b.action_taken.toUpperCase()}
                                    </span>
                                    <div className="flex-1">
                                        <p className="text-sm text-white">${b.spent_usd} / ${b.budget_usd} ({b.pct_used}%)</p>
                                        <p className="text-xs text-slate-500">Switch to: {b.alternative} · Save ${b.potential_save_usd}</p>
                                    </div>
                                    <p className="text-xs text-slate-600">{new Date(b.fired_at).toLocaleTimeString()}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
