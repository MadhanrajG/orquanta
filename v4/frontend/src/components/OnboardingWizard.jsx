import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
    Cpu, Zap, DollarSign, Shield, ArrowRight, ArrowLeft,
    Check, X, Sparkles, Target, Server, BarChart2
} from 'lucide-react'

const GOAL_TEMPLATES = [
    {
        id: 'llama',
        icon: '🦙',
        title: 'Fine-tune LLaMA 3',
        desc: 'Custom dataset, budget $50',
        goal: 'Fine-tune LLaMA 3 8B on my custom dataset using A100 GPUs, keep cost under $50',
    },
    {
        id: 'whisper',
        icon: '🎙️',
        title: 'Batch Transcription',
        desc: 'Whisper Large v3, 10 hrs audio',
        goal: 'Transcribe 10 hours of audio files using Whisper Large v3, optimize for cost',
    },
    {
        id: 'sdxl',
        icon: '🎨',
        title: 'Image Generation',
        desc: 'SDXL 1024px, 1000 images',
        goal: 'Generate 1000 product images at 1024px using SDXL, budget $15',
    },
    {
        id: 'embeddings',
        icon: '🔍',
        title: 'Embedding Pipeline',
        desc: 'Vector embeddings at scale',
        goal: 'Generate 1M text embeddings for semantic search using the cheapest available GPU',
    },
    {
        id: 'sweep',
        icon: '📊',
        title: 'Hyperparameter Sweep',
        desc: '32 trials, A10 GPUs',
        goal: 'Run a 32-trial hyperparameter sweep on A10 GPUs, distributed across cheapest providers',
    },
    {
        id: 'custom',
        icon: '✏️',
        title: 'Custom Goal',
        desc: 'Describe your own task',
        goal: '',
    },
]

const STEPS = ['Welcome', 'First Goal', 'Budget']

function ProgressDots({ step }) {
    return (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 28 }}>
            {STEPS.map((label, i) => (
                <div key={label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                    <div style={{
                        width: i <= step ? 28 : 8,
                        height: 8,
                        borderRadius: 99,
                        transition: 'all 0.3s ease',
                        background: i < step
                            ? 'linear-gradient(90deg,#3a52eb,#7a9bfa)'
                            : i === step
                                ? 'linear-gradient(90deg,#7a9bfa,#a78bfa)'
                                : 'rgba(255,255,255,0.12)',
                    }} />
                </div>
            ))}
        </div>
    )
}

