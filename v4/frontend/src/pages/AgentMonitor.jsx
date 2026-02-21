import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

/* ─── Agent node positions (SVG viewBox 0 0 600 400) ─────────────────── */
const AGENT_NODES = [
    { key: 'master_orchestrator', label: 'OrMind', sub: 'Orchestrator', x: 300, y: 180, icon: '🧠', color: '#00D4FF', size: 46 },
    { key: 'scheduler_agent', label: 'Scheduler', sub: 'EDF Queue', x: 140, y: 100, icon: '📅', color: '#7B2FFF', size: 36 },
    { key: 'cost_optimizer_agent', label: 'Cost AI', sub: 'Optimizer', x: 460, y: 100, icon: '💸', color: '#FFB800', size: 36 },
    { key: 'healing_agent', label: 'Healing', sub: 'Self-Repair', x: 120, y: 290, icon: '🔧', color: '#00FF88', size: 36 },
    { key: 'forecast_agent', label: 'Forecast', sub: 'Demand AI', x: 480, y: 290, icon: '📊', color: '#F472B6', size: 36 },
]

const EDGES = [
    ['master_orchestrator', 'scheduler_agent'],
    ['master_orchestrator', 'cost_optimizer_agent'],
    ['master_orchestrator', 'healing_agent'],
    ['master_orchestrator', 'forecast_agent'],
]

/* ─── Pulse line component ─────────────────────────────────────────────── */
function PulseLine({ x1, y1, x2, y2, color, active }) {
    const len = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    return (
        <g>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={`${color}20`} strokeWidth={active ? 2 : 1} />
            {active && (
                <circle r={3} fill={color} style={{ filter: `drop-shadow(0 0 4px ${color})` }}>
                    <animateMotion dur="1.2s" repeatCount="indefinite">
                        <mpath>
                            <path d={`M${x1},${y1} L${x2},${y2}`} />
                        </mpath>
                    </animateMotion>
                </circle>
            )}
        </g>
    )
}

/* ─── Agent thought stream ─────────────────────────────────────────────── */
const ALL_THOUGHTS = {
    master_orchestrator: [
        'Goal received: "Fine-tune Mistral 7B, budget $50"',
        'Decomposing into 4 subtasks…',
        'Dispatching to Cost Optimizer and Scheduler',
        'Platform health score: 97/100',
        'All agents responsive. Orchestration nominal.',
    ],
    scheduler_agent: [
        'Queue depth: 3 jobs pending',
        'Applying Earliest-Deadline-First ordering',
        'orq-7f2a promoted: deadline in 2h',
        'Spot interruption budget: $12 allocated',
        'Next job provisioning in 18 seconds',
    ],
    cost_optimizer_agent: [
        'Polling 5 providers for A100 prices…',
        'Lambda Labs $1.99/hr (best) vs AWS $4.10/hr',
        'Spot risk on Lambda: 8% — acceptable',
        'Routing orq-7f2a to Lambda Labs us-tx-3',
        'Cumulative savings today: $127.40',
    ],
    healing_agent: [
        'All instances nominal. 1Hz telemetry active.',
        'VRAM rolling average: 71.2% across 8 instances',
        'No anomalies in 60-sample Z-score window',
        'Temperature: 68°C avg — within thermal budget',
        'Last heal: 12 minutes ago (VRAM prescale, 8.3s)',
    ],
    forecast_agent: [
        'Training demand pattern: 9AM–2PM peak',
        'Predicting 40% utilization spike in ~2 hours',
        'Recommendation: pre-warm 2 additional A100s',
        'Monthly spend forecast: $1,240 (↓23% vs last month)',
        'Model: gradient boosted on 90 days of history',
    ],
}

