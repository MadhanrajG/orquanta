import VeroStatus from "../components/VeroStatus.jsx"
import { useState, useEffect } from'react'
import {
 Activity, Server, DollarSign, Zap,
 Globe, Sparkles, Brain, Shield,
 BarChart2, ArrowUp, ArrowDown
} from'lucide-react'
import {
 AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
 LineChart, Line, ReferenceLine
} from'recharts'
import { useAuth } from'../App.jsx'

const API = import.meta.env.VITE_API_URL ||''

/* ─── Shared fetch hook — with AbortController and request timeout ── */
function useApi(endpoint, interval = 6000) {
 const { token } = useAuth()
 const [data, setData] = useState(null)
 useEffect(() => {
 let controller = new AbortController()
 const go = async () => {
 controller.abort()
 controller = new AbortController()
 try {
 const r = await fetch(`${API}${endpoint}`, {
 headers: { Authorization: `Bearer ${token}` },
 signal: AbortSignal.any
 ? AbortSignal.any([controller.signal, AbortSignal.timeout(8000)])
 : controller.signal,
 })
 if (r.ok) setData(await r.json())
 } catch (e) {
 if (e.name !== 'AbortError') { /* silent — stale data stays visible */ }
 }
 }
 go()
 const t = setInterval(go, interval)
 return () => { clearInterval(t); controller.abort() }
 }, [endpoint, token])
 return data
}

/* ─── Live UTC clock ──────────────────────────────────────────────────── */
function LiveClock() {
 const [now, setNow] = useState(new Date())
 useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t) }, [])
 const utcStr = now.toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
 return (
 <span className="font-mono text-xs text-slate-400 tabular-nums tracking-wide">{utcStr}</span>
 )
}

/* ─── Health Score Ring ───────────────────────────────────────────────── */
function HealthRing({ score = 97 }) {
 const r = 22, circ = 2 * Math.PI * r
 const dash = circ * (score / 100)
 const color = score >= 90 ?'#00FF88' : score >= 70 ?'#FFB800' :'#FF4444'
 return (
 <div className="flex items-center gap-3">
 <div className="relative w-14 h-14">
 <svg viewBox="0 0 56 56" className="rotate-[-90deg] w-full h-full">
 <circle cx="28" cy="28" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4" />
 <circle cx="28" cy="28" r={r} fill="none" stroke={color} strokeWidth="4"
 strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
 style={{ transition:'stroke-dasharray 1s ease', filter: `drop-shadow(0 0 6px ${color})` }} />
 </svg>
 <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-white">{score}</span>
 </div>
 <div>
 <div className="text-sm font-semibold text-white">System Health</div>
 <div className="text-xs" style={{ color }}>{score >= 90 ?'All Systems Optimal' : score >= 70 ?'Minor Issues' :'Action Required'}</div>
 </div>
 </div>
 )
}

