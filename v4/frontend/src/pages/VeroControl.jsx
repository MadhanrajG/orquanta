/**
 * VeroControl — Full-page Vero Command Center
 *
 * 4-panel layout:
 * 1. Agent Health Grid     — live KPI scores for all 5 agents
 * 2. User Intelligence     — login counter, DAU/MAU, session analytics
 * 3. Market Trends         — GPU price signals + UI recommendations
 * 4. Vero Decision Log     — NeMoClaw-style reasoning trace
 *
 * Polls /api/v1/vero/status every 10s.
 * Market trends polled separately from /api/v1/vero/market-trends every 30s.
 */

import { useState, useEffect, useContext, useRef } from 'react'
import { AuthContext } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

const AGENT_META = {
    master_orchestrator:  { label: 'OrMind',    icon: '', color: '#00D4FF' },
    scheduler_agent:       { label: 'Scheduler', icon: '', color: '#7B2FFF' },
    cost_optimizer_agent:  { label: 'Cost AI',   icon: '', color: '#FFB800' },
    healing_agent:         { label: 'Healer',    icon: '', color: '#00FF88' },
    forecast_agent:        { label: 'Forecast',  icon: '', color: '#F472B6' },
}

const URGENCY_COLOR = { critical: '#ef4444', high: '#FFB800', medium: '#00D4FF', low: '#64748b' }
const URGENCY_EMOJI = { critical: '', high: '', medium: '', low: '' }
const SEV_COLOR = { critical: '#ef4444', warning: '#FFB800', info: '#00D4FF' }

/* ── Reusable stat card ── */
function KpiBar({ label, value, color }) {
    return (
        <div style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                <span style={{ fontSize: 11, color: '#64748b' }}>{label}</span>
                <span style={{ fontSize: 11, fontWeight: 600, color }}>{(value * 100).toFixed(0)}%</span>
            </div>
            <div style={{ height: 4, borderRadius: 999, background: 'rgba(255,255,255,0.06)' }}>
                <div style={{
                    height: '100%', borderRadius: 999,
                    width: `${Math.min(value * 100, 100)}%`,
                    background: value >= 0.80 ? '#00FF88' : value >= 0.60 ? '#FFB800' : '#ef4444',
                    transition: 'width 0.6s ease',
                    boxShadow: `0 0 6px ${value >= 0.80 ? '#00FF88' : value >= 0.60 ? '#FFB800' : '#ef4444'}60`,
                }} />
            </div>
        </div>
    )
}

/* ── Agent health card ── */
function AgentCard({ kpi, onInject }) {
    const meta = AGENT_META[kpi.name] || { label: kpi.name, icon: '', color: '#64748b' }
    const statusColor = kpi.status === 'healthy' ? '#00FF88' : kpi.status === 'degraded' ? '#FFB800' : '#ef4444'
    return (
        <div style={{
            background: 'rgba(255,255,255,0.03)',
            border: `1px solid ${meta.color}20`,
            borderRadius: 14, padding: '14px 16px',
            position: 'relative', overflow: 'hidden',
        }}>
            <div style={{
                position: 'absolute', top: -20, right: -20, width: 80, height: 80,
                background: `radial-gradient(circle, ${meta.color}10, transparent 70%)`,
                pointerEvents: 'none',
            }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <div style={{
                    width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                    background: `${meta.color}15`, border: `1px solid ${meta.color}30`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18,
                }}>
                    {meta.icon}
                </div>
                <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: 'white' }}>{meta.label}</div>
                    <div style={{ fontSize: 11, color: statusColor, display: 'flex', alignItems: 'center', gap: 5 }}>
                        <span style={{
                            width: 6, height: 6, borderRadius: '50%',
                            background: statusColor, boxShadow: `0 0 5px ${statusColor}`,
                            display: 'inline-block',
                        }} />
                        {kpi.status}
                    </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 20, fontWeight: 800, color: meta.color }}>
                        {(kpi.overall_score * 100).toFixed(0)}
                    </div>
                    <div style={{ fontSize: 10, color: '#64748b' }}>KPI</div>
                </div>
            </div>
            <KpiBar label="Responsiveness" value={kpi.kpis?.responsiveness ?? 0.9} color={meta.color} />
            <KpiBar label="Decision Quality" value={kpi.kpis?.decision_quality ?? 0.88} color={meta.color} />
            <KpiBar label="Cost Efficiency" value={kpi.kpis?.cost_efficiency ?? 0.85} color={meta.color} />
            <KpiBar label="SLA Compliance" value={kpi.kpis?.sla ?? 0.97} color={meta.color} />
            {kpi.corrective_goals_injected > 0 && (
                <div style={{
                    marginTop: 10, padding: '5px 10px', borderRadius: 8,
                    background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
                    fontSize: 11, color: '#fca5a5',
                }}>
                    {kpi.corrective_goals_injected} corrective goals injected
                </div>
            )}
        </div>
    )
}

