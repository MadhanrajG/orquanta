import { useState, useEffect } from 'react'
import { Plus, RefreshCw, X, Server, Clock, CheckCircle, AlertCircle, Circle } from 'lucide-react'
import { useAuth } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

const STATUS_BADGE = {
    queued: 'badge-yellow', running: 'badge-blue', completed: 'badge-green',
    failed: 'badge-red', cancelled: 'badge-gray', pending: 'badge-gray',
}

const GPU_COLORS = { H100: 'text-purple-400', A100: 'text-brand-400', T4: 'text-emerald-400', A10G: 'text-amber-400' }

export default function JobManager() {
    const { token } = useAuth()
    const [jobs, setJobs] = useState([])
    const [queueStatus, setQueueStatus] = useState({})
    const [loading, setLoading] = useState(true)
    const [showForm, setShowForm] = useState(false)
    const [form, setForm] = useState({ intent: '', gpu_type: 'H100', gpu_count: 1, provider: 'aws', required_vram_gb: 80, max_cost_usd: 500, max_runtime_minutes: 120 })
    const [submitting, setSubmitting] = useState(false)
    const [statusFilter, setStatusFilter] = useState('')

    const headers = { Authorization: `Bearer ${token}` }

    const fetchJobs = async () => {
        try {
            const url = `${API}/api/v1/jobs${statusFilter ? `?status=${statusFilter}` : ''}`
            const res = await fetch(url, { headers })
            if (res.ok) { const d = await res.json(); setJobs(d.jobs || []); setQueueStatus(d.queue_status || {}) }
        } catch { }
        finally { setLoading(false) }
    }

    useEffect(() => { fetchJobs(); const t = setInterval(fetchJobs, 5000); return () => clearInterval(t) }, [statusFilter])

    const handleSubmit = async (e) => {
        e.preventDefault(); setSubmitting(true)
        try {
            await fetch(`${API}/api/v1/jobs`, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(form) })
            setShowForm(false); fetchJobs()
        } catch { } finally { setSubmitting(false) }
    }

    const cancelJob = async (id) => {
        await fetch(`${API}/api/v1/jobs/${id}`, { method: 'DELETE', headers })
        fetchJobs()
    }

    return (
        <div className="space-y-6 animate-fade-in">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-white">Job Manager</h1>
                    <p className="text-slate-400 text-sm mt-0.5">GPU job queue with {queueStatus.queued_jobs ?? 0} jobs queued</p>
                </div>
                <button id="new-job-btn" onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2">
                    <Plus size={16} />New Job
                </button>
            </div>

            {/* Queue Stats */}
            <div className="grid grid-cols-4 gap-3">
                {[
                    { label: 'Total Jobs', value: queueStatus.total_jobs ?? jobs.length },
                    { label: 'Queued', value: queueStatus.queued_jobs ?? 0 },
                    { label: 'Active Bins', value: queueStatus.active_bins ?? 0 },
                    { label: 'Running', value: jobs.filter(j => j.status === 'running').length },
                ].map(({ label, value }) => (
                    <div key={label} className="glass-card p-4 text-center">
                        <p className="text-xl font-bold text-white">{value}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{label}</p>
                    </div>
                ))}
            </div>

            {/* Filters */}
            <div className="flex gap-2">
                {['', 'queued', 'running', 'completed', 'failed'].map(s => (
                    <button key={s} onClick={() => setStatusFilter(s)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 border ${statusFilter === s ? 'bg-brand-600/20 text-brand-400 border-brand-500/30' : 'btn-ghost text-slate-400 border-white/[0.08]'
                            }`}>
                        {s || 'All'}
                    </button>
                ))}
                <button onClick={fetchJobs} className="ml-auto btn-ghost flex items-center gap-1.5 text-xs">
                    <RefreshCw size={13} />Refresh
                </button>
            </div>

            {/* Job Table */}
            <div className="glass-card overflow-hidden">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-white/[0.06]">
                            {['Job ID', 'Intent', 'GPU', 'Provider', 'Priority', 'Status', 'Actions'].map(h => (
                                <th key={h} className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500">Loading…</td></tr>
                        ) : jobs.length === 0 ? (
                            <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500">No jobs found. Create one above.</td></tr>
                        ) : jobs.map(job => (
                            <tr key={job.job_id} className="table-row">
                                <td className="px-4 py-3 font-mono text-xs text-slate-400">{job.job_id}</td>
                                <td className="px-4 py-3 text-slate-300 max-w-[200px] truncate">{job.intent}</td>
                                <td className="px-4 py-3">
                                    <span className={`font-semibold text-xs ${GPU_COLORS[job.gpu_type] || 'text-slate-400'}`}>
                                        {job.gpu_count}×{job.gpu_type}
                                    </span>
                                </td>
                                <td className="px-4 py-3 text-slate-400 text-xs">{job.provider}</td>
                                <td className="px-4 py-3">
                                    <div className="w-16 h-1 bg-white/[0.06] rounded-full overflow-hidden">
                                        <div className="h-full bg-brand-500 rounded-full" style={{ width: `${(job.priority || 0.5) * 100}%` }} />
                                    </div>
                                </td>
                                <td className="px-4 py-3">
                                    <span className={`badge ${STATUS_BADGE[job.status] || 'badge-gray'}`}>{job.status}</span>
                                </td>
                                <td className="px-4 py-3">
                                    {['queued', 'running', 'pending'].includes(job.status) && (
                                        <button onClick={() => cancelJob(job.job_id)} className="text-slate-600 hover:text-red-400 transition-colors" title="Cancel">
                                            <X size={14} />
                                        </button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* New Job Modal */}
            {showForm && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="glass-card p-6 w-full max-w-lg animate-slide-up">
                        <div className="flex items-center justify-between mb-5">
                            <h3 className="font-semibold text-white">Create GPU Job</h3>
                            <button onClick={() => setShowForm(false)} className="text-slate-500 hover:text-white"><X size={18} /></button>
                        </div>
                        <form id="job-form" onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-300 mb-1.5">Intent / Description</label>
                                <textarea className="input-field min-h-[80px] resize-none" placeholder="e.g. Train ResNet-50 on ImageNet"
                                    value={form.intent} onChange={e => setForm(f => ({ ...f, intent: e.target.value }))} required />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                {[
                                    { label: 'GPU Type', field: 'gpu_type', type: 'select', options: ['H100', 'A100', 'T4', 'A10G'] },
                                    { label: 'Provider', field: 'provider', type: 'select', options: ['aws', 'gcp', 'azure', 'coreweave'] },
                                    { label: 'GPU Count', field: 'gpu_count', type: 'number', min: 1, max: 64 },
                                    { label: 'VRAM (GB)', field: 'required_vram_gb', type: 'number', min: 1 },
                                    { label: 'Max Cost ($)', field: 'max_cost_usd', type: 'number', min: 0 },
                                    { label: 'Runtime (min)', field: 'max_runtime_minutes', type: 'number', min: 1 },
                                ].map(({ label, field, type, options, min, max }) => (
                                    <div key={field}>
                                        <label className="block text-xs font-medium text-slate-400 mb-1">{label}</label>
                                        {type === 'select' ? (
                                            <select className="input-field text-sm" value={form[field]} onChange={e => setForm(f => ({ ...f, [field]: e.target.value }))}>
                                                {options.map(o => <option key={o}>{o}</option>)}
                                            </select>
                                        ) : (
                                            <input className="input-field text-sm" type="number" min={min} max={max}
                                                value={form[field]} onChange={e => setForm(f => ({ ...f, [field]: parseFloat(e.target.value) }))} />
                                        )}
                                    </div>
                                ))}
                            </div>
                            <div className="flex gap-3 pt-2">
                                <button type="button" onClick={() => setShowForm(false)} className="btn-ghost flex-1">Cancel</button>
                                <button type="submit" className="btn-primary flex-1" disabled={submitting}>
                                    {submitting ? <RefreshCw size={14} className="animate-spin mr-2 inline" /> : null}
                                    {submitting ? 'Scheduling…' : 'Schedule Job'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    )
}
