import { useState } from 'react'
import { User, Key, Bell, Shield, Save, Eye, EyeOff, Copy, RefreshCw, CheckCircle } from 'lucide-react'
import { useAuth } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

export default function ProfilePage() {
    const { user, token } = useAuth()
    const [tab, setTab] = useState('profile')
    const [saving, setSaving] = useState(false)
    const [saved, setSaved] = useState(false)
    const [showPass, setShowPass] = useState(false)
    const [apiKeyCopied, setApiKeyCopied] = useState(false)

    const [profileForm, setProfileForm] = useState({
        full_name: user?.name || '',
        email: user?.email || '',
    })
    const [passForm, setPassForm] = useState({ current: '', next: '', confirm: '' })
    const [error, setError] = useState('')

    const apiKey = token ? `oq-${token.slice(0, 24)}` : 'oq-xxxx-login-to-view'

    const handleSaveProfile = async (e) => {
        e.preventDefault(); setSaving(true); setError('')
        try {
            await new Promise(r => setTimeout(r, 600)) // simulated save
            setSaved(true); setTimeout(() => setSaved(false), 2500)
        } catch { setError('Failed to save profile') }
        finally { setSaving(false) }
    }

    const handleChangePassword = async (e) => {
        e.preventDefault(); setError('')
        if (passForm.next !== passForm.confirm) { setError('Passwords do not match'); return }
        if (passForm.next.length < 8) { setError('Password must be at least 8 characters'); return }
        setSaving(true)
        try {
            const res = await fetch(`${API}/api/v1/auth/change-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ current_password: passForm.current, new_password: passForm.next }),
            })
            if (!res.ok) throw new Error('Current password incorrect')
            setSaved(true); setPassForm({ current: '', next: '', confirm: '' })
            setTimeout(() => setSaved(false), 2500)
        } catch (err) { setError(err.message) }
        finally { setSaving(false) }
    }

    const copyApiKey = () => {
        navigator.clipboard.writeText(token || '')
        setApiKeyCopied(true); setTimeout(() => setApiKeyCopied(false), 2000)
    }

    const TABS = [
        { id: 'profile', label: 'Profile', Icon: User },
        { id: 'security', label: 'Security', Icon: Shield },
        { id: 'api', label: 'API Keys', Icon: Key },
        { id: 'notifications', label: 'Notifications', Icon: Bell },
    ]

    return (
        <div className="space-y-6 animate-fade-in" style={{ maxWidth: 720 }}>
            <div>
                <h1 className="text-2xl font-bold text-white">Settings</h1>
                <p className="text-slate-400 text-sm mt-0.5">Manage your account, security, and API access</p>
            </div>

            {/* Tab bar */}
            <div className="flex gap-1 border-b border-white/[0.08] pb-0">
                {TABS.map(({ id, label, Icon }) => (
                    <button key={id} onClick={() => { setTab(id); setError(''); setSaved(false) }}
                        className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-all duration-200 border-b-2 -mb-px"
                        style={{
                            color: tab === id ? '#7a9bfa' : '#94a3b8',
                            borderBottomColor: tab === id ? '#7a9bfa' : 'transparent',
                            background: 'none', border: 'none',
                            borderBottom: tab === id ? '2px solid #7a9bfa' : '2px solid transparent',
                            cursor: 'pointer',
                        }}>
                        <Icon size={14} />
                        {label}
                    </button>
                ))}
            </div>

            {/* Error / Success */}
            {error && (
                <div className="glass-card p-3 border border-red-500/30 bg-red-500/10">
                    <p className="text-sm text-red-400">{error}</p>
                </div>
            )}
            {saved && (
                <div className="glass-card p-3 border border-emerald-500/30 bg-emerald-500/10 flex items-center gap-2">
                    <CheckCircle size={14} className="text-emerald-400" />
                    <p className="text-sm text-emerald-400">Saved successfully</p>
                </div>
            )}

            {/* Profile Tab */}
            {tab === 'profile' && (
                <form onSubmit={handleSaveProfile} className="glass-card p-6 space-y-5">
                    <div className="flex items-center gap-4 mb-2">
                        <div className="user-avatar" style={{ width: 52, height: 52, fontSize: 20 }}>
                            {user?.email?.[0]?.toUpperCase() || 'A'}
                        </div>
                        <div>
                            <p className="text-white font-semibold">{user?.email || 'admin@orquanta.ai'}</p>
                            <p className="text-xs text-slate-500 mt-0.5">OrQuanta Member</p>
                        </div>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-300 mb-1.5">Full Name</label>
                        <input className="input-field" placeholder="Your full name"
                            value={profileForm.full_name}
                            onChange={e => setProfileForm(f => ({ ...f, full_name: e.target.value }))} />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-300 mb-1.5">Email Address</label>
                        <input className="input-field" type="email" placeholder="you@example.com"
                            value={profileForm.email}
                            onChange={e => setProfileForm(f => ({ ...f, email: e.target.value }))} />
                    </div>
                    <button type="submit" className="btn-primary flex items-center gap-2" disabled={saving}>
                        {saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
                        {saving ? 'Saving...' : 'Save Profile'}
                    </button>
                </form>
            )}

            {/* Security Tab */}
            {tab === 'security' && (
                <form onSubmit={handleChangePassword} className="glass-card p-6 space-y-5">
                    <h3 className="text-white font-semibold">Change Password</h3>
                    {[
                        { label: 'Current Password', field: 'current' },
                        { label: 'New Password', field: 'next' },
                        { label: 'Confirm New Password', field: 'confirm' },
                    ].map(({ label, field }) => (
                        <div key={field}>
                            <label className="block text-sm font-medium text-slate-300 mb-1.5">{label}</label>
                            <div className="relative">
                                <input className="input-field pr-10"
                                    type={showPass ? 'text' : 'password'}
                                    value={passForm[field]}
                                    onChange={e => setPassForm(f => ({ ...f, [field]: e.target.value }))}
                                    required autoComplete="off" />
                                <button type="button" onClick={() => setShowPass(s => !s)}
                                    style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#64748b', cursor: 'pointer' }}>
                                    {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                                </button>
                            </div>
                        </div>
                    ))}
                    <div className="glass-card p-3 bg-white/[0.03] text-xs text-slate-500 space-y-1">
                        <p>Password requirements:</p>
                        <p>- Minimum 8 characters</p>
                        <p>- Mix of letters and numbers recommended</p>
                    </div>
                    <button type="submit" className="btn-primary flex items-center gap-2" disabled={saving}>
                        {saving ? <RefreshCw size={14} className="animate-spin" /> : <Shield size={14} />}
                        {saving ? 'Updating...' : 'Update Password'}
                    </button>
                </form>
            )}

            {/* API Keys Tab */}
            {tab === 'api' && (
                <div className="space-y-4">
                    <div className="glass-card p-6">
                        <h3 className="text-white font-semibold mb-1">Your API Token</h3>
                        <p className="text-xs text-slate-500 mb-4">Use this token to authenticate API requests. Keep it secret.</p>
                        <div className="flex items-center gap-2">
                            <code className="flex-1 input-field font-mono text-xs py-2 text-slate-300 overflow-hidden text-ellipsis whitespace-nowrap">
                                {apiKey}
                            </code>
                            <button onClick={copyApiKey} className="btn-ghost flex items-center gap-1.5 text-xs whitespace-nowrap" style={{ minWidth: 80 }}>
                                {apiKeyCopied ? <CheckCircle size={13} className="text-emerald-400" /> : <Copy size={13} />}
                                {apiKeyCopied ? 'Copied' : 'Copy'}
                            </button>
                        </div>
                        <p className="text-xs text-slate-600 mt-3">
                            Use as: <code className="text-slate-400">Authorization: Bearer {'<token>'}</code>
                        </p>
                    </div>
                    <div className="glass-card p-5">
                        <h3 className="text-white font-semibold mb-2 text-sm">API Documentation</h3>
                        <p className="text-xs text-slate-500 mb-3">Full REST API with WebSocket streaming support.</p>
                        <a href="/docs" target="_blank" rel="noopener noreferrer" className="btn-ghost text-sm inline-flex items-center gap-2">
                            Open Swagger Docs
                        </a>
                    </div>
                </div>
            )}

            {/* Notifications Tab */}
            {tab === 'notifications' && (
                <div className="glass-card p-6 space-y-5">
                    <h3 className="text-white font-semibold">Notification Preferences</h3>
                    {[
                        { label: 'Job completion alerts', desc: 'Get notified when your GPU jobs finish' },
                        { label: 'Cost threshold warnings', desc: 'Alert when daily spend exceeds 80% of budget' },
                        { label: 'Agent failure alerts', desc: 'Notify on healing agent interventions' },
                        { label: 'Weekly spend summary', desc: 'Email digest every Monday at 9am' },
                    ].map(({ label, desc }) => (
                        <div key={label} className="flex items-center justify-between py-2 border-b border-white/[0.04]">
                            <div>
                                <p className="text-sm text-white font-medium">{label}</p>
                                <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                            </div>
                            <label style={{ position: 'relative', display: 'inline-block', width: 40, height: 22, cursor: 'pointer', flexShrink: 0 }}>
                                <input type="checkbox" defaultChecked style={{ opacity: 0, width: 0, height: 0 }} />
                                <span style={{ position: 'absolute', inset: 0, background: 'rgba(82,113,245,0.7)', borderRadius: 22, transition: '0.2s' }} />
                            </label>
                        </div>
                    ))}
                    <button className="btn-primary flex items-center gap-2">
                        <Save size={14} />Save Preferences
                    </button>
                </div>
            )}
        </div>
    )
}