/* ─── Sparkline mini chart ────────────────────────────────────────────── */
function Sparkline({ data, color ='#00D4FF' }) {
 return (
 <ResponsiveContainer width="100%" height={40}>
 <AreaChart data={data} margin={{ top: 2, bottom: 2 }}>
 <defs>
 <linearGradient id={`spark-${color.replace('#','')}`} x1="0" y1="0" x2="0" y2="1">
 <stop offset="5%" stopColor={color} stopOpacity={0.25} />
 <stop offset="95%" stopColor={color} stopOpacity={0} />
 </linearGradient>
 </defs>
 <Area type="monotone" dataKey="v" stroke={color} strokeWidth={1.5}
 fill={`url(#spark-${color.replace('#','')})`} dot={false} />
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
function HeroCard({ icon: Icon, label, value, sub, color, trend, sparkData }) {
 const glows = {
 blue:'rgba(0,212,255,0.15)',
 green:'rgba(0,255,136,0.12)',
 amber:'rgba(255,184,0,0.12)',
 purple:'rgba(123,47,255,0.15)',
 }
 const colors = {
 blue:'#00D4FF',
 green:'#00FF88',
 amber:'#FFB800',
 purple:'#7B2FFF',
 }
 const c = colors[color] || colors.blue
 const kpiClass = { blue:'kpi-cyan', green:'kpi-green', amber:'kpi-amber', purple:'kpi-violet' }[color] || 'kpi-cyan'
 return (
 <div className={`glass-card p-5 relative overflow-hidden group transition-all duration-300 hover:-translate-y-1 metric-card ${kpiClass}`}
 data-color={color === 'blue' ? 'cyan' : color === 'purple' ? 'violet' : color}
 style={{ boxShadow: `0 0 0 1px rgba(${color==='blue'?'0,212,255':color==='green'?'0,255,136':color==='amber'?'255,184,0':'123,47,255'},0.12), 0 8px 32px rgba(0,0,0,0.4)` }}>
 {/* glow corner */}
 <div className="absolute -top-10 -right-10 w-32 h-32 rounded-full blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"
 style={{ background: glows[color] }} />
 <div className="flex items-start justify-between mb-2">
 <div className="p-2 rounded-xl" style={{ background:`${c}18`, border:`1px solid ${c}30` }}>
 <Icon size={18} style={{ color: c }} />
 </div>
 {trend != null && (
 <span className={`flex items-center gap-0.5 text-xs font-semibold ${trend >= 0 ?'text-green-400':'text-red-400'}`}>
 {trend >= 0 ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
 {Math.abs(trend)}%
 </span>
 )}
 </div>
 <p className="text-2xl font-bold text-white mb-0.5 tabular-nums" style={{ textShadow:`0 0 20px ${c}60` }}>{value ?? '-'}</p>
 <p className="text-xs font-semibold" style={{ color:'var(--text-secondary)' }}>{label}</p>
 {sub && <p className="text-xs mt-0.5" style={{ color:'var(--text-muted)' }}>{sub}</p>}
 {sparkData && <div className="mt-3"><Sparkline data={sparkData} color={c} /></div>}
 </div>
 )
}

/* ─── GPU Fleet Overview ──────────────────────────────────────────────── */
const FLEET_REGIONS = [
  // Americas
  { id: 'lam-us1',  region: 'us-central-1',  provider: 'Lambda',     flag: '🇺🇸', gpus: 5, type: 'A100 80G', rate: 1.99, active: true,  util: 84 },
  { id: 'cw-us1',   region: 'ord1',           provider: 'CoreWeave',  flag: '🇺🇸', gpus: 2, type: 'A100 80G', rate: 1.82, active: true,  util: 71 },
  { id: 'lam-tx1',  region: 'us-tx-3',        provider: 'Lambda',     flag: '🇺🇸', gpus: 6, type: 'H100 SXM', rate: 2.49, active: true,  util: 91 },
  { id: 'aws-us1',  region: 'us-east-1',      provider: 'AWS',        flag: '🇺🇸', gpus: 0, type: 'A10G',     rate: 4.10, active: false, util: 0  },
  // Europe
  { id: 'gcp-eu1',  region: 'europe-west4',   provider: 'GCP',        flag: '🇳🇱', gpus: 3, type: 'A100 40G', rate: 2.21, active: true,  util: 67 },
  { id: 'run-eu1',  region: 'EU-SE-1',        provider: 'RunPod',     flag: '🇸🇪', gpus: 4, type: 'RTX 4090', rate: 0.74, active: true,  util: 55 },
  // Asia-Pacific
  { id: 'aws-ap1',  region: 'ap-south-1',     provider: 'AWS',        flag: '🇮🇳', gpus: 0, type: 'A100 80G', rate: 4.20, active: false, util: 0  },
  { id: 'vast-sg1', region: 'SG-1',           provider: 'Vast.ai',    flag: '🇸🇬', gpus: 2, type: 'RTX 3090', rate: 0.31, active: true,  util: 42 },
]

const PROVIDER_COLORS = {
  Lambda:    '#00D4FF',
  CoreWeave: '#A78BFA',
  AWS:       '#F97316',
  GCP:       '#34D399',
  RunPod:    '#FB923C',
  'Vast.ai': '#F472B6',
}

function GPUFleet() {
  const totalActive = FLEET_REGIONS.filter(r => r.active).reduce((a, r) => a + r.gpus, 0)
  const hourlyRate  = FLEET_REGIONS.filter(r => r.active).reduce((a, r) => a + r.gpus * r.rate, 0)

  const groups = [
    { label: '🌎 Americas', ids: ['lam-us1','cw-us1','lam-tx1','aws-us1'] },
    { label: '🌍 Europe',   ids: ['gcp-eu1','run-eu1'] },
    { label: '🌏 Asia-Pac', ids: ['aws-ap1','vast-sg1'] },
  ]

  return (
    <div className="glass-card p-5">
      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:16 }}>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <Globe size={16} style={{ color:'#00D4FF' }} />
          <span style={{ fontWeight:600, color:'#fff', fontSize:14 }}>Global GPU Fleet</span>
        </div>
        <div style={{ display:'flex', gap:16, alignItems:'center' }}>
          <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:12, color:'#00FF88', fontWeight:700 }}>
            {totalActive} GPUs active
          </span>
          <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:12, color:'#FFB800', fontWeight:700 }}>
            ${hourlyRate.toFixed(2)}/hr
          </span>
        </div>
      </div>

      {/* Region groups */}
      <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        {groups.map(group => {
          const regions = FLEET_REGIONS.filter(r => group.ids.includes(r.id))
          return (
            <div key={group.label}>
              <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.1em', textTransform:'uppercase', color:'var(--text-muted)', marginBottom:6, display:'flex', alignItems:'center', gap:6 }}>
                {group.label}
                <div style={{ flex:1, height:1, background:'var(--border)', borderRadius:999 }} />
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(200px,1fr))', gap:6 }}>
                {regions.map(r => {
                  const pc = PROVIDER_COLORS[r.provider] || '#8899aa'
                  return (
                    <div key={r.id} style={{
                      display:'flex', alignItems:'center', gap:10,
                      padding:'9px 12px', borderRadius:10,
                      background: r.active ? `${pc}08` : 'rgba(255,255,255,0.02)',
                      border: `1px solid ${r.active ? pc + '25' : 'rgba(255,255,255,0.06)'}`,
                      transition:'all 0.2s',
                      opacity: r.active ? 1 : 0.45,
                    }}>
                      {/* Status dot */}
                      <div style={{
                        width:8, height:8, borderRadius:'50%', flexShrink:0,
                        background: r.active ? '#00FF88' : '#475569',
                        boxShadow: r.active ? '0 0 6px #00FF88, 0 0 12px rgba(0,255,136,0.3)' : 'none',
                        animation: r.active ? 'live-pulse 2s ease-in-out infinite' : 'none',
                      }} />
                      {/* Info */}
                      <div style={{ flex:1, minWidth:0 }}>
                        <div style={{ display:'flex', alignItems:'center', gap:4, marginBottom:2 }}>
                          <span style={{ fontSize:10, color: pc, fontWeight:700 }}>{r.flag} {r.provider}</span>
                        </div>
                        <div style={{ fontSize:11, color:'var(--text-secondary)', fontWeight:500, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                          {r.region}
                        </div>
                        <div style={{ fontSize:10, color:'var(--text-muted)', marginTop:1 }}>{r.type}</div>
                      </div>
                      {/* GPU count + rate */}
                      <div style={{ textAlign:'right', flexShrink:0 }}>
                        <div style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:13, fontWeight:700, color: r.active ? '#fff' : 'var(--text-muted)' }}>
                          {r.active ? r.gpus : '—'}
                        </div>
                        <div style={{ fontSize:9, color:'var(--text-muted)' }}>{r.active ? 'GPUs' : 'offline'}</div>
                        {r.active && (
                          <div style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:9, color:'#FFB800', marginTop:1, fontWeight:600 }}>
                            ${r.rate}/hr
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      {/* Utilization footer */}
      <div style={{ marginTop:14, paddingTop:12, borderTop:'1px solid var(--border)', display:'flex', gap:8, flexWrap:'wrap' }}>
        {FLEET_REGIONS.filter(r => r.active).map(r => {
          const pc = PROVIDER_COLORS[r.provider] || '#8899aa'
          return (
            <div key={r.id} style={{ flex:'1 1 140px', minWidth:0 }}>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
                <span style={{ fontSize:9, color:'var(--text-muted)' }}>{r.region}</span>
                <span style={{ fontSize:9, fontWeight:700, fontFamily:"'JetBrains Mono',monospace", color: r.util > 85 ? '#F97316' : r.util > 70 ? '#FFB800' : '#00FF88' }}>{r.util}%</span>
              </div>
              <div style={{ height:3, background:'rgba(255,255,255,0.06)', borderRadius:999, overflow:'hidden' }}>
                <div style={{ height:'100%', width:`${r.util}%`, background: r.util > 85 ? '#F97316' : pc, borderRadius:999, transition:'width 1s ease' }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ─── Agent Activity Feed ─────────────────────────────────────────────── */
const AGENT_COLORS = {
 master_orchestrator: { color:'#00D4FF', icon:'', label:'Orchestrator' },
 scheduler_agent: { color:'#7B2FFF', icon:'', label:'Scheduler' },
 cost_optimizer_agent: { color:'#FFB800', icon:'', label:'Cost Optimizer' },
 healing_agent: { color:'#00FF88', icon:'', label:'Healing' },
 forecast_agent: { color:'#F472B6', icon:'', label:'Forecast' },
 audit_agent: { color:'#94A3B8', icon:'', label:'Audit' },
}

const DEMO_THOUGHTS = [
 { agent:'cost_optimizer_agent', msg:'Lambda Labs A100 @ $1.99/hr wins vs AWS $4.10/hr', time: 0 },
 { agent:'scheduler_agent', msg:'Job orq-7f2a queued - EDF priority: deadline in 4h', time: 1 },
 { agent:'healing_agent', msg:'All instances nominal. VRAM avg 71%. Temp 68 degreesC.', time: 2 },
 { agent:'master_orchestrator', msg:'Goal decomposed: 4 subtasks dispatched to agents.', time: 3 },
 { agent:'forecast_agent', msg:'GPU demand peak predicted in ~2h: pre-warming pool', time: 4 },
 { agent:'cost_optimizer_agent', msg:'Spot interruption risk 8% - acceptable, saving $23/hr', time: 5 },
 { agent:'audit_agent', msg:'HMAC batch #47 signed. 12 decisions logged, zero anomalies.', time: 6 },
 { agent:'healing_agent', msg:'VRAM at 94% on inst-3d9a prescaling memory...', time: 7 },
 { agent:'healing_agent', msg:'Memory prescaled. VRAM 94% 69%. No data loss.', time: 8 },
 { agent:'cost_optimizer_agent', msg:'Migrated 2 jobs from AWS to Lambda - saving $67.20/hr', time: 9 },
 { agent:'scheduler_agent', msg:'orq-9e1c completed. Cost: $12.40. Saved: $8.30 vs baseline.', time: 10 },
 { agent:'master_orchestrator', msg:'Platform health: 97/100. All agents responsive.', time: 11 },
]

function AgentFeed() {
 const { token } = useAuth()
 const [entries, setEntries] = useState(() =>
 DEMO_THOUGHTS.slice(0, 4).map((t, i) => ({ ...t, key: i, ts: Date.now() - (11 - i) * 4000 }))
 )
 const [isLive, setIsLive] = useState(false)

 useEffect(() => {
 // Try real WebSocket first; fall back to demo rotation if unavailable
 const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws'
 const wsUrl = `${wsProto}://${window.location.host}/ws/agent-stream?token=${token}`
 let ws = null
 let demoTimer = null
 let demoIdx = 4

 const startDemo = () => {
 demoTimer = setInterval(() => {
 const thought = DEMO_THOUGHTS[demoIdx % DEMO_THOUGHTS.length]
 setEntries(prev => [{ ...thought, key: Date.now(), ts: Date.now() }, ...prev.slice(0, 14)])
 demoIdx++
 }, 3000)
 }

 try {
 ws = new WebSocket(wsUrl)
 ws.onopen = () => setIsLive(true)
 ws.onmessage = (e) => {
 try {
 const msg = JSON.parse(e.data)
 if (msg.agent && msg.message) {
 setEntries(prev => [
 { agent: msg.agent, msg: msg.message, key: Date.now(), ts: Date.now() },
 ...prev.slice(0, 14),
 ])
 }
 } catch { /* ignore malformed frames */ }
 }
 ws.onerror = () => { setIsLive(false); startDemo() }
 ws.onclose = () => { setIsLive(false); startDemo() }
 } catch { startDemo() }

 return () => {
 if (ws) ws.close()
 if (demoTimer) clearInterval(demoTimer)
 }
 }, [token])

 return (
 <div className="glass-card p-5 flex flex-col" style={{ minHeight: 320 }}>
 <div className="flex items-center justify-between mb-4">
 <div className="flex items-center gap-2">
 <Brain size={16} className="text-cyan-400" />
 <h3 className="font-semibold text-white text-sm">Agent Activity Feed</h3>
 </div>
 <div className="flex items-center gap-1.5">
 <span className={`w-2 h-2 rounded-full animate-pulse ${isLive ? 'bg-green-400' : 'bg-amber-400'}`} />
 <span className={`text-xs ${isLive ? 'text-green-400' : 'text-amber-400'}`}>
 {isLive ? 'Live' : 'Demo'}
 </span>
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
 background: i === 0 ? `${cfg.color}12` :'rgba(255,255,255,0.02)',
 border: i === 0 ? `1px solid ${cfg.color}20` :'1px solid transparent',
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
 <h3 className="font-semibold text-white text-sm">GPU Utilization - Live Multi-Provider</h3>
 </div>
 <div className="flex gap-1">
 {['1h','6h','24h','7d'].map(r => (
 <button key={r} onClick={() => setRange(r)}
 className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all"
 style={range === r
 ? { background:'rgba(0,212,255,0.15)', color:'#00D4FF', border:'1px solid rgba(0,212,255,0.3)' }
 : { background:'rgba(255,255,255,0.04)', color:'#64748b', border:'1px solid transparent' }
 }>{r}</button>
 ))}
 </div>
 </div>
 <div className="flex gap-4 mb-3">
 {[['lambda','#00D4FF','Lambda Labs'], ['aws','#F97316','AWS'], ['gcp','#A78BFA','GCP']].map(([k, c, l]) => (
 <div key={k} className="flex items-center gap-1.5">
 <div className="w-3 h-0.5 rounded" style={{ background: c }} />
 <span className="text-xs text-slate-400">{l}</span>
 </div>
 ))}
 </div>
 <ResponsiveContainer width="100%" height={180}>
 <LineChart data={data} margin={{ left: -20, right: 8 }}>
 <defs>
 {[['lambda','#00D4FF'], ['aws','#F97316'], ['gcp','#A78BFA']].map(([k, c]) => (
 <linearGradient key={k} id={`g-${k}`} x1="0" y1="0" x2="0" y2="1">
 <stop offset="5%" stopColor={c} stopOpacity={0.2} />
 <stop offset="95%" stopColor={c} stopOpacity={0} />
 </linearGradient>
 ))}
 </defs>
 <XAxis dataKey="t" tick={{ fill:'#475569', fontSize: 10 }} tickLine={false} interval={14} />
 <YAxis domain={[0, 100]} tick={{ fill:'#475569', fontSize: 10 }} tickLine={false}
 tickFormatter={v => `${v}%`} />
 <Tooltip content={<CustomTooltip />} />
 <ReferenceLine y={90} stroke="rgba(255,68,68,0.3)" strokeDasharray="4 4" />
 {[['lambda','#00D4FF'], ['aws','#F97316'], ['gcp','#A78BFA']].map(([k, c]) => (
 <Line key={k} type="monotoneX" dataKey={k} stroke={c} strokeWidth={2}
 dot={false} activeDot={{ r: 4, fill: c, stroke:'#0A0B14', strokeWidth: 2 }} />
 ))}
 </LineChart>
 </ResponsiveContainer>
 </div>
 )
}

/* ─── Cost Intelligence Panel ─────────────────────────────────────────── */
function CostPanel() {
 const [savings, setSavings] = useState(1247.80)
 useEffect(() => {
 const t = setInterval(() => setSavings(s => +(s + Math.random() * 0.12).toFixed(2)), 3000)
 return () => clearInterval(t)
 }, [])

 const providers = [
 { name:'Lambda Labs', price: 1.99, color:'#00D4FF', selected: true },
 { name:'CoreWeave', price: 1.82, color:'#7B2FFF' },
 { name:'GCP Spot', price: 1.24, color:'#A78BFA' },
 { name:'AWS OD', price: 4.10, color:'#F97316' },
 { name:'Azure OD', price: 3.85, color:'#FB7185' },
 ]
 const maxPrice = Math.max(...providers.map(p => p.price))

 return (
 <div className="glass-card p-5">
 <div className="flex items-center gap-2 mb-4">
 <Sparkles size={16} className="text-amber-400" />
 <h3 className="font-semibold text-white text-sm">Cost Intelligence</h3>
 </div>

 {/* Big savings counter */}
 <div className="rounded-xl p-4 mb-4" style={{ background:'rgba(0,255,136,0.06)', border:'1px solid rgba(0,255,136,0.15)' }}>
 <p className="text-xs text-slate-400 mb-1">AI saved you today</p>
 <p className="text-3xl font-bold tabular-nums" style={{ color:'#00FF88', textShadow:'0 0 20px rgba(0,255,136,0.4)' }}>
 ${savings.toFixed(2)}
 </p>
 <p className="text-xs text-slate-500 mt-1">vs AWS on-demand pricing for same workloads</p>
 </div>

 {/* Provider price bars */}
 <div className="space-y-2.5 mb-4">
 <p className="text-xs text-slate-500 uppercase tracking-wider mb-3">A100 80GB - Live Prices</p>
 {providers.map(p => (
 <div key={p.name} className="flex items-center gap-3">
 <span className="text-xs text-slate-400 w-24 truncate">{p.name}</span>
 <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
 <div className="h-full rounded-full transition-all duration-700"
 style={{
 width: `${(p.price / maxPrice) * 100}%`,
 background: p.color,
 boxShadow: p.selected ? `0 0 8px ${p.color}` :'none',
 opacity: p.selected ? 1 : 0.5,
 }} />
 </div>
 <span className="text-xs font-mono font-semibold w-14 text-right"
 style={{ color: p.selected ? p.color :'#64748b' }}>${p.price.toFixed(2)}/hr</span>
 </div>
 ))}
 </div>

 {/* Opportunity alert */}
 <div className="rounded-xl p-3" style={{ background:'rgba(255,184,0,0.08)', border:'1px solid rgba(255,184,0,0.2)' }}>
 <p className="text-xs font-semibold text-amber-400 mb-1"> Opportunity</p>
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
 const metrics = useApi('/health')
 const [healthScore] = useState(97)

 return (
 <div className="space-y-5 animate-fade-in">
 {/* ── Vero meta-agent status ── */}
 <VeroStatus />

 {/* ── Hero savings bar ── */}
 <div className="savings-hero">
 <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
 <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
 <div className="savings-hero-value">$127.40</div>
 <div>
 <div className="savings-hero-label">Saved This Month</div>
 <div style={{ fontSize: 11, color: '#64748b', marginTop: 1 }}>vs AWS on-demand pricing</div>
 </div>
 </div>
 </div>
 <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginLeft: 'auto' }}>
 <span className="savings-hero-pill">⚡ 67% cheaper than AWS</span>
 <span className="savings-hero-pill">🧠 5 agents active</span>
 <span className="savings-hero-pill">✅ 3 jobs auto-healed</span>
 <span className="savings-hero-pill">🟢 All systems optimal</span>
 </div>
 </div>

 {/* ── Top bar ── */}
 <div className="flex items-center justify-between flex-wrap gap-3">
 <div>
 <h1 className="text-xl font-bold text-white" style={{ letterSpacing: '-0.02em' }}>Mission Control</h1>
 <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
 <span className="purpose-tag">🚀 GPU Cloud Orchestration · AI-Automated Cost Optimization</span>
 </div>
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
 <CostPanel />
 </div>

 {/* ── GPU Fleet + Agent feed ── */}
 <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
 <GPUFleet />
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