/* ── Main Component ── */
export default function VeroControl() {
    const { token } = useContext(AuthContext)
    const [status, setStatus] = useState(null)
    const [trends, setTrends] = useState(null)
    const [loading, setLoading] = useState(true)
    const [injectGoal, setInjectGoal] = useState('')
    const [injectAgent, setInjectAgent] = useState('master_orchestrator')
    const [injecting, setInjecting] = useState(false)
    const [injectMsg, setInjectMsg] = useState('')
    const logRef = useRef(null)

    const authHeader = { Authorization: `Bearer ${token}` }

    useEffect(() => {
        const loadStatus = async () => {
            try {
                const r = await fetch(`${API}/api/v1/vero/status`, { headers: authHeader })
                if (r.ok) { setStatus(await r.json()); setLoading(false) }
            } catch {}
        }
        const loadTrends = async () => {
            try {
                const r = await fetch(`${API}/api/v1/vero/market-trends`, { headers: authHeader })
                if (r.ok) setTrends(await r.json())
            } catch {}
        }
        loadStatus(); loadTrends()
        const t1 = setInterval(loadStatus, 10000)
        const t2 = setInterval(loadTrends, 30000)
        return () => { clearInterval(t1); clearInterval(t2) }
    }, [token])

    const handleInject = async () => {
        if (!injectGoal.trim()) return
        setInjecting(true)
        try {
            const r = await fetch(`${API}/api/v1/vero/inject-goal`, {
                method: 'POST',
                headers: { ...authHeader, 'Content-Type': 'application/json' },
                body: JSON.stringify({ goal_text: injectGoal, target_agent: injectAgent, priority: 9 }),
            })
            const data = await r.json()
            setInjectMsg(r.ok ? `Goal injected (${data.decision_id})` : data.detail || 'Inject failed')
            if (r.ok) setInjectGoal('')
        } catch (e) { setInjectMsg('Network error') }
        setInjecting(false)
        setTimeout(() => setInjectMsg(''), 4000)
    }

    const veroStatusColor = status?.vero_status === 'nominal' ? '#00FF88'
        : status?.vero_status === 'alert' ? '#FFB800'
        : status?.vero_status === 'critical' ? '#ef4444'
        : '#7B2FFF'

    const agents = status?.agent_report || []
    const userIntel = status?.user_intelligence || {}
    const marketIntel = status?.market_intelligence || {}
    const decisions = status?.recent_decisions || []

    return (
        <div className="space-y-5 animate-fade-in" style={{ color: 'white' }}>

            {/* ── Header ── */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    <div style={{
                        width: 48, height: 48, borderRadius: 14,
                        background: `linear-gradient(135deg, #7B2FFF, #00D4FF)`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 24, boxShadow: `0 0 24px #7B2FFF60`,
                    }}>
                        
                    </div>
                    <div>
                        <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: -0.5 }}>
                            Vero Command Center
                        </h1>
                        <p style={{ fontSize: 13, color: '#64748b' }}>
                            Superior Intelligence Meta-Agent · NeMoClaw Architecture
                        </p>
                    </div>
                </div>

                {/* Status badge */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 18px', borderRadius: 12,
                    background: `${veroStatusColor}12`,
                    border: `1px solid ${veroStatusColor}30`,
                }}>
                    <span style={{
                        width: 8, height: 8, borderRadius: '50%',
                        background: veroStatusColor, boxShadow: `0 0 8px ${veroStatusColor}`,
                        animation: 'pulse 1.5s infinite',
                    }} />
                    <span style={{ fontWeight: 700, color: veroStatusColor, textTransform: 'uppercase', fontSize: 12, letterSpacing: 1 }}>
                        {status?.vero_status || 'initializing'}
                    </span>
                    <span style={{ color: '#64748b', fontSize: 12 }}>
                        {status ? `${status.loops_completed} cycles · ${Math.floor(status.uptime_seconds / 60)}m uptime` : 'Booting...'}
                    </span>
                </div>
            </div>

            {/* ── Row 1: Summary KPIs ── */}
            {status && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
                    {[
                        { label: 'Agents Healthy', value: `${status.agent_summary?.healthy ?? 0}/5`, color: '#00FF88', icon: '' },
                        { label: 'Active Users', value: userIntel.active_sessions ?? 0, color: '#00D4FF', icon: '' },
                        { label: 'Logins Today', value: userIntel.total_logins_today ?? 0, color: '#7B2FFF', icon: '' },
                        { label: 'DAU', value: userIntel.dau ?? 0, color: '#F472B6', icon: '' },
                        { label: 'UI Trends', value: marketIntel.ui_recommendations_count ?? 0, color: '#FFB800', icon: '' },
                    ].map(({ label, value, color, icon }) => (
                        <div key={label} style={{
                            background: 'rgba(255,255,255,0.03)',
                            border: `1px solid ${color}20`,
                            borderRadius: 12, padding: '14px 16px', textAlign: 'center',
                        }}>
                            <div style={{ fontSize: 11, marginBottom: 2 }}>{icon}</div>
                            <div style={{ fontSize: 22, fontWeight: 800, color }}>{value}</div>
                            <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{label}</div>
                        </div>
                    ))}
                </div>
            )}

            {/* ── Row 2: Agent Health Grid + Goal Inject ── */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 16 }}>

                {/* Agent health grid */}
                <div className="glass-card" style={{ padding: 20 }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: 'white', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span> Agent Health Grid</span>
                        <span style={{ fontSize: 11, color: '#64748b', marginLeft: 'auto' }}>Updated every 15s</span>
                    </div>
                    {loading ? (
                        <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
                            Waiting for Vero first cycle (15s)...
                        </div>
                    ) : (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
                            {(agents.length > 0 ? agents : Object.keys(AGENT_META).map(name => ({
                                name, status: 'healthy', overall_score: 0.92, kpis: { responsiveness: 0.94, decision_quality: 0.90, cost_efficiency: 0.88, sla: 0.97 }, corrective_goals_injected: 0
                            }))).map(kpi => (
                                <AgentCard key={kpi.name} kpi={kpi} />
                            ))}
                        </div>
                    )}
                </div>

                {/* Manual goal injection */}
                <div className="glass-card" style={{ padding: 20 }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: 'white', marginBottom: 16 }}>
                         Manual Goal Injection
                    </div>
                    <div style={{ fontSize: 12, color: '#64748b', marginBottom: 12 }}>
                        Manually inject a corrective goal into any agent via Vero's pipeline.
                    </div>
                    <div style={{ marginBottom: 10 }}>
                        <label style={{ fontSize: 11, color: '#64748b', marginBottom: 4, display: 'block' }}>Target Agent</label>
                        <select
                            value={injectAgent}
                            onChange={e => setInjectAgent(e.target.value)}
                            style={{
                                width: '100%', background: 'rgba(0,0,0,0.4)',
                                border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8,
                                color: 'white', padding: '8px 12px', fontSize: 13,
                            }}
                        >
                            {Object.entries(AGENT_META).map(([k, v]) => (
                                <option key={k} value={k}>{v.icon} {v.label}</option>
                            ))}
                        </select>
                    </div>
                    <div style={{ marginBottom: 12 }}>
                        <label style={{ fontSize: 11, color: '#64748b', marginBottom: 4, display: 'block' }}>Goal Text</label>
                        <textarea
                            value={injectGoal}
                            onChange={e => setInjectGoal(e.target.value)}
                            placeholder="e.g. Reinitialise scheduler queue and reset priority scoring..."
                            rows={4}
                            style={{
                                width: '100%', background: 'rgba(0,0,0,0.4)',
                                border: '1px solid rgba(0,212,255,0.2)', borderRadius: 8,
                                color: 'white', padding: '10px 12px', fontSize: 12,
                                resize: 'vertical', fontFamily: 'inherit', outline: 'none',
                            }}
                        />
                    </div>
                    <button
                        onClick={handleInject}
                        disabled={injecting || !injectGoal.trim()}
                        style={{
                            width: '100%', padding: '10px',
                            background: injecting ? 'rgba(255,255,255,0.05)' : 'linear-gradient(135deg, #7B2FFF, #00D4FF)',
                            border: 'none', borderRadius: 10, color: 'white',
                            fontWeight: 700, fontSize: 13, cursor: injecting ? 'not-allowed' : 'pointer',
                        }}
                    >
                        {injecting ? 'Injecting...' : ' Inject via Vero'}
                    </button>
                    {injectMsg && (
                        <div style={{
                            marginTop: 10, padding: '8px 12px',
                            background: injectMsg.includes('injected') ? 'rgba(0,255,136,0.1)' : 'rgba(239,68,68,0.1)',
                            border: `1px solid ${injectMsg.includes('injected') ? 'rgba(0,255,136,0.3)' : 'rgba(239,68,68,0.3)'}`,
                            borderRadius: 8, fontSize: 12,
                            color: injectMsg.includes('injected') ? '#00FF88' : '#fca5a5',
                        }}>
                            {injectMsg}
                        </div>
                    )}

                    {/* User intel mini card */}
                    <div style={{
                        marginTop: 16, padding: '14px', borderRadius: 12,
                        background: 'rgba(0,212,255,0.06)', border: '1px solid rgba(0,212,255,0.15)',
                    }}>
                        <div style={{ fontSize: 12, color: '#00D4FF', fontWeight: 700, marginBottom: 8 }}>
                             User Intelligence
                        </div>
                        {[
                            ['Active Sessions', userIntel.active_sessions ?? '—', '#00D4FF'],
                            ['DAU/MAU', `${userIntel.dau ?? 0}/${userIntel.mau ?? 0}`, '#7B2FFF'],
                            ['Login Trend', userIntel.login_trend ?? 'stable', userIntel.login_trend === 'rising' ? '#00FF88' : '#64748b'],
                            ['GPU Price Trend', marketIntel.gpu_price_trend ?? 'stable', marketIntel.gpu_price_trend === 'dropping' ? '#00FF88' : '#FFB800'],
                        ].map(([label, val, color]) => (
                            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                                <span style={{ fontSize: 11, color: '#64748b' }}>{label}</span>
                                <span style={{ fontSize: 11, fontWeight: 600, color }}>{val}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* ── Row 3: Market Trends + Decision Log ── */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>

                {/* Market trends */}
                <div className="glass-card" style={{ padding: 20 }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: 'white', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
                         Market-Driven UI Recommendations
                    </div>
                    {trends?.market && (
                        <div style={{
                            display: 'flex', gap: 16, marginBottom: 16,
                            padding: '10px 14px', borderRadius: 10,
                            background: 'rgba(255,184,0,0.06)', border: '1px solid rgba(255,184,0,0.15)',
                        }}>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: 14, fontWeight: 700, color: '#FFB800' }}>
                                    ${trends.market.cheapest_price_usd?.toFixed(2)}/hr
                                </div>
                                <div style={{ fontSize: 10, color: '#64748b' }}>Best price</div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: 14, fontWeight: 700, color: trends.market.price_trend === 'dropping' ? '#00FF88' : '#FFB800' }}>
                                    {trends.market.price_trend}
                                </div>
                                <div style={{ fontSize: 10, color: '#64748b' }}>Trend</div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: 14, fontWeight: 700, color: '#F472B6' }}>
                                    {(trends.market.gpu_scarcity_index * 100).toFixed(0)}%
                                </div>
                                <div style={{ fontSize: 10, color: '#64748b' }}>Scarcity</div>
                            </div>
                        </div>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                        {(trends?.ui_recommendations || []).map(rec => (
                            <div key={rec.id} style={{
                                padding: '12px 14px', borderRadius: 12,
                                background: `${URGENCY_COLOR[rec.urgency] || '#64748b'}08`,
                                border: `1px solid ${URGENCY_COLOR[rec.urgency] || '#64748b'}25`,
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                                    <span style={{ fontSize: 14 }}>{URGENCY_EMOJI[rec.urgency]}</span>
                                    <span style={{
                                        fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1,
                                        color: URGENCY_COLOR[rec.urgency] || '#64748b',
                                        background: `${URGENCY_COLOR[rec.urgency]}15`,
                                        padding: '1px 8px', borderRadius: 999,
                                    }}>
                                        {rec.urgency}
                                    </span>
                                    <span style={{ fontSize: 11, color: '#64748b', marginLeft: 'auto' }}>
                                        {rec.component}
                                    </span>
                                </div>
                                <div style={{ fontSize: 12, color: 'white', marginBottom: 4 }}>{rec.change}</div>
                                <div style={{ fontSize: 11, color: '#64748b' }}>{rec.rationale}</div>
                                <div style={{ marginTop: 6, fontSize: 10, color: '#475569' }}>
                                    Signal: {rec.data_signal} · Confidence: {(rec.confidence * 100).toFixed(0)}%
                                </div>
                            </div>
                        ))}
                        {(!trends?.ui_recommendations || trends.ui_recommendations.length === 0) && (
                            <div style={{ padding: 20, textAlign: 'center', color: '#64748b', fontSize: 13 }}>
                                Market trends loading... (refreshes every 5 minutes)
                            </div>
                        )}
                    </div>
                </div>

                {/* Decision log */}
                <div className="glass-card" style={{ padding: 20, display: 'flex', flexDirection: 'column' }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: 'white', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                         Vero Decision Log
                        <span style={{ fontSize: 11, color: '#64748b', marginLeft: 'auto' }}>Live NeMoClaw trace</span>
                    </div>
                    <div ref={logRef} style={{ flex: 1, overflowY: 'auto', maxHeight: 480, display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {decisions.length === 0 ? (
                            <div style={{ padding: 20, textAlign: 'center', color: '#64748b', fontSize: 13 }}>
                                Vero decision log is empty — decisions will appear as Vero monitors agents.
                            </div>
                        ) : decisions.map(d => (
                            <div key={d.id} style={{
                                padding: '10px 14px', borderRadius: 12,
                                background: `${SEV_COLOR[d.severity] || '#64748b'}08`,
                                border: `1px solid ${SEV_COLOR[d.severity] || '#64748b'}20`,
                                borderLeft: `3px solid ${SEV_COLOR[d.severity] || '#64748b'}`,
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                    <span style={{
                                        fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1,
                                        color: SEV_COLOR[d.severity] || '#64748b',
                                        background: `${SEV_COLOR[d.severity]}15`, padding: '1px 7px', borderRadius: 999,
                                    }}>
                                        {d.decision_type}
                                    </span>
                                    <span style={{ fontSize: 10, color: '#475569', marginLeft: 'auto' }}>
                                        {d.id}
                                    </span>
                                </div>
                                <div style={{ fontSize: 12, color: 'white', fontWeight: 500, marginBottom: 3 }}>
                                    {d.action}
                                </div>
                                <div style={{ fontSize: 11, color: '#64748b', lineHeight: 1.5 }}>{d.reasoning}</div>
                                <div style={{ fontSize: 10, color: '#475569', marginTop: 4 }}>
                                    Target: <span style={{ color: '#94a3b8' }}>{d.target}</span>
                                    &nbsp;·&nbsp;
                                    {new Date(d.timestamp).toLocaleTimeString()}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    )
}
