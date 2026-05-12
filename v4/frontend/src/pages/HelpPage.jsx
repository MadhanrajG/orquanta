import { useState } from 'react'
import { X, BookOpen, MessageCircle, Zap, Shield, Code2, ExternalLink,
         Search, ChevronRight, HelpCircle, Mail, Globe, FileText,
         Brain, Cpu, DollarSign, BarChart2, Layers, Wand2 } from 'lucide-react'

const FAQS = [
    {
        section: 'ðŸš€ Getting Started',
        items: [
            {
                q: 'What is OrQuanta?',
                a: 'OrQuanta is an AI-native GPU cloud platform that autonomously orchestrates workloads across 6 cloud providers (Lambda Labs, RunPod, CoreWeave, AWS, GCP, Azure). Just describe your goal in plain English â€” 5 AI agents handle the rest.'
            },
            {
                q: 'How do I submit my first GPU job?',
                a: 'Click "Submit Goal" in the sidebar. Type your task in natural language (e.g. "Fine-tune LLaMA 3 8B on my dataset for $40"). OrQuanta will decompose it, find the cheapest GPU, and launch it automatically. Use a Quick Start Template to get started in seconds.'
            },
            {
                q: 'What is a "Goal" vs a "Job"?',
                a: 'A Goal is a high-level intent (e.g. "Train Whisper on 10hrs audio"). OrQuanta\'s AI agents decompose it into one or more Jobs â€” actual GPU compute tasks. You set the goal; agents handle the rest.'
            },
        ]
    },
    {
        section: 'ðŸ’° Cost & Billing',
        items: [
            {
                q: 'How does OrQuanta save me money?',
                a: 'The CostOptimizer agent continuously monitors spot prices across all providers every 60 seconds. It automatically routes jobs to the cheapest available GPU, switching providers mid-job when savings are significant. Users typically save 40-70% vs on-demand pricing.'
            },
            {
                q: 'How do I set a budget limit?',
                a: 'OrQuanta\'s CostWatcher enforces 3 automatic budget tiers: âš ï¸ Warn at 50%, ðŸ”¶ Throttle new jobs at 80%, ðŸ›‘ Halt non-critical jobs at 95%. Set your monthly budget in Billing & Plans â†’ Settings.'
            },
            {
                q: 'What payment methods are accepted?',
                a: 'Credit card via Stripe (Visa, Mastercard, Amex). Enterprise customers can use wire transfer or purchase orders. Contact support@orquanta.com for enterprise billing.'
            },
        ]
    },
    {
        section: 'ðŸ¤– AI Agents',
        items: [
            {
                q: 'What are the 5 core agents?',
                a: '1. Orchestrator â€” Decomposes your goal into subtasks. 2. Scheduler â€” Picks the optimal GPU and timing. 3. CostOptimizer â€” Finds the cheapest provider in real-time. 4. HealingAgent â€” Recovers failed jobs automatically. 5. Vero (Meta-Agent) â€” Oversees all agents and injects corrective goals.'
            },
            {
                q: 'What is NemoClaw?',
                a: 'NemoClaw is OrQuanta\'s cognitive enhancement layer. It adds persistent memory (ContextGraph), self-correcting reasoning (AdaptiveReAct), proactive GPU pre-warming (PredictivePrefetch), and real-time budget enforcement (CostWatcher). Access it via the Brain icon in the sidebar.'
            },
            {
                q: 'What is Vero?',
                a: 'Vero is the meta-agent â€” the "manager" that watches all other agents. It runs a health loop every 15 seconds, 60 seconds, and 5 minutes. If any agent misbehaves or makes a bad decision, Vero injects a corrective goal to fix it automatically.'
            },
        ]
    },
    {
        section: 'ðŸ›¡ï¸ Security & Compliance',
        items: [
            {
                q: 'How is my data protected?',
                a: 'All API calls are authenticated with JWT Bearer tokens (RS256). API keys are stored encrypted. Every agent decision is logged in the cryptographic Audit Log (HMAC-signed). OrQuanta never stores your model weights or training data.'
            },
            {
                q: 'What is the Audit Log?',
                a: 'A tamper-proof event trail of every decision made by every agent â€” job submissions, provider switches, cost alerts, healing actions. Each entry is HMAC-signed for integrity. Useful for SOC2 / compliance reviews.'
            },
        ]
    },
    {
        section: 'âš™ï¸ Technical',
        items: [
            {
                q: 'How do I connect my cloud provider API keys?',
                a: 'Go to Settings â†’ API Keys. Add your RunPod, Lambda Labs, CoreWeave, AWS, or GCP API keys. OrQuanta uses these to provision GPUs on your behalf. Keys are AES-256 encrypted at rest.'
            },
            {
                q: 'What GPU types are supported?',
                a: 'A100 80GB, H100 80GB, A10G, RTX 4090, RTX 3090, V100, T4 â€” across Lambda Labs, RunPod, CoreWeave, AWS (g5/p4d), GCP (a2/n1-highmem), and Azure (NDv3/NDv4). New GPU types are added automatically as providers list them.'
            },
            {
                q: 'Can I use OrQuanta with Kubernetes?',
                a: 'Yes. The KubernetesRunner agent manages multi-node distributed training with DDP/FSDP. Set job type to "distributed" in your goal. OrQuanta handles node provisioning, NFS mounting, and inter-node networking.'
            },
        ]
    },
]