function ThoughtStream({ agentKey, color }) {
    const thoughts = ALL_THOUGHTS[agentKey] || []
    const [idx, setIdx] = useState(0)
    const [visible, setVisible] = useState([thoughts[0]])

    useEffect(() => {
        const t = setInterval(() => {
            setIdx(i => {
                const next = (i + 1) % thoughts.length
                setVisible(prev => [thoughts[next], ...prev.slice(0, 4)])
                return next
            })
        }, 2800)
        return () => clearInterval(t)
    }, [agentKey])

    return (
        <div className="space-y-1.5 max-h-40 overflow-hidden">
            {visible.map((thought, i) => (
                <div key={thought} className="flex items-start gap-2 transition-all duration-500"
                    style={{ opacity: Math.max(0.2, 1 - i * 0.22) }}>
                    <span className="text-xs mt-px" style={{ color }}>→</span>
                    <p className="text-xs text-slate-400 leading-relaxed">{thought}</p>
                </div>
            ))}
        </div>
    )
}

/* ─── Main Agent Monitor ───────────────────────────────────────────────── */
export default function AgentMonitor() {
    const [activeNode, setActiveNode] = useState('master_orchestrator')
    const [activeEdges, setActiveEdges] = useState([])
    const agents = useApi('/agents/status')

    // Animate random edge activations
    useEffect(() => {
        const t = setInterval(() => {
            const edge = EDGES[Math.floor(Math.random() * EDGES.length)]
            setActiveEdges([edge[0] + '-' + edge[1]])
            setTimeout(() => setActiveEdges([]), 800)
        }, 1200)
        return () => clearInterval(t)
    }, [])

    const selectedNode = AGENT_NODES.find(n => n.key === activeNode)

    return (
        <div className="space-y-5 animate-fade-in">
            <div>
                <h1 className="text-xl font-bold text-white">Agent Monitor</h1>
                <p className="text-slate-500 text-sm mt-1">Real-time neural network view of 5 active OrQuanta agents</p>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                {/* ── Neural Network SVG ── */}
                <div className="xl:col-span-2 glass-card p-5">
                    <div className="flex items-center justify-between mb-4">
                        <span className="text-sm font-semibold text-white">Agent Network</span>
                        <div className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                            <span className="text-xs text-green-400">5 agents active</span>
                        </div>
                    </div>
                    <div className="relative" style={{ paddingBottom: '65%' }}>
                        <svg viewBox="0 0 600 400" className="absolute inset-0 w-full h-full">
                            {/* Background grid */}
                            <defs>
                                <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
                                    <path d="M 30 0 L 0 0 0 30" fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
                                </pattern>
                            </defs>
                            <rect width="600" height="400" fill="url(#grid)" />

                            {/* Edges */}
                            {EDGES.map(([from, to]) => {
                                const a = AGENT_NODES.find(n => n.key === from)
                                const b = AGENT_NODES.find(n => n.key === to)
                                const isActive = activeEdges.includes(`${from}-${to}`)
                                return <PulseLine key={`${from}-${to}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                                    color={a.color} active={isActive} />
                            })}

                            {/* Agent nodes */}
                            {AGENT_NODES.map(node => {
                                const isSelected = node.key === activeNode
                                return (
                                    <g key={node.key} onClick={() => setActiveNode(node.key)}
                                        className="cursor-pointer" style={{ transition: 'all 0.3s' }}>
                                        {/* Outer glow ring */}
                                        {isSelected && (
                                            <circle cx={node.x} cy={node.y} r={node.size + 10}
                                                fill="none" stroke={node.color} strokeWidth={1.5} opacity={0.4}>
                                                <animate attributeName="r" values={`${node.size + 8};${node.size + 14};${node.size + 8}`} dur="2s" repeatCount="indefinite" />
                                                <animate attributeName="opacity" values="0.4;0.1;0.4" dur="2s" repeatCount="indefinite" />
                                            </circle>
                                        )}
                                        {/* Main circle */}
                                        <circle cx={node.x} cy={node.y} r={node.size}
                                            fill={`${node.color}15`}
                                            stroke={isSelected ? node.color : `${node.color}40`}
                                            strokeWidth={isSelected ? 2 : 1}
                                            style={{ filter: isSelected ? `drop-shadow(0 0 12px ${node.color})` : 'none' }} />
                                        {/* Icon */}
                                        <text x={node.x} y={node.y - 4} textAnchor="middle" dominantBaseline="middle"
                                            fontSize={node.key === 'master_orchestrator' ? 22 : 18}>
                                            {node.icon}
                                        </text>
                                        {/* Label */}
                                        <text x={node.x} y={node.y + node.size + 14} textAnchor="middle"
                                            fill={isSelected ? 'white' : '#64748b'} fontSize={10} fontWeight={isSelected ? 600 : 400}
                                            fontFamily="Inter, sans-serif">
                                            {node.label}
                                        </text>
                                        <text x={node.x} y={node.y + node.size + 26} textAnchor="middle"
                                            fill="#374151" fontSize={8.5} fontFamily="Inter, sans-serif">
                                            {node.sub}
                                        </text>
                                        {/* Pulse dot */}
                                        <circle cx={node.x + node.size - 6} cy={node.y - node.size + 6} r={4} fill="#00FF88">
                                            <animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite" />
                                        </circle>
                                    </g>
                                )
                            })}
                        </svg>
                    </div>
                    <p className="text-xs text-center text-slate-600 mt-2">Click any agent node to see live reasoning</p>
                </div>

                {/* ── Agent detail panel ── */}
                <div className="flex flex-col gap-4">
                    {selectedNode && (
                        <div className="glass-card p-5 flex-1"
                            style={{ border: `1px solid ${selectedNode.color}20` }}>
                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl"
                                    style={{ background: `${selectedNode.color}15`, border: `1px solid ${selectedNode.color}30` }}>
                                    {selectedNode.icon}
                                </div>
                                <div>
                                    <div className="font-semibold text-white">{selectedNode.label}</div>
                                    <div className="text-xs" style={{ color: selectedNode.color }}>{selectedNode.sub} · Active</div>
                                </div>
                            </div>
                            <div className="mb-3">
                                <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">Live Reasoning</div>
                                <ThoughtStream agentKey={activeNode} color={selectedNode.color} />
                            </div>
                            <div className="grid grid-cols-2 gap-2 mt-4">
                                {[
                                    { label: 'Decisions/hr', value: '142' },
                                    { label: 'Latency', value: '12ms' },
                                    { label: 'Accuracy', value: '99.1%' },
                                    { label: 'Uptime', value: '99.97%' },
                                ].map(stat => (
                                    <div key={stat.label} className="rounded-lg p-2.5 text-center"
                                        style={{ background: `${selectedNode.color}08`, border: `1px solid ${selectedNode.color}15` }}>
                                        <div className="text-sm font-bold text-white">{stat.value}</div>
                                        <div className="text-xs text-slate-500">{stat.label}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* All agents strip */}
                    <div className="glass-card p-4">
                        <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">All Agents</div>
                        <div className="space-y-2">
                            {AGENT_NODES.map(node => (
                                <button key={node.key} onClick={() => setActiveNode(node.key)}
                                    className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-left transition-all hover:bg-white/5"
                                    style={{
                                        background: activeNode === node.key ? `${node.color}0F` : 'transparent',
                                        border: `1px solid ${activeNode === node.key ? node.color + '25' : 'transparent'}`,
                                    }}>
                                    <span className="text-sm">{node.icon}</span>
                                    <span className="text-xs font-medium flex-1"
                                        style={{ color: activeNode === node.key ? 'white' : '#94a3b8' }}>{node.label}</span>
                                    <div className="flex items-center gap-1">
                                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: node.color, boxShadow: `0 0 4px ${node.color}` }} />
                                        <span className="text-xs" style={{ color: node.color }}>Active</span>
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}

/* ─── Local hook ─────────────────────────────────────────────────────── */
import { useContext } from 'react'
import { AuthContext } from '../App.jsx'
function useApi(endpoint) {
    const { token } = useContext(AuthContext)
    const [data, setData] = useState(null)
    useEffect(() => {
        const go = async () => {
            try {
                const r = await fetch(`${API}${endpoint}`, { headers: { Authorization: `Bearer ${token}` } })
                if (r.ok) setData(await r.json())
            } catch { }
        }
        go()
        const t = setInterval(go, 8000)
        return () => clearInterval(t)
    }, [endpoint, token])
    return data
}
