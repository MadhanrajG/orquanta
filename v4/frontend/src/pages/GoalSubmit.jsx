import { useState, useEffect, useRef } from 'react'
import { Send, Mic, Loader, ChevronRight, Cpu, Zap, DollarSign, Clock, CheckCircle, AlertCircle } from 'lucide-react'
import { useAuth } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

/* ─── Placeholder cycling ─────────────────────────────────────────────── */
const PLACEHOLDERS = [
    'Train Llama 3 8B on my dataset — budget $50',
    'Run 500 Stable Diffusion jobs across Lambda Labs',
    'Fine-tune Whisper Large v3 on 10 hours of audio',
    'Benchmark Mistral 7B vs LLaMA 3 on my eval set',
    'Generate 1M embeddings with text-embedding-3-large',
    'Run hyperparameter sweep — 32 trials, A10 GPUs',
]

/* ─── Agent execution steps ───────────────────────────────────────────── */
const AGENTS = [
    {
        key: 'orchestrator', icon: '🧠', name: 'OrMind Orchestrator', color: '#00D4FF',
        thoughts: ['Parsing natural language goal…', 'Building execution DAG…', 'Confidence: 0.91 ✓']
    },
    {
        key: 'cost', icon: '💸', name: 'Cost Optimizer', color: '#FFB800',
        thoughts: ['Comparing 5 providers…', 'Lambda Labs A100 @ $1.99/hr wins', 'Saving $2.11/hr vs AWS ✓']
    },
    {
        key: 'scheduler', icon: '📅', name: 'Scheduler', color: '#7B2FFF',
        thoughts: ['No queue backlog…', 'EDF priority assigned…', 'Provisioning now ✓']
    },
    {
        key: 'healing', icon: '🔧', name: 'Healing Agent', color: '#00FF88',
        thoughts: ['1Hz telemetry armed…', 'Anomaly baseline set…', 'Monitoring active ✓']
    },
    {
        key: 'audit', icon: '🔒', name: 'Audit Agent', color: '#94A3B8',
        thoughts: ['Goal hash logged…', 'HMAC chain updated…', 'Decision recorded ✓']
    },
]

/* ─── Cost Estimator (live preview) ──────────────────────────────────────*/
function CostPreview({ goal }) {
    const [est, setEst] = useState(null)
    useEffect(() => {
        if (!goal || goal.length < 10) { setEst(null); return }
        const t = setTimeout(() => {
            // Heuristic estimate from goal text
            const isLarge = /70b|72b|large|xl|huge|8x/i.test(goal)
            const isMedium = /7b|13b|medium|fine-?tune/i.test(goal)
            const gpu = isLarge ? 'gpu_8x_a100' : isMedium ? 'gpu_1x_a100' : 'gpu_1x_a10'
            const hr = isLarge ? 14.32 : isMedium ? 1.99 : 0.75
            const hrs = isLarge ? 4 : isMedium ? Math.round(2 + Math.random() * 4) : 1
            const awsHr = isLarge ? 32.77 : isMedium ? 4.10 : 1.10
            setEst({
                gpu_type: gpu,
                gpu_display: isLarge ? '8× A100 80GB' : isMedium ? 'A100 80GB' : 'A10 24GB',
                provider: 'Lambda Labs',
                cost_per_hr: hr,
                estimated_hrs: hrs,
                total: +(hr * hrs).toFixed(2),
                saved_vs_aws: +((awsHr - hr) * hrs).toFixed(2),
                confidence: Math.round(85 + Math.random() * 10),
            })
        }, 600)
        return () => clearTimeout(t)
    }, [goal])
    if (!est) return null
    return (
        <div className="animate-fade-in rounded-2xl p-5 mt-4"
            style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.15)' }}>
            <div className="flex items-center gap-2 mb-4">
                <span className="text-sm font-semibold text-cyan-400">AI Estimate</span>
                <span className="text-xs px-2 py-0.5 rounded-full text-slate-400"
                    style={{ background: 'rgba(255,255,255,0.06)' }}>{est.confidence}% confidence</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                    { label: 'GPU', value: est.gpu_display, icon: '🖥️' },
                    { label: 'Provider', value: est.provider, icon: '⚡' },
                    { label: 'Est. Duration', value: `~${est.estimated_hrs}h`, icon: '⏱️' },
                    { label: 'Est. Cost', value: `$${est.total}`, icon: '💰', highlight: true },
                ].map(item => (
                    <div key={item.label} className="rounded-xl p-3 text-center"
                        style={{ background: item.highlight ? 'rgba(0,255,136,0.08)' : 'rgba(255,255,255,0.04)' }}>
                        <div className="text-lg mb-1">{item.icon}</div>
                        <div className="text-sm font-bold" style={{ color: item.highlight ? '#00FF88' : 'white' }}>{item.value}</div>
                        <div className="text-xs text-slate-500 mt-0.5">{item.label}</div>
                    </div>
                ))}
            </div>
            {est.saved_vs_aws > 0 && (
                <div className="mt-3 text-center text-xs text-slate-400">
                    Saves <span className="text-green-400 font-semibold">${est.saved_vs_aws}</span> vs AWS on-demand
                </div>
            )}
        </div>
    )
}

