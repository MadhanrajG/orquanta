import { useState, useEffect } from 'react'
import { Clock, Plus, Trash2, RefreshCw, Play, Pause, ChevronDown, ChevronRight, CheckCircle, AlertCircle } from 'lucide-react'
import { useAuth } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

const CRON_PRESETS = [
    { label: 'Every hour',          expr: '0 * * * *' },
    { label: 'Every 6 hours',       expr: '0 */6 * * *' },
    { label: 'Every day at 9am',    expr: '0 9 * * *' },
    { label: 'Every day at midnight', expr: '0 0 * * *' },
    { label: 'Every Monday 2am',    expr: '0 2 * * 1' },
    { label: 'Every 15 minutes',    expr: '*/15 * * * *' },
    { label: '1st of every month',  expr: '0 0 1 * *' },
    { label: 'Custom…',             expr: '' },
]

const GPU_TYPES = ['A100', 'H100', 'A10G', 'L4', 'T4', 'V100']

const DEFAULT_FORM = {
    goal: '',
    cron_expr: '0 9 * * *',
    budget_usd: 50,
    gpu_type: 'A100',
    description: '',
    enabled: true,
    notify_channels: ['email', 'in_app'],
}

export default function SchedulesPage() {
    const { token } = useAuth()
    const [schedules, setSchedules] = useState([])
    const [loading, setLoading] = useState(true)
    const [form, setForm] = useState(DEFAULT_FORM)
    const [customCron, setCustomCron] = useState(false)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState('')
    const [success, setSuccess] = useState('')
    const [expandedRuns, setExpandedRuns] = useState(null)
    const [runs, setRuns] = useState({})
    const [toggling, setToggling] = useState(null)
    const [showForm, setShowForm] = useState(false)

    useEffect(() => { fetchSchedules() }, [])

    const fetchSchedules = async () => {
        setLoading(true)
        try {
            const res = await fetch(`${API}/api/v1/schedules`, {
                headers: { Authorization: `Bearer ${token}` },
            })
            if (res.ok) setSchedules(await res.json())
        } catch { /* non-fatal */ }
        finally { setLoading(false) }
    }

    const handleCreate = async (e) => {
        e.preventDefault()
        setError('')
        if (!form.goal.trim()) { setError('Goal is required'); return }
        if (!form.cron_expr.trim()) { setError('Cron expression is required'); return }
        setSubmitting(true)
        try {
            const res = await fetch(`${API}/api/v1/schedules`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ ...form, budget_usd: Number(form.budget_usd) }),
            })
            if (res.ok) {
                setForm(DEFAULT_FORM)
                setCustomCron(false)
                setShowForm(false)
                setSuccess('Schedule created')
                setTimeout(() => setSuccess(''), 3000)
                fetchSchedules()
            } else {
                const err = await res.json().catch(() => ({}))
                setError(err.detail || 'Failed to create schedule')
            }
        } catch { setError('Network error') }
        finally { setSubmitting(false) }
    }

    const handleDelete = async (id) => {
        try {
            await fetch(`${API}/api/v1/schedules/${id}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
            })
            setSchedules(ss => ss.filter(s => s.id !== id))
            if (expandedRuns === id) setExpandedRuns(null)
        } catch { /* non-fatal */ }
    }

    const handleToggleEnabled = async (sched) => {
        setToggling(sched.id)
        try {
            const res = await fetch(`${API}/api/v1/schedules/${sched.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ enabled: !sched.enabled }),
            })
            if (res.ok) {
                const updated = await res.json()
                setSchedules(ss => ss.map(s => s.id === sched.id ? updated : s))
            }
        } catch { /* non-fatal */ }
        finally { setToggling(null) }
    }

    const fetchRuns = async (id) => {
        try {
            const res = await fetch(`${API}/api/v1/schedules/${id}/runs`, {
                headers: { Authorization: `Bearer ${token}` },
            })
            if (res.ok) {
                const data = await res.json()
                setRuns(r => ({ ...r, [id]: data }))
            }
        } catch { /* non-fatal */ }
    }

    const toggleRuns = (id) => {
        if (expandedRuns === id) {
            setExpandedRuns(null)
        } else {
            setExpandedRuns(id)
            fetchRuns(id)
        }
    }

    const setCronPreset = (expr) => {
        if (expr === '') {
            setCustomCron(true)
            setForm(f => ({ ...f, cron_expr: '' }))
        } else {
            setCustomCron(false)
            setForm(f => ({ ...f, cron_expr: expr }))
        }
    }

    const fmtDate = (iso) => iso ? new Date(iso).toLocaleString() : '—'

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-white">Schedules</h1>
                    <p className="text-slate-400 text-sm mt-0.5">Recurring GPU jobs on a cron expression</p>
                </div>
                <button
                    onClick={() => { setShowForm(f => !f); setError('') }}
                    className="btn-primary flex items-center gap-2 text-sm">
                    <Plus size={14} />
                    New Schedule
                </button>
            </div>

            {/* Feedback */}
            {error && (
                <div className="glass-card p-3 border border-red-500/30 bg-red-500/10 flex items-center gap-2">
                    <AlertCircle size={14} className="text-red-400 shrink-0" />
                    <p className="text-sm text-red-400">{error}</p>
                </div>
            )}
            {success && (
                <div className="glass-card p-3 border border-emerald-500/30 bg-emerald-500/10 flex items-center gap-2">
                    <CheckCircle size={14} className="text-emerald-400 shrink-0" />
                    <p className="text-sm text-emerald-400">{success}</p>
                </div>
            )}

            {/* Create form */}
            {showForm && (
                <div className="glass-card p-6 space-y-5">
                    <h3 className="text-white font-semibold">New Schedule</h3>
                    <form onSubmit={handleCreate} className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-300 mb-1.5">Goal</label>
                            <textarea
                                className="input-field text-sm resize-none"
                                rows={3}
                                placeholder="Fine-tune LLaMA 3 8B on customer support data and push to HuggingFace…"
                                value={form.goal}
                                onChange={e => setForm(f => ({ ...f, goal: e.target.value }))}
                                required
                            />
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-slate-300 mb-2">Schedule</label>
                            <div className="flex flex-wrap gap-2 mb-3">
                                {CRON_PRESETS.map(({ label, expr }) => {
                                    const isSelected = expr === '' ? customCron : (!customCron && form.cron_expr === expr)
                                    return (
                                        <button
                                            key={label}
                                            type="button"
                                            onClick={() => setCronPreset(expr)}
                                            className="text-xs px-3 py-1.5 rounded-full border transition-all"
                                            style={{
                                                background: isSelected ? 'rgba(82,113,245,0.2)' : 'rgba(255,255,255,0.04)',
                                                borderColor: isSelected ? 'rgba(82,113,245,0.6)' : 'rgba(255,255,255,0.1)',
                                                color: isSelected ? '#7a9bfa' : '#94a3b8',
                                                cursor: 'pointer',
                                            }}>
                                            {label}
                                        </button>
                                    )
                                })}
                            </div>
                            {customCron && (
                                <input
                                    className="input-field text-sm font-mono"
                                    placeholder='Cron expression, e.g. "0 2 * * MON"'
                                    value={form.cron_expr}
                                    onChange={e => setForm(f => ({ ...f, cron_expr: e.target.value }))}
                                    required
                                />
                            )}
                            {form.cron_expr && !customCron && (
                                <p className="text-xs text-slate-500 mt-1.5 font-mono">{form.cron_expr}</p>
                            )}
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-300 mb-1.5">GPU Type</label>
                                <select
                                    className="input-field text-sm"
                                    value={form.gpu_type}
                                    onChange={e => setForm(f => ({ ...f, gpu_type: e.target.value }))}>
                                    {GPU_TYPES.map(g => <option key={g} value={g}>{g}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-300 mb-1.5">Budget (USD)</label>
                                <input
                                    className="input-field text-sm"
                                    type="number"
                                    min={1}
                                    max={10000}
                                    step={1}
                                    value={form.budget_usd}
                                    onChange={e => setForm(f => ({ ...f, budget_usd: e.target.value }))}
                                />
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-slate-300 mb-1.5">Description <span className="text-slate-600">(optional)</span></label>
                            <input
                                className="input-field text-sm"
                                placeholder="e.g. Weekly fine-tune run"
                                value={form.description}
                                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                                maxLength={200}
                            />
                        </div>

                        <div className="flex gap-3">
                            <button type="submit" disabled={submitting} className="btn-primary flex items-center gap-2 text-sm">
                                {submitting ? <RefreshCw size={14} className="animate-spin" /> : <Clock size={14} />}
                                {submitting ? 'Creating…' : 'Create Schedule'}
                            </button>
                            <button type="button" onClick={() => { setShowForm(false); setError('') }} className="btn-ghost text-sm">
                                Cancel
                            </button>
                        </div>
                    </form>
                </div>
            )}

            {/* Schedule list */}
            {loading
                ? <div className="flex justify-center py-16"><RefreshCw size={20} className="animate-spin text-slate-500" /></div>
                : schedules.length === 0
                    ? (
                        <div className="glass-card p-12 text-center">
                            <Clock size={36} className="text-slate-600 mx-auto mb-3" />
                            <p className="text-slate-400 font-medium">No schedules yet</p>
                            <p className="text-slate-600 text-sm mt-1">Create one above to run GPU jobs on a recurring basis.</p>
                        </div>
                    )
                    : (
                        <div className="space-y-3">
                            {schedules.map(s => (
                                <div key={s.id} className="glass-card p-5 space-y-3">
                                    {/* Top row */}
                                    <div className="flex items-start gap-4">
                                        {/* Enabled toggle */}
                                        <button
                                            type="button"
                                            onClick={() => handleToggleEnabled(s)}
                                            disabled={toggling === s.id}
                                            title={s.enabled ? 'Pause schedule' : 'Resume schedule'}
                                            style={{
                                                position: 'relative',
                                                display: 'inline-block',
                                                width: 40,
                                                height: 22,
                                                borderRadius: 22,
                                                border: 'none',
                                                cursor: 'pointer',
                                                flexShrink: 0,
                                                marginTop: 2,
                                                background: s.enabled ? 'rgba(82,113,245,0.85)' : 'rgba(100,116,139,0.4)',
                                                transition: 'background 0.2s',
                                                padding: 0,
                                                opacity: toggling === s.id ? 0.5 : 1,
                                            }}>
                                            <span style={{
                                                position: 'absolute',
                                                top: 2,
                                                left: s.enabled ? 20 : 2,
                                                width: 18,
                                                height: 18,
                                                borderRadius: '50%',
                                                background: 'white',
                                                transition: 'left 0.2s',
                                                boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                                            }} />
                                        </button>

                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <p className="text-white font-medium text-sm leading-snug">{s.goal.length > 100 ? s.goal.slice(0, 100) + '…' : s.goal}</p>
                                                {!s.enabled && (
                                                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(100,116,139,0.2)', color: '#94a3b8' }}>Paused</span>
                                                )}
                                            </div>
                                            <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs text-slate-500">
                                                <span className="font-mono text-slate-400">{s.cron_expr}</span>
                                                <span className="text-slate-600">·</span>
                                                <span>{s.cron_description}</span>
                                                <span className="text-slate-600">·</span>
                                                <span>{s.gpu_type}</span>
                                                <span className="text-slate-600">·</span>
                                                <span>${s.budget_usd} budget</span>
                                            </div>
                                            {s.description && <p className="text-xs text-slate-600 mt-1">{s.description}</p>}
                                        </div>

                                        <div className="flex items-center gap-2 shrink-0">
                                            <button
                                                onClick={() => handleToggleEnabled(s)}
                                                disabled={toggling === s.id}
                                                className="btn-ghost flex items-center gap-1 text-xs px-3 py-1.5"
                                                title={s.enabled ? 'Pause' : 'Resume'}>
                                                {toggling === s.id
                                                    ? <RefreshCw size={12} className="animate-spin" />
                                                    : s.enabled ? <Pause size={12} /> : <Play size={12} />}
                                                {s.enabled ? 'Pause' : 'Resume'}
                                            </button>
                                            <button
                                                onClick={() => handleDelete(s.id)}
                                                className="btn-ghost text-red-400 hover:text-red-300 flex items-center gap-1 text-xs px-3 py-1.5">
                                                <Trash2 size={12} /> Delete
                                            </button>
                                        </div>
                                    </div>

                                    {/* Stats row */}
                                    <div className="flex flex-wrap gap-4 text-xs pl-12">
                                        <span className="text-slate-500">
                                            <span className="text-slate-400">Next run:</span> {fmtDate(s.next_run)}
                                        </span>
                                        <span className="text-slate-500">
                                            <span className="text-slate-400">Last run:</span> {fmtDate(s.last_run)}
                                        </span>
                                        {s.last_status && (
                                            <span style={{ color: s.last_status === 'triggered' ? '#34d399' : '#f87171' }}>
                                                {s.last_status}
                                            </span>
                                        )}
                                        <span className="text-slate-600">{s.run_count} runs total</span>
                                    </div>

                                    {/* Run history toggle */}
                                    <div className="pl-12">
                                        <button
                                            onClick={() => toggleRuns(s.id)}
                                            className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition-colors"
                                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                                            {expandedRuns === s.id ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                                            Run history
                                        </button>

                                        {expandedRuns === s.id && (
                                            <div className="mt-2 space-y-1">
                                                {(runs[s.id] || []).length === 0
                                                    ? <p className="text-xs text-slate-600">No runs yet.</p>
                                                    : [...(runs[s.id] || [])].reverse().map(r => (
                                                        <div key={r.run_id} className="flex items-center gap-3 py-1.5 border-b border-white/[0.04] text-xs">
                                                            <span style={{ color: r.status === 'triggered' ? '#34d399' : '#94a3b8', width: 64, flexShrink: 0 }}>
                                                                {r.status}
                                                            </span>
                                                            <span className="text-slate-400 font-mono shrink-0">{r.job_id}</span>
                                                            <span className="text-slate-600">{fmtDate(r.fired_at)}</span>
                                                        </div>
                                                    ))
                                                }
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )
            }
        </div>
    )
}
