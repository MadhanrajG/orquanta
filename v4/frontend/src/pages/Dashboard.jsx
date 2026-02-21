import { useState, useEffect, useRef, useCallback } from 'react'
import {
    Activity, Server, DollarSign, Zap, TrendingUp, TrendingDown,
    CheckCircle, AlertCircle, Clock, Globe, Sparkles, Brain, Shield,
    BarChart2, Cpu, ArrowUp, ArrowDown
} from 'lucide-react'
import {
    AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
    LineChart, Line, ReferenceLine
} from 'recharts'
import { useAuth } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

/* ─── Shared fetch hook ───────────────────────────────────────────────── */
function useApi(endpoint, interval = 6000) {
    const { token } = useAuth()
    const [data, setData] = useState(null)
    useEffect(() => {
        const go = async () => {
            try {
                const r = await fetch(`${API}${endpoint}`, { headers: { Authorization: `Bearer ${token}` } })
                if (r.ok) setData(await r.json())
            } catch { }
        }
        go()
        const t = setInterval(go, interval)
        return () => clearInterval(t)
    }, [endpoint, token])
    return data
}

/* ─── Live UTC clock ──────────────────────────────────────────────────── */
function LiveClock() {
    const [now, setNow] = useState(new Date())
    useEffect(() => { const t = setInterval(() => setNow(new Date()), 100); return () => clearInterval(t) }, [])
    return (
        <span className="font-mono text-xs text-slate-400 tabular-nums tracking-wide">
            {now.toUTCString().replace('GMT', 'UTC')}
        </span>
    )
}

/* ─── Health Score Ring ───────────────────────────────────────────────── */
function HealthRing({ score = 97 }) {
    const r = 22, circ = 2 * Math.PI * r
    const dash = circ * (score / 100)
    const color = score >= 90 ? '#00FF88' : score >= 70 ? '#FFB800' : '#FF4444'
    return (
        <div className="flex items-center gap-3">
            <div className="relative w-14 h-14">
                <svg viewBox="0 0 56 56" className="rotate-[-90deg] w-full h-full">
                    <circle cx="28" cy="28" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4" />
                    <circle cx="28" cy="28" r={r} fill="none" stroke={color} strokeWidth="4"
                        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
                        style={{ transition: 'stroke-dasharray 1s ease', filter: `drop-shadow(0 0 6px ${color})` }} />
                </svg>
                <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-white">{score}</span>
            </div>
            <div>
                <div className="text-sm font-semibold text-white">System Health</div>
                <div className="text-xs" style={{ color }}>{score >= 90 ? 'All Systems Optimal' : score >= 70 ? 'Minor Issues' : 'Action Required'}</div>
            </div>
        </div>
    )
}