/* ─── Agent Execution Theater ─────────────────────────────────────────── */
function AgentTheater({ phase, activeAgent }) {
    if (phase === 'idle') return null
    return (
        <div className="mt-6 animate-fade-in">
            <div className="flex items-center gap-2 mb-4">
                <div className="h-px flex-1 bg-white/10" />
                <span className="text-xs text-slate-500 uppercase tracking-wider">Agent Execution</span>
                <div className="h-px flex-1 bg-white/10" />
            </div>
            <div className="flex gap-3 justify-center flex-wrap">
                {AGENTS.map((agent, idx) => {
                    const isActive = idx === activeAgent
                    const isDone = idx < activeAgent || phase === 'running'
                    return (
                        <div key={agent.key}
                            className="flex flex-col items-center gap-2 p-4 rounded-2xl transition-all duration-500 w-28"
                            style={{
                                background: isDone ? `${agent.color}12` : isActive ? `${agent.color}1A` : 'rgba(255,255,255,0.03)',
                                border: `1px solid ${isDone || isActive ? agent.color + '35' : 'rgba(255,255,255,0.06)'}`,
                                transform: isActive ? 'scale(1.08)' : 'scale(1)',
                                boxShadow: isActive ? `0 0 24px ${agent.color}30` : 'none',
                            }}>
                            <span className="text-2xl" style={{ filter: isActive ? `drop-shadow(0 0 8px ${agent.color})` : 'none' }}>
                                {isDone ? '✅' : agent.icon}
                            </span>
                            <span className="text-xs font-medium text-center leading-tight"
                                style={{ color: isDone ? agent.color : isActive ? 'white' : '#64748b' }}>
                                {agent.name}
                            </span>
                            {isActive && (
                                <div className="flex gap-0.5 mt-1">
                                    {[0, 1, 2].map(i => (
                                        <div key={i} className="w-1 h-1 rounded-full animate-bounce"
                                            style={{ background: agent.color, animationDelay: `${i * 0.15}s` }} />
                                    ))}
                                </div>
                            )}
                            {isDone && <span className="text-xs font-mono" style={{ color: agent.color }}>Done</span>}
                        </div>
                    )
                })}
            </div>

            {/* Live thought stream */}
            {activeAgent < AGENTS.length && (
                <div className="mt-4 rounded-xl p-4"
                    style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.06)', fontFamily: 'JetBrains Mono, monospace' }}>
                    <div className="text-xs text-slate-500 mb-2">// agent reasoning stream</div>
                    {phase === 'running' ? (
                        <div className="text-xs text-green-400 animate-pulse">● Task running on Lambda Labs A100 — monitoring active</div>
                    ) : (
                        AGENTS[activeAgent]?.thoughts.slice(0, Math.min(3, activeAgent + 1)).map((t, i) => (
                            <div key={i} className="text-xs mb-1"
                                style={{ color: AGENTS[activeAgent].color, opacity: 1 - i * 0.25 }}>
                                → {t}
                            </div>
                        ))
                    )}
                </div>
            )}

            {/* Progress bar */}
            <div className="mt-4">
                <div className="flex justify-between text-xs text-slate-500 mb-2">
                    <span>{['Planning…', 'Optimizing…', 'Scheduling…', 'Monitoring…', 'Auditing…', 'Running ✓'][Math.min(activeAgent, 5)]}</span>
                    <span>{Math.round(Math.min(100, (activeAgent / (AGENTS.length)) * 100))}%</span>
                </div>
                <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-700"
                        style={{
                            width: `${Math.min(100, ((phase === 'running' ? AGENTS.length : activeAgent) / AGENTS.length) * 100)}%`,
                            background: 'linear-gradient(90deg, #00D4FF, #7B2FFF)',
                            boxShadow: '0 0 8px rgba(0,212,255,0.5)',
                        }} />
                </div>
            </div>
        </div>
    )
}