function Step1Welcome({ onNext, onSkip }) {
    const VALUE_PROPS = [
        { icon: DollarSign, color: '#00FF88', title: '67% cheaper than AWS', desc: 'H100 from $2.49/hr vs $12.29/hr on-demand' },
        { icon: Zap, color: '#00D4FF', title: '5 AI agents orchestrate', desc: 'Auto-routing, healing, cost optimization' },
        { icon: BarChart2, color: '#A78BFA', title: 'Natural language goals', desc: 'Describe what you want — agents handle the rest' },
        { icon: Shield, color: '#FFB800', title: 'Full audit trail', desc: 'Every agent action logged and reviewable' },
    ]

    return (
        <div className="animate-fade-in">
            <div style={{ textAlign: 'center', marginBottom: 28 }}>
                <div style={{
                    width: 64, height: 64, margin: '0 auto 16px',
                    background: 'linear-gradient(135deg,rgba(58,82,235,0.25),rgba(122,155,250,0.25))',
                    border: '1px solid rgba(122,155,250,0.35)',
                    borderRadius: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                    <Cpu size={30} color="#7a9bfa" />
                </div>
                <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', color: 'white', marginBottom: 8 }}>
                    Welcome to OrQuanta
                </h2>
                <p style={{ color: 'var(--text-muted)', fontSize: 14, lineHeight: 1.6, maxWidth: 380, margin: '0 auto' }}>
                    Your autonomous GPU cloud. Submit a goal in plain English — 5 AI agents
                    route, provision, and optimize your workload automatically.
                </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 28 }}>
                {VALUE_PROPS.map(({ icon: Icon, color, title, desc }) => (
                    <div key={title} style={{
                        background: 'rgba(255,255,255,0.035)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: 12, padding: '14px 14px',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                            <Icon size={16} color={color} />
                            <span style={{ fontSize: 13, fontWeight: 600, color: 'white' }}>{title}</span>
                        </div>
                        <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5, margin: 0 }}>{desc}</p>
                    </div>
                ))}
            </div>

            <button onClick={onNext} className="btn btn-primary" style={{ width: '100%', padding: '12px 0', fontSize: 15, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                Get Started <ArrowRight size={16} />
            </button>
            <button onClick={onSkip} style={{ width: '100%', marginTop: 10, background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 13, cursor: 'pointer', padding: '6px 0' }}>
                Skip for now
            </button>
        </div>
    )
}

function Step2Goal({ onNext, onBack }) {
    const [selected, setSelected] = useState(null)
    const [customText, setCustomText] = useState('')

    const handleNext = () => {
        if (!selected) return
        const goal = selected.id === 'custom' ? customText.trim() : selected.goal
        if (!goal || goal.length < 10) return
        onNext(goal)
    }

    const isReady = selected && (selected.id !== 'custom' || customText.trim().length >= 10)

    return (
        <div className="animate-fade-in">
            <div style={{ textAlign: 'center', marginBottom: 22 }}>
                <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.35rem', color: 'white', marginBottom: 6 }}>
                    What do you want to run?
                </h2>
                <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                    Choose a template to get started instantly
                </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
                {GOAL_TEMPLATES.map(t => (
                    <button
                        key={t.id}
                        onClick={() => setSelected(t)}
                        style={{
                            background: selected?.id === t.id
                                ? 'linear-gradient(135deg,rgba(58,82,235,0.22),rgba(167,139,250,0.18))'
                                : 'rgba(255,255,255,0.035)',
                            border: selected?.id === t.id
                                ? '1px solid rgba(122,155,250,0.5)'
                                : '1px solid rgba(255,255,255,0.08)',
                            borderRadius: 11, padding: '12px 12px', cursor: 'pointer',
                            textAlign: 'left', transition: 'all 0.15s ease', position: 'relative',
                        }}
                    >
                        {selected?.id === t.id && (
                            <div style={{
                                position: 'absolute', top: 7, right: 7,
                                width: 18, height: 18, borderRadius: '50%',
                                background: 'rgba(122,155,250,0.3)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                                <Check size={11} color="#7a9bfa" />
                            </div>
                        )}
                        <div style={{ fontSize: 20, marginBottom: 4 }}>{t.icon}</div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: 'white', marginBottom: 2 }}>{t.title}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t.desc}</div>
                    </button>
                ))}
            </div>

            {selected?.id === 'custom' && (
                <textarea
                    value={customText}
                    onChange={e => setCustomText(e.target.value)}
                    placeholder="Describe your GPU task in plain English... (min 10 chars)"
                    autoFocus
                    style={{
                        width: '100%', minHeight: 80, padding: '10px 12px',
                        background: 'rgba(255,255,255,0.05)',
                        border: '1px solid rgba(255,255,255,0.15)',
                        borderRadius: 10, color: '#e2e8f0', fontSize: 13,
                        resize: 'vertical', outline: 'none', boxSizing: 'border-box',
                        marginBottom: 12,
                    }}
                />
            )}

            <div style={{ display: 'flex', gap: 10 }}>
                <button onClick={onBack} className="btn btn-ghost" style={{ flex: '0 0 auto', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ArrowLeft size={15} /> Back
                </button>
                <button onClick={handleNext} disabled={!isReady} className="btn btn-primary" style={{ flex: 1, padding: '10px 0', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                    Continue <ArrowRight size={15} />
                </button>
            </div>
        </div>
    )
}

function Step3Budget({ goal, onFinish, onBack }) {
    const [budget, setBudget] = useState(50)
    const [notify, setNotify] = useState(true)
    const [loading, setLoading] = useState(false)

    const PRESETS = [10, 25, 50, 100, 250]

    const handleFinish = async () => {
        setLoading(true)
        // Small delay for UX — wizard feels deliberate, not instant
        await new Promise(r => setTimeout(r, 500))
        onFinish(goal, budget, notify)
    }

    return (
        <div className="animate-fade-in">
            <div style={{ textAlign: 'center', marginBottom: 24 }}>
                <div style={{ fontSize: 36, marginBottom: 10 }}>💰</div>
                <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.35rem', color: 'white', marginBottom: 6 }}>
                    Set your spending limit
                </h2>
                <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                    Agents will auto-stop your workload if this cap is reached
                </p>
            </div>

            <div style={{ marginBottom: 20 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, justifyContent: 'center', marginBottom: 12 }}>
                    <span style={{ fontSize: 40, fontWeight: 700, color: 'white', fontFamily: 'var(--font-mono)' }}>${budget}</span>
                    <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>max spend</span>
                </div>

                <input
                    type="range" min={5} max={500} step={5}
                    value={budget}
                    onChange={e => setBudget(Number(e.target.value))}
                    style={{ width: '100%', accentColor: '#7a9bfa', marginBottom: 12 }}
                />

                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
                    {PRESETS.map(p => (
                        <button
                            key={p}
                            onClick={() => setBudget(p)}
                            style={{
                                padding: '5px 14px', borderRadius: 99, border: '1px solid',
                                fontSize: 12, fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s',
                                borderColor: budget === p ? 'rgba(122,155,250,0.6)' : 'rgba(255,255,255,0.1)',
                                background: budget === p ? 'rgba(122,155,250,0.15)' : 'rgba(255,255,255,0.04)',
                                color: budget === p ? '#7a9bfa' : 'var(--text-muted)',
                            }}
                        >${p}</button>
                    ))}
                </div>
            </div>

            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 14px', borderRadius: 10, marginBottom: 22,
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.08)',
            }}>
                <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'white', marginBottom: 2 }}>Email alerts at 80% spend</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Get notified before hitting your limit</div>
                </div>
                <button
                    onClick={() => setNotify(n => !n)}
                    style={{
                        width: 44, height: 24, borderRadius: 99, border: 'none',
                        cursor: 'pointer', transition: 'all 0.2s',
                        background: notify ? 'linear-gradient(90deg,#3a52eb,#7a9bfa)' : 'rgba(255,255,255,0.12)',
                        position: 'relative',
                    }}
                >
                    <div style={{
                        width: 18, height: 18, borderRadius: '50%', background: 'white',
                        position: 'absolute', top: 3,
                        left: notify ? 23 : 3,
                        transition: 'left 0.2s',
                    }} />
                </button>
            </div>

            <div style={{ display: 'flex', gap: 10 }}>
                <button onClick={onBack} className="btn btn-ghost" style={{ flex: '0 0 auto', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ArrowLeft size={15} /> Back
                </button>
                <button onClick={handleFinish} disabled={loading} className="btn btn-primary" style={{ flex: 1, padding: '12px 0', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    {loading ? (
                        <>
                            <div style={{ width: 14, height: 14, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'white', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
                            Setting up...
                        </>
                    ) : (
                        <><Sparkles size={15} /> Start Orchestrating</>
                    )}
                </button>
            </div>
        </div>
    )
}

export default function OnboardingWizard() {
    const navigate = useNavigate()
    const [visible, setVisible] = useState(() => !localStorage.getItem('orq_onboarded'))
    const [step, setStep] = useState(0)
    const [selectedGoal, setSelectedGoal] = useState('')

    const dismiss = () => {
        localStorage.setItem('orq_onboarded', '1')
        setVisible(false)
    }

    const handleStep1Next = () => setStep(1)
    const handleStep2Next = (goal) => { setSelectedGoal(goal); setStep(2) }
    const handleStep3Finish = (goal, budget, notify) => {
        localStorage.setItem('orq_onboarded', '1')
        localStorage.setItem('orq_default_budget', String(budget))
        localStorage.setItem('orq_notify_spend', notify ? '1' : '0')
        setVisible(false)
        navigate(`/goals?goal=${encodeURIComponent(goal)}`)
    }

    if (!visible) return null

    return (
        <div style={{
            position: 'fixed', inset: 0, zIndex: 200,
            background: 'rgba(5,6,8,0.85)',
            backdropFilter: 'blur(8px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 20,
        }}>
            <div style={{
                width: '100%', maxWidth: 480,
                background: 'var(--surface-800)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 20,
                padding: '28px 28px 24px',
                position: 'relative',
                boxShadow: '0 24px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(122,155,250,0.08)',
            }}>
                <button
                    onClick={dismiss}
                    style={{
                        position: 'absolute', top: 16, right: 16,
                        background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: 8, width: 30, height: 30,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        color: 'var(--text-muted)', cursor: 'pointer',
                    }}
                >
                    <X size={15} />
                </button>

                <ProgressDots step={step} />

                {step === 0 && <Step1Welcome onNext={handleStep1Next} onSkip={dismiss} />}
                {step === 1 && <Step2Goal onNext={handleStep2Next} onBack={() => setStep(0)} />}
                {step === 2 && <Step3Budget goal={selectedGoal} onFinish={handleStep3Finish} onBack={() => setStep(1)} />}
            </div>
        </div>
    )
}
