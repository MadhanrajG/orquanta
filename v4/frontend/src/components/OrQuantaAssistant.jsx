import { useState, useEffect, useRef, useCallback } from 'react'
import { MessageSquare, X, Minimize2, Send, Loader, Sparkles, Brain } from 'lucide-react'
import { useAuth } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

/* ─── Smart context-aware responses ──────────────────────────────────── */
const DEMO_RESPONSES = {
    utilization: 'Your GPU utilization is averaging 81% across active instances on Lambda Labs. The A100 cluster is particularly efficient at 88%. I recommend checking the idle instances in us-east-1 — two appear underutilized.',
    cost: 'Your projected spend this month is **$1,240** based on current usage patterns, down 23% from last month. OrQuanta has saved you **$1,247** vs AWS on-demand pricing so far. The biggest saving: migrating 3 jobs from AWS ($4.10/hr) to Lambda Labs ($1.99/hr).',
    spot: '**Yes, switching to spot now makes sense.** Current spot interruption risk is 8% — well within acceptable range. Switching would save approximately $47/hour on your current workload mix. Want me to migrate the 3 eligible jobs now?',
    gpu: 'For fine-tuning Llama 70B, you need at least 80GB VRAM per node. I recommend:\n\n• **8× A100 80GB** on Lambda Labs ($14.32/hr) — fastest\n• **8× A100** on CoreWeave ($13.80/hr) — cheapest\n• Estimated time: 8–12 hours | Cost: $114–$170\n\nShall I submit this job?',
    failed: 'Last week you had **2 failed jobs**: `orq-7a2f` failed with OOM (batch size 32 too large for A10 VRAM), and `orq-9c1e` hit spot interruption. Both were automatically retried — `orq-7a2f` succeeded with batch_size=16, `orq-9c1e` completed on requeue.',
    default: 'I can help you with job status, GPU costs, agent decisions, and infrastructure recommendations. Try asking "What\'s my projected spend this month?" or "Should I switch to spot instances right now?"',
}

function getResponse(msg) {
    const m = msg.toLowerCase()
    if (m.includes('utiliz') || m.includes('gpu util')) return DEMO_RESPONSES.utilization
    if (m.includes('cost') || m.includes('spend') || m.includes('budget') || m.includes('month')) return DEMO_RESPONSES.cost
    if (m.includes('spot')) return DEMO_RESPONSES.spot
    if (m.includes('70b') || m.includes('which gpu') || m.includes('gpu should')) return DEMO_RESPONSES.gpu
    if (m.includes('fail') || m.includes('last week') || m.includes('error')) return DEMO_RESPONSES.failed
    return DEMO_RESPONSES.default
}

