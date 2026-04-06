import { useState, useCallback } from 'react'
import { Wand2, RefreshCw, CheckCircle, AlertTriangle, Zap, Shield, Eye,
         BarChart2, Layers, ChevronRight, Play, Wrench, Award } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || ''
const getH = () => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${localStorage.getItem('orquanta_token') || ''}`,
})

const GRADE_COLOR = { A: '#00FF88', B: '#00D4FF', C: '#FFB800', D: '#FF8C42', F: '#ff4444' }
const SEV_COLOR = { critical: '#ff4444', high: '#FF8C42', medium: '#FFB800', low: '#00D4FF', info: '#94a3b8' }
const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }

const CAT_ICONS = {
    'Visual Consistency': Layers,
    'Empty State UX': Eye,
    'Loading States': RefreshCw,
    'Responsiveness': BarChart2,
    'Interaction Feedback': Zap,
    'Accessibility': Shield,
}

function ScoreRing({ score, size = 80 }) {
    const r = size / 2 - 6
    const circ = 2 * Math.PI * r
    const progress = (score / 100) * circ
    const color = score >= 90 ? '#00FF88' : score >= 75 ? '#00D4FF' : score >= 60 ? '#FFB800' : '#ff4444'
    return (
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={5} />
            <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={5}
                strokeDasharray={`${progress} ${circ}`} strokeLinecap="round"
                transform={`rotate(-90 ${size/2} ${size/2})`}
                style={{ filter: `drop-shadow(0 0 4px ${color})` }} />
            <text x={size/2} y={size/2 + 1} textAnchor="middle" dominantBaseline="middle"
                fill={color} fontSize={size / 4} fontWeight="700" fontFamily="monospace">{score}</text>
        </svg>
    )
}

function PageCard({ ps, onClick, selected }) {
    const gradeColor = GRADE_COLOR[ps.grade] || '#94a3b8'
    return (
        <div onClick={onClick} className="glass-card p-4 cursor-pointer transition-all"
            style={{ border: `1px solid ${selected ? 'rgba(123,47,255,0.5)' : 'rgba(255,255,255,0.06)'}`,
                     boxShadow: selected ? '0 0 16px rgba(123,47,255,0.15)' : undefined }}>
            <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-semibold text-white truncate">{ps.page}</p>
                <span className="text-xs font-bold px-1.5 py-0.5 rounded" style={{ background: gradeColor + '20', color: gradeColor }}>
                    {ps.grade}
                </span>
            </div>
            <div className="flex items-center gap-2">
                <ScoreRing score={ps.overall_score} size={48} />
                <div>
                    <p className="text-xs text-slate-500">{ps.issue_count} issue{ps.issue_count !== 1 ? 's' : ''}</p>
                    <p className="text-xs text-slate-600 mt-0.5">{ps.route}</p>
                </div>
            </div>
        </div>
    )
}

function IssueRow({ issue }) {
    const sev = issue.severity
    return (
        <div className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
            <div className="flex items-start gap-3">
                <span className="mt-0.5 text-xs px-1.5 py-0.5 rounded font-medium shrink-0"
                    style={{ background: SEV_COLOR[sev] + '20', color: SEV_COLOR[sev] }}>
                    {sev.toUpperCase()}
                </span>
                <div className="flex-1 min-w-0">
                    <p className="text-sm text-white font-medium">{issue.title}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{issue.description}</p>
                    <p className="text-xs mt-1.5 italic" style={{ color: '#A78BFA' }}>
                        Fix: {issue.fix_description}
                    </p>
                </div>
                <div className="text-right shrink-0">
                    <p className="text-xs text-slate-500">-{issue.score_impact}pts</p>
                    {issue.auto_fixable && (
                        <span className="text-xs" style={{ color: '#00FF88' }}>⚡ Auto</span>
                    )}
                </div>
            </div>
        </div>
    )
}

export default function UIXAgentPage() {
    const [auditing, setAuditing] = useState(false)
    const [report, setReport] = useState(null)
    const [error, setError] = useState('')
    const [selectedPage, setSelectedPage] = useState(null)
    const [applyingPatchId, setApplyingPatchId] = useState(null)
    const [patchResults, setPatchResults] = useState({})
    const [tab, setTab] = useState('overview')

    const runAudit = useCallback(async () => {
        setAuditing(true); setError(''); setReport(null); setSelectedPage(null)
        try {
            const res = await fetch(`${API}/api/v1/uix/audit`, { method: 'POST', headers: getH() })
            if (!res.ok) throw new Error(await res.text())
            const data = await res.json()
            setReport(data)
            if (data.page_scores?.length) setSelectedPage(data.page_scores[0])
        } catch (e) {
            setError(e.message || 'UIXAgent audit failed.')
        } finally { setAuditing(false) }
    }, [])

    const applyPatch = async (patchId) => {
        setApplyingPatchId(patchId)
        try {
            const res = await fetch(`${API}/api/v1/uix/patches/${patchId}/apply`, { method: 'POST', headers: getH() })
            const data = await res.json()
            setPatchResults(r => ({ ...r, [patchId]: data }))
        } catch { setPatchResults(r => ({ ...r, [patchId]: { error: 'Failed' } })) }
        finally { setApplyingPatchId(null) }
    }

    const sorted_pages = report?.page_scores?.slice().sort((a, b) => a.overall_score - b.overall_score) || []
    const top_issues = report?.top_issues?.slice().sort((a, b) => (SEV_ORDER[a.severity] || 4) - (SEV_ORDER[b.severity] || 4)) || []
    const sel_issues = selectedPage
        ? (report?.top_issues || []).filter(i => i.page === selectedPage.page)
        : top_issues

    const TABS = [
        { id: 'overview', label: 'Overview', Icon: BarChart2 },
        { id: 'pages', label: 'Pages', Icon: Layers },
        { id: 'issues', label: 'Issues', Icon: AlertTriangle },
        { id: 'enhance', label: 'Enhancements', Icon: Wand2 },
    ]

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl" style={{ background: 'linear-gradient(135deg, rgba(0,212,255,0.15), rgba(123,47,255,0.15))' }}>
                        <Wand2 size={22} style={{ color: '#00D4FF' }} />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-white">UIXAgent</h1>
                        <p className="text-xs text-slate-500">Autonomous UI/UX Diagnostic · 12 rules · 6 categories · Auto-fix pipeline</p>
                    </div>
                </div>
                <button onClick={runAudit} disabled={auditing}
                    className="btn-primary flex items-center gap-2"
                    style={{ background: 'linear-gradient(135deg, #00D4FF, #7B2FFF)', opacity: auditing ? 0.7 : 1 }}>
                    {auditing ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
                    {auditing ? 'Auditing All 13 Pages...' : 'Run Full Audit'}
                </button>
            </div>

            {error && (
                <div className="glass-card p-3 border border-red-500/30 bg-red-500/10 flex items-center gap-2">
                    <AlertTriangle size={14} className="text-red-400" />
                    <p className="text-sm text-red-400">{error}</p>
                </div>
            )}

            {!report && !auditing && (
                <div className="glass-card p-12 text-center" style={{ border: '1px solid rgba(0,212,255,0.08)' }}>
                    <Wand2 size={48} className="mx-auto mb-4 opacity-20 text-cyan-400" />
                    <h3 className="text-white font-semibold mb-2">Ready to Diagnose</h3>
                    <p className="text-slate-500 text-sm max-w-md mx-auto">
                        UIXAgent will crawl all 13 pages, apply 12 UX heuristic rules,
                        score each page A–F, and generate auto-fix patches — in seconds.
                    </p>
                </div>
            )}

            {auditing && (
                <div className="glass-card p-8 text-center space-y-3">
                    <RefreshCw size={32} className="mx-auto animate-spin" style={{ color: '#00D4FF' }} />
                    <p className="text-white font-medium">Auditing all 13 pages...</p>
                    <p className="text-slate-500 text-sm">Applying 12 heuristic rules across 6 UX categories</p>
                </div>
            )}

            {report && (
                <>
                    {/* Tabs */}
                    <div className="flex gap-1 border-b border-white/[0.08]">
                        {TABS.map(({ id, label, Icon }) => (
                            <button key={id} onClick={() => setTab(id)}
                                className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-all"
                                style={{
                                    color: tab === id ? '#00D4FF' : '#94a3b8',
                                    borderBottom: tab === id ? '2px solid #00D4FF' : '2px solid transparent',
                                    background: 'none', cursor: 'pointer',
                                }}>
                                <Icon size={13} /> {label}
                            </button>
                        ))}
                    </div>

                    {/* ── Overview ── */}
                    {tab === 'overview' && (
                        <div className="space-y-5">
                            <div className="glass-card p-6 flex items-center gap-8">
                                <ScoreRing score={report.overall_platform_score} size={100} />
                                <div>
                                    <h2 className="text-2xl font-bold text-white">Platform UX Score</h2>
                                    <p className="text-slate-400 text-sm mt-1">{report.summary}</p>
                                </div>
                            </div>

                            <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
                                {[
                                    { label: 'Pages Audited', v: report.pages_audited, c: '#00D4FF' },
                                    { label: 'Total Issues', v: report.total_issues, c: '#FFB800' },
                                    { label: 'Auto-Fixable', v: report.auto_fixable_count, c: '#00FF88' },
                                    { label: 'Medium Issues', v: report.medium_count, c: '#FFB800' },
                                    { label: 'Low Issues', v: report.low_count, c: '#94a3b8' },
                                ].map(({ label, v, c }) => (
                                    <div key={label} className="glass-card p-4">
                                        <p className="text-xs text-slate-500 mb-1">{label}</p>
                                        <p className="text-2xl font-bold font-mono" style={{ color: c }}>{v}</p>
                                    </div>
                                ))}
                            </div>

                            {/* Worst pages */}
                            <div className="glass-card p-5">
                                <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
                                    <AlertTriangle size={14} style={{ color: '#FFB800' }} /> Lowest Scoring Pages
                                </h3>
                                <div className="space-y-2">
                                    {sorted_pages.slice(0, 5).map(ps => (
                                        <div key={ps.page} className="flex items-center gap-3 p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                                            <ScoreRing score={ps.overall_score} size={36} />
                                            <div className="flex-1">
                                                <p className="text-sm text-white">{ps.page}</p>
                                                <p className="text-xs text-slate-500">{ps.issue_count} issues</p>
                                            </div>
                                            <span className="text-xs font-bold" style={{ color: GRADE_COLOR[ps.grade] }}>{ps.grade}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* ── Pages Grid ── */}
                    {tab === 'pages' && (
                        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
                            {report.page_scores.map(ps => (
                                <PageCard key={ps.page} ps={ps}
                                    onClick={() => { setSelectedPage(ps); setTab('issues') }}
                                    selected={selectedPage?.page === ps.page} />
                            ))}
                        </div>
                    )}

                    {/* ── Issues ── */}
                    {tab === 'issues' && (
                        <div className="space-y-3">
                            {selectedPage && (
                                <div className="flex items-center gap-2 text-sm">
                                    <button onClick={() => setSelectedPage(null)} className="text-slate-500 hover:text-white">All Issues</button>
                                    <ChevronRight size={12} className="text-slate-600" />
                                    <span style={{ color: '#00D4FF' }}>{selectedPage.page}</span>
                                </div>
                            )}
                            {sel_issues.length === 0 ? (
                                <div className="glass-card p-8 text-center">
                                    <CheckCircle size={32} className="mx-auto mb-2 text-green-400" />
                                    <p className="text-white font-medium">No issues found!</p>
                                </div>
                            ) : (
                                sel_issues.map(i => <IssueRow key={i.issue_id} issue={i} />)
                            )}
                        </div>
                    )}

                    {/* ── Enhancements ── */}
                    {tab === 'enhance' && (
                        <div className="space-y-4">
                            <div className="glass-card p-5 border border-violet-500/20">
                                <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
                                    <Award size={16} style={{ color: '#A78BFA' }} /> Futuristic Enhancement Priorities
                                </h3>
                                {[
                                    { tier: 'T1', label: 'Live 3D Globe Map', desc: 'Replace blob SVG with WebGL orbital GPU node visualization', impact: 'Visual WOW', color: '#00FF88', time: '3 days' },
                                    { tier: 'T1', label: 'AI Goal Autocomplete', desc: 'LLM completions in the Submit Goal textarea as user types', impact: 'UX Revolution', color: '#00FF88', time: '2 days' },
                                    { tier: 'T1', label: 'Fix Live Pricing 0-results', desc: 'Show mock spot prices when provider keys not configured', impact: 'Critical UX', color: '#FFB800', time: '1 day' },
                                    { tier: 'T2', label: 'Skeleton Loading States', desc: 'Replace blank states with shimmer skeletons on all data pages', impact: 'Polish', color: '#00D4FF', time: '2 days' },
                                    { tier: 'T2', label: 'Cost Savings Hero', desc: '"You saved $X this month" prominent banner on dashboard', impact: 'Retention', color: '#00D4FF', time: '1 day' },
                                    { tier: 'T2', label: 'Keyboard Shortcuts', desc: 'Global command palette already exists — expand with 20 shortcuts', impact: 'Power Users', color: '#00D4FF', time: '1 day' },
                                    { tier: 'T3', label: 'Team Workspaces', desc: 'Multi-user GPU budgets with per-member spend tracking', impact: 'Enterprise', color: '#A78BFA', time: '2 weeks' },
                                    { tier: 'T3', label: 'pgvector ContextGraph', desc: 'Semantic search at 1M+ nodes for true institutional memory', impact: 'Moat', color: '#A78BFA', time: '2 weeks' },
                                ].map(e => (
                                    <div key={e.label} className="flex items-start gap-3 p-3 rounded-lg mb-2"
                                        style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
                                        <span className="text-xs font-bold px-1.5 py-0.5 rounded shrink-0 mt-0.5"
                                            style={{ background: e.color + '20', color: e.color }}>{e.tier}</span>
                                        <div className="flex-1">
                                            <p className="text-sm text-white font-medium">{e.label}</p>
                                            <p className="text-xs text-slate-500 mt-0.5">{e.desc}</p>
                                        </div>
                                        <div className="text-right shrink-0">
                                            <p className="text-xs font-medium" style={{ color: e.color }}>{e.impact}</p>
                                            <p className="text-xs text-slate-600">{e.time}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </>
            )}
        </div>
    )
}