const QUICK_LINKS = [
    { icon: Code2, label: 'API Reference', href: 'https://docs.orquanta.com/api', color: '#0091FF' },
    { icon: BookOpen, label: 'Documentation', href: 'https://docs.orquanta.com', color: '#A78BFA' },
    { icon: Mail, label: 'Email Support', href: 'mailto:support@orquanta.com', color: '#10B981' },
    { icon: MessageCircle, label: 'Discord Community', href: 'https://discord.gg/orquanta', color: '#5865F2' },
    { icon: Globe, label: 'Status Page', href: 'https://status.orquanta.com', color: '#F59E0B' },
    { icon: FileText, label: 'Changelog', href: 'https://docs.orquanta.com/changelog', color: '#FF6B6B' },
]

const FEATURE_CARDS = [
    { Icon: Brain, label: 'NemoClaw', desc: 'Cognitive AI layer with persistent memory', color: '#0091FF', route: '/nemoclaw' },
    { Icon: Cpu, label: 'Agent Monitor', desc: 'Real-time view of all 5 AI agents', color: '#A78BFA', route: '/agents' },
    { Icon: DollarSign, label: 'Cost Analytics', desc: 'Spend breakdown and savings dashboard', color: '#10B981', route: '/costs' },
    { Icon: BarChart2, label: 'Live Pricing', desc: 'GPU spot prices updated every 60s', color: '#F59E0B', route: '/pricing' },
    { Icon: Layers, label: 'Audit Log', desc: 'Cryptographic trail of every decision', color: '#FF6B6B', route: '/audit' },
    { Icon: Wand2, label: 'UIXAgent', desc: 'UI/UX self-diagnostic and fix agent', color: '#7B2FFF', route: '/uix' },
]