/* ─── Sparkline mini chart ────────────────────────────────────────────── */
function Sparkline({ data, color = '#00D4FF' }) {
    return (
        <ResponsiveContainer width="100%" height={40}>
            <AreaChart data={data} margin={{ top: 2, bottom: 2 }}>
                <defs>
                    <linearGradient id={`spark-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={color} stopOpacity={0.25} />
                        <stop offset="95%" stopColor={color} stopOpacity={0} />
                    </linearGradient>
                </defs>
                <Area type="monotone" dataKey="v" stroke={color} strokeWidth={1.5}
                    fill={`url(#spark-${color.replace('#', '')})`} dot={false} />
            </AreaChart>
        </ResponsiveContainer>
    )
}

/* ─── Generate data ───────────────────────────────────────────────────── */
function genSpark(n = 24, base = 60, range = 30) {
    let v = base
    return Array.from({ length: n }, (_, i) => {
        v = Math.max(5, Math.min(100, v + (Math.random() - 0.45) * range * 0.3))
        return { t: i, v: Math.round(v) }
    })
}

/* ─── Hero Metric Card ────────────────────────────────────────────────── */
function HeroCard({ icon: Icon, label, value, sub, color, sparkColor, trend, sparkData }) {
    const glows = {
        blue: 'rgba(0,212,255,0.15)',
        green: 'rgba(0,255,136,0.12)',
        amber: 'rgba(255,184,0,0.12)',
        purple: 'rgba(123,47,255,0.15)',
    }
    const colors = {
        blue: '#00D4FF',
        green: '#00FF88',
        amber: '#FFB800',
        purple: '#7B2FFF',
    }
    const c = colors[color] || colors.blue
    return (
        <div className="glass-card p-5 relative overflow-hidden group transition-all duration-300 hover:-translate-y-1"
            style={{ boxShadow: `0 0 0 1px rgba(${color === 'blue' ? '0,212,255' : color === 'green' ? '0,255,136' : color === 'amber' ? '255,184,0' : '123,47,255'},0.12), 0 8px 32px rgba(0,0,0,0.4)` }}>
            {/* glow corner */}
            <div className="absolute -top-10 -right-10 w-32 h-32 rounded-full blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                style={{ background: glows[color] }} />
            <div className="flex items-start justify-between mb-2">
                <div className="p-2 rounded-xl" style={{ background: `${c}18`, border: `1px solid ${c}30` }}>
                    <Icon size={18} style={{ color: c }} />
                </div>
                {trend != null && (
                    <span className={`flex items-center gap-0.5 text-xs font-semibold ${trend >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {trend >= 0 ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
                        {Math.abs(trend)}%
                    </span>
                )}
            </div>
            <p className="text-2xl font-bold text-white mb-0.5 tabular-nums">{value ?? '—'}</p>
            <p className="text-xs font-medium text-slate-400">{label}</p>
            {sub && <p className="text-xs text-slate-600 mt-0.5">{sub}</p>}
            {sparkData && <div className="mt-3"><Sparkline data={sparkData} color={c} /></div>}
        </div>
    )
}

/* ─── World Map ───────────────────────────────────────────────────────── */
const GPU_NODES = [
    { id: 'aws-us-east', label: 'AWS us-east-1', x: '22%', y: '36%', active: true, count: 8 },
    { id: 'gcp-europe', label: 'GCP europe-w4', x: '48%', y: '28%', active: true, count: 3 },
    { id: 'lambda-ord', label: 'Lambda ORD1', x: '19%', y: '32%', active: true, count: 5 },
    { id: 'azure-east', label: 'Azure eastus', x: '21%', y: '34%', active: false, count: 0 },
    { id: 'cw-ord', label: 'CoreWeave ORD', x: '20%', y: '35%', active: true, count: 2 },
    { id: 'gcp-us', label: 'GCP us-central', x: '18%', y: '37%', active: true, count: 4 },
    { id: 'lambda-tx', label: 'Lambda us-tx-3', x: '17%', y: '40%', active: true, count: 6 },
    { id: 'aws-ap', label: 'AWS ap-south', x: '72%', y: '48%', active: false, count: 0 },
]

function WorldMap() {
    const [hovered, setHovered] = useState(null)
    return (
        <div className="glass-card p-5 relative overflow-hidden">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Globe size={16} className="text-cyan-400" />
                    <h3 className="font-semibold text-white text-sm">Active GPU Instances — Global</h3>
                </div>
                <span className="text-xs text-slate-500 font-mono">{GPU_NODES.filter(n => n.active).reduce((a, n) => a + n.count, 0)} GPUs active</span>
            </div>
            <div className="relative" style={{ paddingBottom: '48%' }}>
                {/* Simplified world SVG */}
                <svg viewBox="0 0 1000 500" className="absolute inset-0 w-full h-full opacity-20"
                    style={{ filter: 'drop-shadow(0 0 8px rgba(0,212,255,0.15))' }}>
                    <path fill="#00D4FF" d="M160,120 Q200,100 280,110 Q340,105 380,120 Q430,130 460,145 Q440,165 410,170 Q370,185 340,175 Q300,170 260,165 Q220,158 180,150 Z" />
                    <path fill="#00D4FF" d="M420,140 Q480,125 560,130 Q620,128 680,140 Q720,150 740,165 Q720,185 700,195 Q660,205 620,200 Q570,195 530,185 Q480,175 450,165 Z" />
                    <path fill="#00D4FF" d="M680,140 Q740,130 800,140 Q840,148 860,160 Q850,178 830,185 Q800,192 770,188 Q740,182 720,170 Z" />
                    <path fill="#00D4FF" d="M160,185 Q200,178 240,182 Q260,185 270,200 Q265,225 250,240 Q225,255 200,250 Q175,240 160,225 Q148,208 158,192 Z" />
                    <path fill="#00D4FF" d="M280,190 Q340,180 400,185 Q440,188 460,200 Q455,230 440,250 Q410,270 380,268 Q340,262 310,248 Q280,232 272,215 Z" />
                    <path fill="#00D4FF" d="M500,175 Q560,162 620,168 Q665,172 680,188 Q675,218 655,235 Q625,252 590,248 Q555,242 530,228 Q505,212 498,195 Z" />
                    <path fill="#00D4FF" d="M720,210 Q760,198 800,204 Q828,210 840,225 Q835,248 815,258 Q790,266 765,260 Q740,250 728,235 Z" />
                    <path fill="#00D4FF" d="M580,270 Q630,258 670,265 Q700,272 710,290 Q700,318 678,326 Q650,332 625,325 Q598,315 588,298 Z" />
                </svg>
                {/* GPU instance dots */}
                {GPU_NODES.map(node => (
                    <div key={node.id} className="absolute transform -translate-x-1/2 -translate-y-1/2 cursor-pointer z-10"
                        style={{ left: node.x, top: node.y }}
                        onMouseEnter={() => setHovered(node)} onMouseLeave={() => setHovered(null)}>
                        {node.active ? (
                            <>
                                <div className="w-3 h-3 rounded-full relative" style={{ background: '#00D4FF', boxShadow: '0 0 8px #00D4FF, 0 0 16px rgba(0,212,255,0.4)' }}>
                                    <div className="absolute inset-0 rounded-full animate-ping" style={{ background: 'rgba(0,212,255,0.3)' }} />
                                </div>
                            </>
                        ) : (
                            <div className="w-2 h-2 rounded-full bg-slate-600 opacity-40" />
                        )}
                        {hovered?.id === node.id && (
                            <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 whitespace-nowrap z-20
                bg-slate-900 border border-cyan-500/30 rounded-lg px-3 py-1.5 text-xs text-white shadow-xl">
                                <div className="font-semibold text-cyan-400">{node.label}</div>
                                <div className="text-slate-400">{node.count} GPU{node.count !== 1 ? 's' : ''} active</div>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}

/* ─── Agent Activity Feed ─────────────────────────────────────────────── */
const AGENT_COLORS = {
    master_orchestrator: { color: '#00D4FF', icon: '🧠', label: 'Orchestrator' },
    scheduler_agent: { color: '#7B2FFF', icon: '📅', label: 'Scheduler' },
    cost_optimizer_agent: { color: '#FFB800', icon: '💸', label: 'Cost Optimizer' },
    healing_agent: { color: '#00FF88', icon: '🔧', label: 'Healing' },
    forecast_agent: { color: '#F472B6', icon: '📊', label: 'Forecast' },
    audit_agent: { color: '#94A3B8', icon: '🔒', label: 'Audit' },
}

const DEMO_THOUGHTS = [
    { agent: 'cost_optimizer_agent', msg: 'Lambda Labs A100 @ $1.99/hr wins vs AWS $4.10/hr', time: 0 },
    { agent: 'scheduler_agent', msg: 'Job orq-7f2a queued — EDF priority: deadline in 4h', time: 1 },
    { agent: 'healing_agent', msg: 'All instances nominal. VRAM avg 71%. Temp 68°C.', time: 2 },
    { agent: 'master_orchestrator', msg: 'Goal decomposed: 4 subtasks dispatched to agents.', time: 3 },
    { agent: 'forecast_agent', msg: 'GPU demand peak predicted in ~2h: pre-warming pool', time: 4 },
    { agent: 'cost_optimizer_agent', msg: 'Spot interruption risk 8% — acceptable, saving $23/hr', time: 5 },
    { agent: 'audit_agent', msg: 'HMAC batch #47 signed. 12 decisions logged, zero anomalies.', time: 6 },
    { agent: 'healing_agent', msg: 'VRAM at 94% on inst-3d9a → prescaling memory...', time: 7 },
    { agent: 'healing_agent', msg: 'Memory prescaled. VRAM 94% → 69%. No data loss. ✓', time: 8 },
    { agent: 'cost_optimizer_agent', msg: 'Migrated 2 jobs from AWS to Lambda — saving $67.20/hr', time: 9 },
    { agent: 'scheduler_agent', msg: 'orq-9e1c completed. Cost: $12.40. Saved: $8.30 vs baseline.', time: 10 },
    { agent: 'master_orchestrator', msg: 'Platform health: 97/100. All agents responsive.', time: 11 },
]

function AgentFeed() {
    const [entries, setEntries] = useState(() =>
        DEMO_THOUGHTS.slice(0, 4).map((t, i) => ({ ...t, key: i, ts: Date.now() - (11 - i) * 4000 }))
    )
    useEffect(() => {
        let idx = 4
        const t = setInterval(() => {
            const thought = DEMO_THOUGHTS[idx % DEMO_THOUGHTS.length]
            setEntries(prev => [
                { ...thought, key: Date.now(), ts: Date.now() },
                ...prev.slice(0, 14)
            ])
            idx++
        }, 3000)
        return () => clearInterval(t)
    }, [])

    return (
        <div className="glass-card p-5 flex flex-col" style={{ minHeight: 320 }}>
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Brain size={16} className="text-cyan-400" />
                    <h3 className="font-semibold text-white text-sm">Agent Activity Feed</h3>
                </div>
                <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                    <span className="text-xs text-green-400">Live</span>
                </div>
            </div>
            <div className="flex-1 space-y-1.5 overflow-hidden">
                {entries.map((entry, i) => {
                    const cfg = AGENT_COLORS[entry.agent] || AGENT_COLORS.audit_agent
                    const age = (Date.now() - entry.ts) / 1000
                    return (
                        <div key={entry.key}
                            className="flex items-start gap-2.5 px-3 py-2 rounded-xl transition-all duration-500"
                            style={{
                                background: i === 0 ? `${cfg.color}12` : 'rgba(255,255,255,0.02)',
                                border: i === 0 ? `1px solid ${cfg.color}20` : '1px solid transparent',
                                opacity: Math.max(0.3, 1 - i * 0.08)
                            }}>
                            <span className="text-sm mt-px">{cfg.icon}</span>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-0.5">
                                    <span className="text-xs font-semibold" style={{ color: cfg.color }}>{cfg.label}</span>
                                    <span className="text-xs text-slate-600 font-mono">
                                        {age < 60 ? `${Math.round(age)}s ago` : `${Math.round(age / 60)}m ago`}
                                    </span>
                                </div>
                                <p className="text-xs text-slate-300 leading-relaxed">{entry.msg}</p>
                            </div>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

/* ─── GPU Utilization Chart ───────────────────────────────────────────── */
function UtilChart() {
    const [range, setRange] = useState('1h')
    const [data, setData] = useState(() => {
        const points = 60
        let a = 78, b = 65, c = 88
        return Array.from({ length: points }, (_, i) => {
            a = Math.max(20, Math.min(99, a + (Math.random() - 0.45) * 8))
            b = Math.max(15, Math.min(95, b + (Math.random() - 0.45) * 7))
            c = Math.max(30, Math.min(99, c + (Math.random() - 0.45) * 6))
            return {
                t: `${i}m`,
                lambda: Math.round(a),
                aws: Math.round(b),
                gcp: Math.round(c),
            }
        })
    })

    useEffect(() => {
        const t = setInterval(() => {
            setData(prev => {
                const last = prev[prev.length - 1]
                const newPt = {
                    t: `now`,
                    lambda: Math.max(20, Math.min(99, last.lambda + (Math.random() - 0.45) * 8)),
                    aws: Math.max(15, Math.min(95, last.aws + (Math.random() - 0.45) * 7)),
                    gcp: Math.max(30, Math.min(99, last.gcp + (Math.random() - 0.45) * 6)),
                }
                return [...prev.slice(-59), newPt]
            })
        }, 2000)
        return () => clearInterval(t)
    }, [])

    const CustomTooltip = ({ active, payload, label }) => {
        if (!active || !payload?.length) return null
        return (
            <div className="bg-slate-900 border border-white/10 rounded-xl p-3 text-xs shadow-2xl">
                <div className="text-slate-400 mb-2">{label}</div>
                {payload.map(p => (
                    <div key={p.dataKey} className="flex items-center gap-2 mb-1">
                        <div className="w-2 h-2 rounded-full" style={{ background: p.color }} />
                        <span className="text-slate-300 capitalize">{p.dataKey}:</span>
                        <span className="font-bold text-white">{Math.round(p.value)}%</span>
                    </div>
                ))}
            </div>
        )
    }

    return (
        <div className="glass-card p-5 xl:col-span-2">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <BarChart2 size={16} className="text-cyan-400" />
                    <h3 className="font-semibold text-white text-sm">GPU Utilization — Live Multi-Provider</h3>
                </div>
                <div className="flex gap-1">
                    {['1h', '6h', '24h', '7d'].map(r => (
                        <button key={r} onClick={() => setRange(r)}
                            className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all"
                            style={range === r
                                ? { background: 'rgba(0,212,255,0.15)', color: '#00D4FF', border: '1px solid rgba(0,212,255,0.3)' }
                                : { background: 'rgba(255,255,255,0.04)', color: '#64748b', border: '1px solid transparent' }
                            }>{r}</button>
                    ))}
                </div>
            </div>
            <div className="flex gap-4 mb-3">
                {[['lambda', '#00D4FF', 'Lambda Labs'], ['aws', '#F97316', 'AWS'], ['gcp', '#A78BFA', 'GCP']].map(([k, c, l]) => (
                    <div key={k} className="flex items-center gap-1.5">
                        <div className="w-3 h-0.5 rounded" style={{ background: c }} />
                        <span className="text-xs text-slate-400">{l}</span>
                    </div>
                ))}
            </div>
            <ResponsiveContainer width="100%" height={180}>
                <LineChart data={data} margin={{ left: -20, right: 8 }}>
                    <defs>
                        {[['lambda', '#00D4FF'], ['aws', '#F97316'], ['gcp', '#A78BFA']].map(([k, c]) => (
                            <linearGradient key={k} id={`g-${k}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor={c} stopOpacity={0.2} />
                                <stop offset="95%" stopColor={c} stopOpacity={0} />
                            </linearGradient>
                        ))}
                    </defs>
                    <XAxis dataKey="t" tick={{ fill: '#475569', fontSize: 10 }} tickLine={false} interval={14} />
                    <YAxis domain={[0, 100]} tick={{ fill: '#475569', fontSize: 10 }} tickLine={false}
                        tickFormatter={v => `${v}%`} />
                    <Tooltip content={<CustomTooltip />} />
                    <ReferenceLine y={90} stroke="rgba(255,68,68,0.3)" strokeDasharray="4 4" />
                    {[['lambda', '#00D4FF'], ['aws', '#F97316'], ['gcp', '#A78BFA']].map(([k, c]) => (
                        <Line key={k} type="monotoneX" dataKey={k} stroke={c} strokeWidth={2}
                            dot={false} activeDot={{ r: 4, fill: c, stroke: '#0A0B14', strokeWidth: 2 }} />
                    ))}
                </LineChart>
            </ResponsiveContainer>
        </div>
    )
}

/* ─── Cost Intelligence Panel ─────────────────────────────────────────── */
function CostPanel({ metrics }) {
    const [savings, setSavings] = useState(1247.80)
    useEffect(() => {
        const t = setInterval(() => setSavings(s => +(s + Math.random() * 0.12).toFixed(2)), 3000)
        return () => clearInterval(t)
    }, [])

    const providers = [
        { name: 'Lambda Labs', price: 1.99, color: '#00D4FF', selected: true },
        { name: 'CoreWeave', price: 1.82, color: '#7B2FFF' },
        { name: 'GCP Spot', price: 1.24, color: '#A78BFA' },
        { name: 'AWS OD', price: 4.10, color: '#F97316' },
        { name: 'Azure OD', price: 3.85, color: '#FB7185' },
    ]
    const maxPrice = Math.max(...providers.map(p => p.price))

    return (
        <div className="glass-card p-5">
            <div className="flex items-center gap-2 mb-4">
                <Sparkles size={16} className="text-amber-400" />
                <h3 className="font-semibold text-white text-sm">Cost Intelligence</h3>
            </div>

            {/* Big savings counter */}
            <div className="rounded-xl p-4 mb-4" style={{ background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.15)' }}>
                <p className="text-xs text-slate-400 mb-1">AI saved you today</p>
                <p className="text-3xl font-bold tabular-nums" style={{ color: '#00FF88', textShadow: '0 0 20px rgba(0,255,136,0.4)' }}>
                    ${savings.toFixed(2)}
                </p>
                <p className="text-xs text-slate-500 mt-1">vs AWS on-demand pricing for same workloads</p>
            </div>

            {/* Provider price bars */}
            <div className="space-y-2.5 mb-4">
                <p className="text-xs text-slate-500 uppercase tracking-wider mb-3">A100 80GB — Live Prices</p>
                {providers.map(p => (
                    <div key={p.name} className="flex items-center gap-3">
                        <span className="text-xs text-slate-400 w-24 truncate">{p.name}</span>
                        <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
                            <div className="h-full rounded-full transition-all duration-700"
                                style={{
                                    width: `${(p.price / maxPrice) * 100}%`,
                                    background: p.color,
                                    boxShadow: p.selected ? `0 0 8px ${p.color}` : 'none',
                                    opacity: p.selected ? 1 : 0.5,
                                }} />
                        </div>
                        <span className="text-xs font-mono font-semibold w-14 text-right"
                            style={{ color: p.selected ? p.color : '#64748b' }}>${p.price.toFixed(2)}/hr</span>
                    </div>
                ))}
            </div>

            {/* Opportunity alert */}
            <div className="rounded-xl p-3" style={{ background: 'rgba(255,184,0,0.08)', border: '1px solid rgba(255,184,0,0.2)' }}>
                <p className="text-xs font-semibold text-amber-400 mb-1">💡 Opportunity</p>
                <p className="text-xs text-slate-400">Switch 3 queued jobs to spot instances for ~$47 additional savings</p>
            </div>
        </div>
    )
}

/* ─── Main Dashboard ──────────────────────────────────────────────────── */
const sparkUtil = genSpark(24, 78, 20)
const sparkJobs = genSpark(24, 5, 4).map(d => ({ ...d, v: Math.round(d.v / 10) }))
const sparkSpend = genSpark(24, 40, 15)
const sparkSaved = genSpark(24, 60, 10).map((d, i) => ({ ...d, v: Math.round(10 + i * 0.8 + Math.random() * 3) }))

export default function Dashboard() {
    const metrics = useApi('/metrics')
    const agents = useApi('/agents/status')
    const [healthScore] = useState(97)

    return (
        <div className="space-y-5 animate-fade-in">
            {/* ── Top bar ── */}
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                    <h1 className="text-xl font-bold text-white">Mission Control</h1>
                    <p className="text-slate-500 text-xs mt-0.5">OrQuanta Agentic v1.0 — Real-time platform view</p>
                </div>
                <div className="flex items-center gap-4 flex-wrap">
                    <LiveClock />
                    <HealthRing score={healthScore} />
                </div>
            </div>

            {/* ── Hero metric cards ── */}
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                <HeroCard icon={Server} label="Active GPU Jobs" color="blue"
                    value={metrics?.total_active_jobs ?? 8}
                    sub={`${metrics?.queued_jobs ?? 3} queued`} trend={12}
                    sparkData={sparkJobs} />
                <HeroCard icon={Activity} label="GPU Utilization" color="green"
                    value={`${metrics?.platform_utilization_pct?.toFixed(0) ?? 81}%`}
                    sub="Avg across all instances" trend={5}
                    sparkData={sparkUtil} />
                <HeroCard icon={DollarSign} label="Today's Spend" color="amber"
                    value={`$${(metrics?.daily_spend_usd ?? 47.23).toFixed(2)}`}
                    sub="$152.77 remaining budget" trend={-8}
                    sparkData={sparkSpend} />
                <HeroCard icon={Zap} label="AI Cost Savings" color="purple"
                    value={`$${(metrics?.total_savings_usd ?? 1247.80).toFixed(0)}`}
                    sub="Total saved vs on-demand" trend={23}
                    sparkData={sparkSaved} />
            </div>

            {/* ── Charts row ── */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                <UtilChart />
                <CostPanel metrics={metrics} />
            </div>

            {/* ── World map + Agent feed ── */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <WorldMap />
                <AgentFeed />
            </div>

            {/* ── Agent status strip ── */}
            <div className="glass-card p-4">
                <div className="flex items-center gap-2 mb-3">
                    <Shield size={14} className="text-cyan-400" />
                    <span className="text-xs font-semibold text-white uppercase tracking-wider">5 Active Agents</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                    {Object.entries(AGENT_COLORS).slice(0, 5).map(([key, cfg]) => (
                        <div key={key} className="flex items-center gap-2 px-3 py-2 rounded-xl"
                            style={{ background: `${cfg.color}0A`, border: `1px solid ${cfg.color}20` }}>
                            <span className="text-sm">{cfg.icon}</span>
                            <div>
                                <p className="text-xs font-medium text-white">{cfg.label}</p>
                                <p className="text-xs" style={{ color: cfg.color }}>Active</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}