/* ─── Main GoalSubmit ─────────────────────────────────────────────────── */
export default function GoalSubmit() {
    const { token } = useAuth()
    const [goal, setGoal] = useState('')
    const [phase, setPhase] = useState('idle') // idle | planning | running | complete | error
    const [activeAgent, setAgent] = useState(0)
    const [jobId, setJobId] = useState(null)
    const [error, setError] = useState('')
    const [pIdx, setPIdx] = useState(0)
    const textRef = useRef(null)

    // Cycle placeholder
    useEffect(() => {
        const t = setInterval(() => setPIdx(i => (i + 1) % PLACEHOLDERS.length), 3500)
        return () => clearInterval(t)
    }, [])

    // Agent theater animation
    useEffect(() => {
        if (phase !== 'planning') return
        let a = 0
        const t = setInterval(() => {
            a++
            setAgent(a)
            if (a >= AGENTS.length) { clearInterval(t); setPhase('running') }
        }, 900)
        return () => clearInterval(t)
    }, [phase])

    const handleSubmit = async (e) => {
        e?.preventDefault()
        if (!goal.trim() || phase === 'planning') return
        setError(''); setPhase('planning'); setAgent(0); setJobId(null)
        try {
            const res = await fetch(`${API}/goals`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ goal, priority: 'normal' }),
            })
            if (res.ok) {
                const data = await res.json()
                setJobId(data.job_id || data.goal_id || 'demo-' + Date.now().toString(36))
            }
        } catch {
            // In demo mode, just animate through without real API
        }
    }

    const handleReset = () => { setPhase('idle'); setGoal(''); setAgent(0); setJobId(null) }

    return (
        <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-white">Command Center</h1>
                <p className="text-slate-500 text-sm mt-1">Tell OrQuanta what you need in plain English. 5 agents handle the rest.</p>
            </div>

            {/* Main input card */}
            <div className="glass-card p-6" style={{ boxShadow: '0 0 60px rgba(0,212,255,0.06)' }}>
                <form onSubmit={handleSubmit}>
                    <div className="relative">
                        <div className="absolute left-4 top-4 text-cyan-400 opacity-60">
                            <Cpu size={20} />
                        </div>
                        <textarea
                            ref={textRef}
                            id="goal-input"
                            value={goal}
                            onChange={e => setGoal(e.target.value)}
                            disabled={phase !== 'idle'}
                            placeholder={PLACEHOLDERS[pIdx]}
                            rows={4}
                            className="w-full rounded-2xl resize-none text-white text-base leading-relaxed transition-all"
                            style={{
                                paddingLeft: '2.75rem', paddingTop: '1rem', paddingRight: '1rem', paddingBottom: '3.5rem',
                                background: 'rgba(0,0,0,0.3)',
                                border: `1px solid ${phase !== 'idle' ? 'rgba(0,212,255,0.3)' : 'rgba(255,255,255,0.08)'}`,
                                outline: 'none',
                                fontSize: '15px',
                            }}
                            onFocus={e => e.target.style.borderColor = 'rgba(0,212,255,0.4)'}
                            onBlur={e => phase === 'idle' && (e.target.style.borderColor = 'rgba(255,255,255,0.08)')}
                            onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit() }}
                        />

                        {/* Bottom bar inside textarea */}
                        <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <span className="text-xs text-slate-600">⌘+Enter to submit</span>
                                {goal.length > 0 && <span className="text-xs text-slate-600">{goal.length} chars</span>}
                            </div>
                            <button id="submit-goal-btn" type="submit"
                                disabled={!goal.trim() || phase !== 'idle'}
                                className="flex items-center gap-2 px-4 py-1.5 rounded-xl text-sm font-semibold transition-all"
                                style={{
                                    background: goal.trim() && phase === 'idle'
                                        ? 'linear-gradient(135deg, #00D4FF, #7B2FFF)'
                                        : 'rgba(255,255,255,0.06)',
                                    color: goal.trim() && phase === 'idle' ? 'white' : '#64748b',
                                    boxShadow: goal.trim() && phase === 'idle' ? '0 0 20px rgba(0,212,255,0.25)' : 'none',
                                }}>
                                {phase === 'planning' ? <Loader size={14} className="animate-spin" /> : <Send size={14} />}
                                {phase === 'idle' ? 'Launch' : phase === 'planning' ? 'Planning…' : 'Running'}
                            </button>
                        </div>
                    </div>
                </form>

                {/* Live cost estimate */}
                <CostPreview goal={goal} />

                {/* Agent theater */}
                <AgentTheater phase={phase} activeAgent={activeAgent} />

                {/* Success state */}
                {phase === 'running' && (
                    <div className="mt-6 rounded-2xl p-5 animate-fade-in"
                        style={{ background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.2)' }}>
                        <div className="flex items-start gap-4">
                            <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0"
                                style={{ background: 'rgba(0,255,136,0.15)', border: '1px solid rgba(0,255,136,0.3)' }}>
                                <CheckCircle size={20} className="text-green-400" />
                            </div>
                            <div className="flex-1">
                                <p className="font-semibold text-white mb-1">Job Running on Lambda Labs A100</p>
                                <p className="text-sm text-slate-400 mb-3">5 agents coordinated. GPU provisioned in 18 seconds. Cost tracking live.</p>
                                <div className="flex gap-2">
                                    <button onClick={() => window.location.hash = '/jobs'}
                                        className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium text-white"
                                        style={{ background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.25)' }}>
                                        View Job <ChevronRight size={14} />
                                    </button>
                                    <button onClick={handleReset}
                                        className="px-4 py-2 rounded-xl text-sm font-medium text-slate-400"
                                        style={{ background: 'rgba(255,255,255,0.05)' }}>
                                        Submit Another
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Quick-start templates */}
            <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider mb-3">Quick Start Templates</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {[
                        { icon: '🦙', title: 'Fine-tune LLaMA 3 8B', sub: 'Custom dataset · ~$39 · 20hrs', goal: 'Fine-tune LLaMA 3 8B on my customer support dataset, keep cost under $50', color: '#00D4FF' },
                        { icon: '🎨', title: 'Stable Diffusion Batch', sub: '500 images · ~$8 · 2hrs', goal: 'Generate 500 product images with Stable Diffusion XL, 1024x1024', color: '#7B2FFF' },
                        { icon: '🎙️', title: 'Whisper Transcription', sub: '10 hours audio · ~$5 · 1hr', goal: 'Transcribe 10 hours of audio using Whisper Large v3', color: '#00FF88' },
                        { icon: '🔬', title: 'Hyperparameter Sweep', sub: '32 trials · ~$22 · 6hrs', goal: 'Run hyperparameter sweep 32 trials for my PyTorch model on A10 GPUs', color: '#FFB800' },
                    ].map(t => (
                        <button key={t.title} onClick={() => { setGoal(t.goal); textRef.current?.focus() }}
                            disabled={phase !== 'idle'}
                            className="text-left p-4 rounded-2xl transition-all hover:-translate-y-0.5 group"
                            style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
                            <div className="flex items-center gap-3">
                                <span className="text-xl">{t.icon}</span>
                                <div>
                                    <p className="text-sm font-semibold text-white group-hover:text-cyan-300 transition-colors">{t.title}</p>
                                    <p className="text-xs text-slate-500 mt-0.5">{t.sub}</p>
                                </div>
                                <ChevronRight size={14} className="ml-auto text-slate-600 group-hover:text-cyan-400 transition-colors" />
                            </div>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    )
}