export default function HelpPage() {
    const [search, setSearch] = useState('')
    const [openIdx, setOpenIdx] = useState({})

    const filtered = FAQS.map(section => ({
        ...section,
        items: section.items.filter(
            item =>
                !search ||
                item.q.toLowerCase().includes(search.toLowerCase()) ||
                item.a.toLowerCase().includes(search.toLowerCase())
        )
    })).filter(s => s.items.length > 0)

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="text-center py-6">
                <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4"
                    style={{ background: 'linear-gradient(135deg, rgba(0,145,255,0.15), rgba(123,47,255,0.15))', border: '1px solid rgba(0,145,255,0.2)' }}>
                    <HelpCircle size={26} style={{ color: '#0091FF' }} />
                </div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">Help Center</h1>
                <p className="text-slate-400 text-sm max-w-md mx-auto">
                    Everything you need to master OrQuanta â€” the AI-native GPU cloud platform.
                </p>
            </div>

            {/* Search */}
            <div className="relative max-w-lg mx-auto">
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                    type="text"
                    placeholder="Search help articles..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    aria-label="Search help articles"
                    className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm text-gray-900"
                    style={{ background: 'rgba(0,0,0,0.04)', border: '1px solid rgba(0,0,0,0.08)', outline: 'none' }}
                />
            </div>

            {/* Quick Links */}
            <div className="glass-card p-5">
                <h2 className="text-gray-900 font-semibold mb-4 text-sm uppercase tracking-wide opacity-60">Quick Links</h2>
                <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
                    {QUICK_LINKS.map(({ icon: Icon, label, href, color }) => (
                        <a key={label} href={href} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-2.5 p-3 rounded-xl transition-all hover:scale-105"
                            style={{ background: color + '10', border: `1px solid ${color}20`, textDecoration: 'none' }}>
                            <Icon size={14} style={{ color }} />
                            <span className="text-sm font-medium text-gray-900">{label}</span>
                            <ExternalLink size={10} className="ml-auto opacity-40 text-gray-900" />
                        </a>
                    ))}
                </div>
            </div>

            {/* Featured Pages */}
            <div className="glass-card p-5">
                <h2 className="text-gray-900 font-semibold mb-4 text-sm uppercase tracking-wide opacity-60">Platform Features</h2>
                <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
                    {FEATURE_CARDS.map(({ Icon, label, desc, color, route }) => (
                        <a key={label} href={`/app${route}`}
                            className="flex items-start gap-3 p-3 rounded-xl transition-all hover:scale-[1.02] cursor-pointer"
                            style={{ background: 'rgba(0,0,0,0.02)', border: '1px solid rgba(0,0,0,0.06)', textDecoration: 'none' }}>
                            <div className="p-1.5 rounded-lg shrink-0" style={{ background: color + '15' }}>
                                <Icon size={14} style={{ color }} />
                            </div>
                            <div>
                                <p className="text-sm font-semibold text-gray-900">{label}</p>
                                <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                            </div>
                            <ChevronRight size={12} className="ml-auto self-center text-slate-600" />
                        </a>
                    ))}
                </div>
            </div>

            {/* FAQ Accordion */}
            <div className="space-y-4">
                <h2 className="text-gray-900 font-semibold text-sm uppercase tracking-wide opacity-60">Frequently Asked Questions</h2>
                {filtered.length === 0 && (
                    <div className="glass-card p-8 text-center">
                        <p className="text-slate-400">No results for "{search}". Try different keywords.</p>
                    </div>
                )}
                {filtered.map((section, si) => (
                    <div key={si} className="glass-card overflow-hidden">
                        <div className="px-5 py-3 border-b border-white/[0.06]">
                            <h3 className="text-sm font-semibold text-gray-900">{section.section}</h3>
                        </div>
                        <div>
                            {section.items.map((item, ii) => {
                                const key = `${si}-${ii}`
                                const isOpen = openIdx[key]
                                return (
                                    <div key={ii} className="border-b border-white/[0.04] last:border-0">
                                        <button
                                            aria-expanded={isOpen}
                                            aria-label={item.q}
                                            onClick={() => setOpenIdx(o => ({ ...o, [key]: !o[key] }))}
                                            className="w-full flex items-center justify-between px-5 py-3.5 text-left transition-colors"
                                            style={{ background: isOpen ? 'rgba(0,145,255,0.04)' : 'none', cursor: 'pointer', border: 'none', color: 'var(--text-primary)' }}
                                        >
                                            <span className="text-sm font-medium text-gray-900 pr-4">{item.q}</span>
                                            <ChevronRight size={14} className="text-slate-500 shrink-0 transition-transform"
                                                style={{ transform: isOpen ? 'rotate(90deg)' : 'none' }} />
                                        </button>
                                        {isOpen && (
                                            <div className="px-5 pb-4">
                                                <p className="text-sm text-slate-400 leading-relaxed">{item.a}</p>
                                            </div>
                                        )}
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                ))}
            </div>

            {/* Contact Support */}
            <div className="glass-card p-6 text-center"
                style={{ background: 'linear-gradient(135deg, rgba(0,145,255,0.05), rgba(123,47,255,0.05))', border: '1px solid rgba(0,145,255,0.1)' }}>
                <MessageCircle size={24} className="mx-auto mb-3" style={{ color: '#0091FF' }} />
                <h3 className="text-gray-900 font-semibold mb-1">Still need help?</h3>
                <p className="text-slate-500 text-sm mb-4">Our team is available Monâ€“Fri, 9amâ€“6pm IST</p>
                <div className="flex items-center justify-center gap-3 flex-wrap">
                    <a href="mailto:support@orquanta.com"
                        className="btn-primary text-sm flex items-center gap-2"
                        style={{ background: 'linear-gradient(135deg,#0091FF,#7B2FFF)' }}>
                        <Mail size={13} /> Email Support
                    </a>
                    <a href="https://discord.gg/orquanta" target="_blank" rel="noopener noreferrer"
                        className="btn-ghost text-sm flex items-center gap-2">
                        <MessageCircle size={13} /> Discord
                    </a>
                </div>
            </div>
        </div>
    )
}