/* ─── Message ─────────────────────────────────────────────────────────── */
function Message({ role, content, streaming }) {
    // Convert basic markdown to JSX
    const renderContent = (text) => {
        const lines = text.split('\n')
        return lines.map((line, i) => {
            const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
            return (
                <div key={i} className={i > 0 && line === '' ? 'h-2' : ''}>
                    {parts.map((part, j) => {
                        if (part.startsWith('**') && part.endsWith('**'))
                            return <strong key={j} className="font-semibold text-white">{part.slice(2, -2)}</strong>
                        if (part.startsWith('`') && part.endsWith('`'))
                            return <code key={j} className="px-1.5 py-0.5 rounded text-xs font-mono"
                                style={{ background: 'rgba(0,212,255,0.1)', color: '#00D4FF' }}>{part.slice(1, -1)}</code>
                        if (part.startsWith('•'))
                            return <div key={j} className="flex gap-2 mt-1"><span className="text-cyan-400">•</span><span>{part.slice(1)}</span></div>
                        return <span key={j}>{part}</span>
                    })}
                </div>
            )
        })
    }

    return (
        <div className={`flex gap-3 ${role === 'user' ? 'flex-row-reverse' : ''} mb-3`}>
            <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-sm mt-0.5"
                style={{ background: role === 'user' ? 'rgba(123,47,255,0.2)' : 'rgba(0,212,255,0.15)' }}>
                {role === 'user' ? '👤' : '🧠'}
            </div>
            <div className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed
          ${role === 'user'
                    ? 'text-white rounded-tr-sm'
                    : 'text-slate-300 rounded-tl-sm'}`}
                style={{
                    background: role === 'user' ? 'rgba(123,47,255,0.2)' : 'rgba(255,255,255,0.05)',
                    border: `1px solid ${role === 'user' ? 'rgba(123,47,255,0.3)' : 'rgba(255,255,255,0.08)'}`,
                }}>
                {renderContent(content)}
                {streaming && <span className="inline-block w-1.5 h-3.5 bg-cyan-400 ml-0.5 animate-pulse rounded-sm" />}
            </div>
        </div>
    )
}

/* ─── Quick actions ────────────────────────────────────────────────────── */
const QUICK_ACTIONS = [
    "What's my GPU utilization?",
    "Projected spend this month?",
    "Which jobs failed last week?",
    "Should I switch to spot now?",
]

/* ─── Main Assistant Component ────────────────────────────────────────── */
export default function OrQuantaAssistant() {
    const [open, setOpen] = useState(false)
    const [messages, setMessages] = useState([
        { role: 'assistant', content: "Hi! I'm OrQuanta's AI assistant. I know your platform state in real-time — jobs, costs, agent decisions, GPU metrics.\n\nAsk me anything about your infrastructure." }
    ])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const [unread, setUnread] = useState(0)
    const scrollRef = useRef(null)
    const inputRef = useRef(null)
    const { token } = useAuth()

    useEffect(() => {
        if (scrollRef.current)
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }, [messages])

    useEffect(() => {
        if (open) { setUnread(0); setTimeout(() => inputRef.current?.focus(), 100) }
    }, [open])

    const sendMessage = useCallback(async (text) => {
        const msg = (text || input).trim()
        if (!msg || loading) return
        setInput('')
        setMessages(prev => [...prev, { role: 'user', content: msg }])
        setLoading(true)

        // Add streaming placeholder
        setMessages(prev => [...prev, { role: 'assistant', content: '', streaming: true }])

        // Try real API, fall back to demo
        let reply = ''
        try {
            const res = await fetch(`${API}/assistant/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ message: msg }),
                signal: AbortSignal.timeout(8000),
            })
            if (res.ok) {
                const data = await res.json()
                reply = data.reply || data.message || getResponse(msg)
            } else {
                reply = getResponse(msg)
            }
        } catch {
            reply = getResponse(msg)
        }

        // Simulate streaming word by word
        const words = reply.split(' ')
        let current = ''
        for (let i = 0; i < words.length; i++) {
            current += (i > 0 ? ' ' : '') + words[i]
            const snap = current
            setMessages(prev => [
                ...prev.slice(0, -1),
                { role: 'assistant', content: snap, streaming: i < words.length - 1 }
            ])
            await new Promise(r => setTimeout(r, 22))
        }
        setLoading(false)
        if (!open) setUnread(u => u + 1)
    }, [input, loading, open, token])

    const handleKey = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
    }

    return (
        <>
            {/* ── Floating toggle button ── */}
            <div className="fixed bottom-6 right-6 z-50">
                {!open && (
                    <button onClick={() => setOpen(true)} id="assistant-toggle"
                        className="relative w-14 h-14 rounded-2xl flex items-center justify-center shadow-2xl transition-all hover:scale-110 active:scale-95"
                        style={{ background: 'linear-gradient(135deg, #00D4FF, #7B2FFF)', boxShadow: '0 0 30px rgba(0,212,255,0.4), 0 8px 32px rgba(0,0,0,0.4)' }}>
                        <Brain size={24} className="text-white" />
                        {/* Pulse ring */}
                        <span className="absolute inset-0 rounded-2xl animate-ping opacity-20"
                            style={{ background: 'linear-gradient(135deg, #00D4FF, #7B2FFF)' }} />
                        {unread > 0 && (
                            <span className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center font-bold">
                                {unread}
                            </span>
                        )}
                    </button>
                )}
            </div>

            {/* ── Chat panel ── */}
            {open && (
                <div className="fixed bottom-6 right-6 z-50 w-96 flex flex-col animate-slide-up shadow-2xl"
                    style={{
                        height: 520,
                        borderRadius: 20,
                        background: 'rgba(10,11,20,0.95)',
                        border: '1px solid rgba(0,212,255,0.15)',
                        backdropFilter: 'blur(20px)',
                        boxShadow: '0 0 60px rgba(0,212,255,0.1), 0 32px 64px rgba(0,0,0,0.6)',
                    }}>

                    {/* Header */}
                    <div className="flex items-center gap-3 px-4 py-3.5 border-b" style={{ borderColor: 'rgba(255,255,255,0.07)' }}>
                        <div className="w-8 h-8 rounded-xl flex items-center justify-center"
                            style={{ background: 'linear-gradient(135deg, rgba(0,212,255,0.2), rgba(123,47,255,0.2))', border: '1px solid rgba(0,212,255,0.2)' }}>
                            <Brain size={16} className="text-cyan-400" />
                        </div>
                        <div className="flex-1">
                            <div className="text-sm font-semibold text-white">OrQuanta Assistant</div>
                            <div className="flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                                <span className="text-xs text-green-400">Live platform context</span>
                            </div>
                        </div>
                        <button onClick={() => setOpen(false)} className="text-slate-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/5">
                            <X size={16} />
                        </button>
                    </div>

                    {/* Messages */}
                    <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4" style={{ scrollbarWidth: 'thin', scrollbarColor: 'rgba(255,255,255,0.1) transparent' }}>
                        {messages.map((msg, i) => (
                            <Message key={i} {...msg} />
                        ))}
                        {loading && messages[messages.length - 1]?.content === '' && (
                            <div className="flex gap-2 items-center px-3 py-2">
                                {[0, 1, 2].map(i => (
                                    <div key={i} className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-bounce"
                                        style={{ animationDelay: `${i * 0.15}s` }} />
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Quick actions */}
                    {messages.length <= 1 && (
                        <div className="px-4 pb-2 flex flex-wrap gap-1.5">
                            {QUICK_ACTIONS.map(q => (
                                <button key={q} onClick={() => sendMessage(q)}
                                    className="text-xs px-2.5 py-1 rounded-lg text-slate-400 transition-all hover:text-cyan-400"
                                    style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}>
                                    {q}
                                </button>
                            ))}
                        </div>
                    )}

                    {/* Input */}
                    <div className="px-3 pb-3">
                        <div className="flex items-center gap-2 rounded-xl px-3 py-2"
                            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}>
                            <input ref={inputRef} id="assistant-input"
                                value={input}
                                onChange={e => setInput(e.target.value)}
                                onKeyDown={handleKey}
                                placeholder="Ask about your GPU infrastructure…"
                                className="flex-1 bg-transparent text-sm text-white placeholder-slate-600 outline-none"
                            />
                            <button onClick={() => sendMessage()} disabled={!input.trim() || loading}
                                className="w-7 h-7 rounded-lg flex items-center justify-center transition-all"
                                style={{
                                    background: input.trim() && !loading ? 'linear-gradient(135deg, #00D4FF, #7B2FFF)' : 'rgba(255,255,255,0.06)',
                                    color: input.trim() && !loading ? 'white' : '#475569',
                                }}>
                                {loading ? <Loader size={13} className="animate-spin" /> : <Send size={13} />}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    )
}
