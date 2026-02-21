import { useState, useEffect } from 'react'
import { ScrollText, RefreshCw, Filter, CheckCircle, AlertCircle, Clock } from 'lucide-react'
import { useAuth } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

export default function AuditLog() {
    const { token } = useAuth()
    const [entries, setEntries] = useState([])
    const [total, setTotal] = useState(0)
    const [loading, setLoading] = useState(true)
    const [agentFilter, setAgentFilter] = useState('')
    const [stats, setStats] = useState(null)

    const AGENTS = ['', 'master_orchestrator', 'scheduler_agent', 'cost_optimizer_agent', 'healing_agent', 'forecast_agent']

    const fetchAudit = async () => {
        setLoading(true)
        try {
            const params = agentFilter ? `?agent=${agentFilter}` : ''
            const headers = { Authorization: `Bearer ${token}` }
            const [auditRes, statsRes] = await Promise.all([
                fetch(`${API}/api/v1/audit${params}&limit=50`, { headers }),
                fetch(`${API}/api/v1/audit/stats`, { headers })
            ])
            if (auditRes.ok) { const d = await auditRes.json(); setEntries(d.entries || []); setTotal(d.total ?? 0) }
            if (statsRes.ok) setStats(await statsRes.json())
        } catch { }
        finally { setLoading(false) }
    }

    useEffect(() => { fetchAudit(); const t = setInterval(fetchAudit, 10000); return () => clearInterval(t) }, [agentFilter])

    const outcomeIcon = o => o === 'success' ? <CheckCircle size={13} className="text-emerald-400" /> :
        o?.startsWith('error') ? <AlertCircle size={13} className="text-red-400" /> :
            <Clock size={13} className="text-amber-400" />

    const agentColor = name => ({
        master_orchestrator: 'text-purple-400', scheduler_agent: 'text-brand-400',
        cost_optimizer_agent: 'text-emerald-400', healing_agent: 'text-amber-400',
        forecast_agent: 'text-cyan-400',
    }[name] || 'text-slate-400')

    return (
        <div className="space-y-6 animate-fade-in">
            <div>
                <h1 className="text-2xl font-bold text-white">Audit Log</h1>
                <p className="text-slate-400 text-sm mt-0.5">Complete decision trail — every agent action logged</p>
            </div>

            {/* Stats row */}
            {stats && (
                <div className="grid grid-cols-4 gap-3">
                    {[
                        { label: 'Total Actions', value: stats.total_actions_logged ?? 0 },
                        { label: 'Successful', value: stats.successful_actions ?? 0 },
                        { label: 'Failed', value: stats.failed_actions ?? 0 },
                        { label: 'Today Spend', value: `$${(stats.daily_spend_usd ?? 0).toFixed(2)}` },
                    ].map(({ label, value }) => (
                        <div key={label} className="glass-card p-4 text-center">
                            <p className="text-xl font-bold text-white">{value}</p>
                            <p className="text-xs text-slate-500 mt-0.5">{label}</p>
                        </div>
                    ))}
                </div>
            )}

            {/* Controls */}
            <div className="flex items-center gap-3">
                <Filter size={14} className="text-slate-500" />
                <div className="flex gap-2 flex-wrap">
                    {AGENTS.map(a => (
                        <button key={a} onClick={() => setAgentFilter(a)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 border ${agentFilter === a ? 'bg-brand-600/20 text-brand-400 border-brand-500/30' : 'btn-ghost text-slate-400 border-white/[0.08]'
                                }`}>
                            {a || 'All Agents'}
                        </button>
                    ))}
                </div>
                <button onClick={fetchAudit} className="ml-auto btn-ghost flex items-center gap-1.5 text-xs">
                    <RefreshCw size={13} />Refresh
                </button>
            </div>

            {/* Audit table */}
            <div className="glass-card overflow-hidden">
                <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
                    <span className="text-sm font-medium text-slate-300">
                        {total > 0 ? `${entries.length} of ${total} entries` : 'No entries yet'}
                    </span>
                    <span className="text-xs text-slate-500">Latest first</span>
                </div>
                {loading ? (
                    <div className="py-12 text-center text-slate-500">Loading audit trail…</div>
                ) : entries.length === 0 ? (
                    <div className="py-12 text-center">
                        <ScrollText size={32} className="text-slate-700 mx-auto mb-3" />
                        <p className="text-slate-500 text-sm">No audit entries yet.</p>
                        <p className="text-slate-600 text-xs mt-1">Agent actions will appear here once you submit a goal.</p>
                    </div>
                ) : (
                    <div className="divide-y divide-white/[0.04]">
                        {entries.map((entry, i) => (
                            <div key={entry.id || i} className="px-5 py-3.5 hover:bg-white/[0.02] transition-colors animate-fade-in">
                                <div className="flex items-start gap-3">
                                    <div className="mt-0.5">{outcomeIcon(entry.outcome)}</div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap mb-1">
                                            <span className={`text-sm font-semibold ${agentColor(entry.agent_name)}`}>{entry.agent_name}</span>
                                            <span className="text-slate-400 text-sm">→</span>
                                            <span className="text-sm text-slate-200 font-medium">{entry.action}</span>
                                            {entry.cost_impact > 0 && (
                                                <span className="badge badge-yellow ml-auto">${entry.cost_impact.toFixed(4)}</span>
                                            )}
                                        </div>
                                        {entry.reasoning && (
                                            <p className="text-xs text-slate-500 leading-relaxed mb-1 line-clamp-2">{entry.reasoning}</p>
                                        )}
                                        <div className="flex items-center gap-3">
                                            <span className={`badge ${entry.outcome === 'success' ? 'badge-green' : entry.outcome === 'pending' ? 'badge-gray' : 'badge-red'}`}>
                                                {entry.outcome}
                                            </span>
                                            <span className="text-xs text-slate-600">{entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}</span>
                                            <span className="text-xs font-mono text-slate-700">{entry.id?.slice(0, 8)}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
