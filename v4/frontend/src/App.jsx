import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate } from 'react-router-dom'
import { useState, useEffect, createContext, useContext, Component } from 'react'
import {
    LayoutDashboard, Target, Server, DollarSign,
    ScrollText, Cpu, Zap, LogOut, Menu, X, AlertTriangle, Leaf, Gift, BarChart2,
    Settings, HelpCircle, Loader2, CreditCard, Globe, Brain, Wand2, Crown, Clock
} from 'lucide-react'
import Dashboard from './pages/Dashboard.jsx'
import GoalSubmit from './pages/GoalSubmit.jsx'
import VeroControl from "./pages/VeroControl.jsx"
import AgentMonitor from './pages/AgentMonitor.jsx'
import JobManager from './pages/JobManager.jsx'
import CostAnalytics from './pages/CostAnalytics.jsx'
import AuditLog from './pages/AuditLog.jsx'
import FreeTier from './pages/FreeTier.jsx'
import LivePricing from './pages/LivePricing.jsx'
import ProfilePage from './pages/ProfilePage.jsx'
import SchedulesPage from './pages/SchedulesPage.jsx'
import BillingPage from './pages/BillingPage.jsx'
import NemoClawPage from './pages/NemoClawPage.jsx'
import UIXAgentPage from './pages/UIXAgentPage.jsx'
import HelpPage from './pages/HelpPage.jsx'
import OrQuantaAssistant from './components/OrQuantaAssistant.jsx'
import { CommandPalette, ShortcutsModal, useCommandPalette } from './components/CommandPalette.jsx'

/* ── Error Boundary — catches unhandled render errors across all routes ── */
class ErrorBoundary extends Component {
    constructor(props) { super(props); this.state = { hasError: false, error: null } }
    static getDerivedStateFromError(error) { return { hasError: true, error } }
    componentDidCatch(error, info) {
        // Log to backend in production; console in dev only
        if (import.meta.env.DEV) {
            console.error('[OrQuanta] Unhandled render error:', error, info)
        }
    }
    render() {
        if (this.state.hasError) return (
            <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#050608', color: '#e2e8f0', flexDirection: 'column', gap: 16, padding: 24 }}>
                <AlertTriangle size={40} color="#f59e0b" />
                <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', color: 'white' }}>Something went wrong</h2>
                <p style={{ color: '#94a3b8', fontSize: 14, maxWidth: 400, textAlign: 'center' }}>
                    An unexpected error occurred. Please refresh the page or contact support.
                </p>
                <button
                    onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload() }}
                    style={{ padding: '10px 24px', background: 'linear-gradient(135deg,#3a52eb,#7a9bfa)', border: 'none', borderRadius: 8, color: 'white', cursor: 'pointer', fontSize: 14 }}
                >
                    Reload App
                </button>
            </div>
        )
        return this.props.children
    }
}

/* ── JWT expiry helper — decode exp claim without a library ── */
function isTokenExpired(token) {
    if (!token) return true
    try {
        const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
        return payload.exp ? Date.now() / 1000 > payload.exp : false
    } catch { return true }
}

/* ── Auth Context ── */
export const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

function AuthProvider({ children }) {
    const [token, setToken] = useState(() => {
        const t = localStorage.getItem('orquanta_token')
        // Evict expired token on load — don't silently accept stale auth
        if (t && isTokenExpired(t)) {
            localStorage.removeItem('orquanta_token')
            localStorage.removeItem('orquanta_user')
            return null
        }
        return t
    })
    const [user, setUser] = useState(() => {
        try { return JSON.parse(localStorage.getItem('orquanta_user')) } catch { return null }
    })

    // OAuth redirect token capture — handles ?token=xxx from /auth/google or /auth/github
    useEffect(() => {
        const params = new URLSearchParams(window.location.search)
        const oauthToken = params.get('token')
        const oauthError = params.get('error')
        if (oauthToken) {
            localStorage.setItem('orquanta_token', oauthToken)
            setToken(oauthToken)
            window.history.replaceState({}, '', '/app')
        }
        if (oauthError) console.warn('OAuth error:', oauthError)
    }, [])

    // Proactively evict token when it expires during the session
    useEffect(() => {
        if (!token) return
        try {
            const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
            if (!payload.exp) return
            const msUntilExpiry = payload.exp * 1000 - Date.now()
            if (msUntilExpiry <= 0) { logout(); return }
            const t = setTimeout(logout, msUntilExpiry)
            return () => clearTimeout(t)
        } catch { /* ignore malformed token */ }
    }, [token])

    const login = async (email, password) => {
        const res = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
            signal: AbortSignal.timeout(10000),
        })
        if (!res.ok) {
            const err = await res.json().catch(() => ({}))
            throw new Error(err.error || 'Invalid credentials')
        }
        const data = await res.json()
        setToken(data.access_token)
        // Decode JWT to get role without a library
        let role = 'member'
        try {
            const payload = JSON.parse(atob(data.access_token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
            role = payload.role || 'member'
        } catch { /* ignore */ }
        const u = { email, role }
        setUser(u)
        localStorage.setItem('orquanta_token', data.access_token)
        localStorage.setItem('orquanta_user', JSON.stringify(u))
    }

    const logout = () => {
        setToken(null); setUser(null)
        localStorage.removeItem('orquanta_token')
        localStorage.removeItem('orquanta_user')
    }

    return (
        <AuthContext.Provider value={{ token, user, login, logout, isAuth: !!token }}>
            {children}
        </AuthContext.Provider>
    )
}

/* ── Login Page ── */
function LoginPage() {
    const { login } = useAuth()
    const [mode, setMode] = useState('login')
    const [name, setName] = useState('')
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)
    const switchMode = (m) => { setMode(m); setError('') }

    const handleLogin = async (e) => {
        e.preventDefault(); setError(''); setLoading(true)
        try { await login(email, password) }
        catch (err) { setError(err.message || 'Invalid email or password') }
        finally { setLoading(false) }
    }

    const handleRegister = async (e) => {
        e.preventDefault(); setError(''); setLoading(true)
        try {
            const res = await fetch('/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, name }),
                signal: AbortSignal.timeout(10000),
            })
            if (!res.ok) {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || err.error || 'Registration failed')
            }
            await login(email, password)
        } catch (err) { setError(err.message || 'Registration failed') }
        finally { setLoading(false) }
    }

    return (
        <div className="auth-page">
            <div style={{ position: 'absolute', top: '20%', left: '20%', width: '500px', height: '500px', background: 'rgba(82,113,245,0.07)', borderRadius: '50%', filter: 'blur(100px)', pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', bottom: '20%', right: '20%', width: '350px', height: '350px', background: 'rgba(139,92,246,0.06)', borderRadius: '50%', filter: 'blur(80px)', pointerEvents: 'none' }} />
            <div style={{ width: '100%', maxWidth: '440px', padding: '0 16px', position: 'relative', zIndex: 1 }}>
                <div className="auth-card fade-in">
                    <div className="auth-logo">
                        {/* Value Proposition — GPU expert hero message */}
                        <div className="login-value-strip">
                            <div className="login-headline">$0.013 / hr</div>
                            <div className="login-subline">GPU Cloud · Orchestrated by 5 AI Agents · 67% Below AWS</div>
                            <div className="login-pills">
                                <span className="login-pill">Auto-Routing</span>
                                <span className="login-pill">NemoClaw AI</span>
                                <span className="login-pill">Cost Watcher</span>
                                <span className="login-pill">Audit Trail</span>
                            </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', justifyContent: 'center', marginBottom: '6px' }}>
                            <div style={{ width: 40, height: 40, background: 'linear-gradient(135deg,rgba(0,212,255,0.15),rgba(123,47,255,0.15))', border: '1px solid rgba(0,212,255,0.3)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <Cpu size={20} color="#00D4FF" />
                            </div>
                            <div style={{ textAlign: 'left' }}>
                                <div className="logo-text">OrQuanta</div>
                                <div className="logo-sub">Agentic GPU Cloud v1.0</div>
                            </div>
                        </div>
                    </div>
                    <div style={{ display: 'flex', background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: 4, marginBottom: 24, border: '1px solid rgba(255,255,255,0.08)' }}>
                        {[['login', 'Sign In'], ['register', 'Create Account']].map(([m, label]) => (
                            <button key={m} onClick={() => switchMode(m)} style={{
                                flex: 1, padding: '8px 0', borderRadius: 7, border: 'none', cursor: 'pointer',
                                fontSize: 14, fontWeight: 600, transition: 'all 0.2s',
                                background: mode === m ? 'linear-gradient(135deg,#3a52eb,#5a72fb)' : 'transparent',
                                color: mode === m ? '#fff' : 'var(--text-muted)',
                                boxShadow: mode === m ? '0 2px 12px rgba(58,82,235,0.4)' : 'none',
                            }}>{label}</button>
                        ))}
                    </div>
                    <h2 className="auth-title" style={{ marginBottom: 4 }}>
                        {mode === 'login' ? 'Welcome back' : 'Start for free'}
                    </h2>
                    <p className="auth-sub" style={{ marginBottom: 20 }}>
                        {mode === 'login' ? 'Sign in to manage your GPU infrastructure' : '14-day free trial. No credit card required'}
                    </p>
                    {error && (
                        <div className="alert alert-error" style={{ marginBottom: 16 }}>
                            <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
                            <span>{error}</span>
                        </div>
                    )}
                    <form onSubmit={mode === 'login' ? handleLogin : handleRegister}>
                        {mode === 'register' && (
                            <div className="input-group" style={{ marginBottom: 14 }}>
                                <label className="input-label">Full Name</label>
                                <input id="reg-name" type="text" value={name} onChange={e => setName(e.target.value)} required minLength={2} placeholder="Ada Lovelace" autoComplete="name" />
                            </div>
                        )}
                        <div className="input-group" style={{ marginBottom: 14 }}>
                            <label className="input-label">Email address</label>
                            <input id="auth-email" type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@company.ai" autoComplete="email" />
                        </div>
                        <div className="input-group" style={{ marginBottom: mode === 'register' ? 8 : 20 }}>
                            <label className="input-label">Password</label>
                            <input id="auth-password" type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} placeholder="Min. 8 characters" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
                        </div>
                        {mode === 'register' && (
                            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 18, lineHeight: 1.5 }}>By signing up you agree to our Terms of Service.</p>
                        )}
                        <button id="auth-submit" type="submit" className="btn btn-primary w-full btn-lg" disabled={loading} style={{ width: '100%' }}>
                            {loading
                                ? <><Loader2 size={15} style={{ animation: 'spin 0.8s linear infinite', display: 'inline', marginRight: 6, verticalAlign: 'middle' }} />{mode === 'login' ? 'Signing in...' : 'Creating account...'}</>
                                : mode === 'login' ? 'Sign In' : 'Create Free Account'
                            }
                        </button>
                    </form>

                    {/* OAuth SSO buttons */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '20px 0 12px' }}>
                        <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.08)' }} />
                        <span style={{ color: '#64748b', fontSize: 12 }}>or continue with</span>
                        <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.08)' }} />
                    </div>
                    <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
                        <a href="/auth/google/login" style={{
                            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                            gap: 8, padding: '10px 0', borderRadius: 8, border: '1px solid rgba(255,255,255,0.12)',
                            background: 'rgba(255,255,255,0.04)', color: '#e2e8f0', fontSize: 13,
                            textDecoration: 'none', fontWeight: 500,
                        }}>
                            <svg width="15" height="15" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
                            Google
                        </a>
                        <a href="/auth/github/login" style={{
                            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                            gap: 8, padding: '10px 0', borderRadius: 8, border: '1px solid rgba(255,255,255,0.12)',
                            background: 'rgba(255,255,255,0.04)', color: '#e2e8f0', fontSize: 13,
                            textDecoration: 'none', fontWeight: 500,
                        }}>
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="#e2e8f0"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
                            GitHub
                        </a>
                    </div>

                    <div style={{ marginTop: 4, paddingTop: 16, borderTop: '1px solid rgba(255,255,255,0.06)', textAlign: 'center' }}>
                        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                            Want to explore first?{' '}
                            <button
                                onClick={() => switchMode('register')}
                                style={{ color: '#7a9bfa', background: 'none', border: 'none', fontWeight: 600, fontSize: 13, cursor: 'pointer', padding: 0, textDecoration: 'underline', textUnderlineOffset: 2 }}
                            >
                                Start free trial
                            </button>
                        </p>
                    </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'center', gap: 20, marginTop: 18, flexWrap: 'wrap' }}>
                    {['Secure JWT Auth', 'Live in Seconds', 'Free 14-Day Trial'].map(b => (
                        <span key={b} style={{ fontSize: 12, color: 'var(--text-muted)' }}>{b}</span>
                    ))}
                </div>
            </div>
        </div>
    )
}

/* ── Carbon Tracker (Coming Soon) ── */
function CarbonTrackerPage() {
    return (
        <div className="space-y-6 animate-fade-in">
            <div>
                <h1 className="text-2xl font-bold text-white">Carbon Tracker</h1>
                <p className="text-slate-400 text-sm mt-0.5">Route workloads to the greenest regions automatically</p>
            </div>
            <div className="glass-card p-8 text-center relative overflow-hidden">
                <div className="absolute inset-0 opacity-5" style={{ background: 'radial-gradient(ellipse at 50% 0%, #00FF88, transparent 70%)' }} />
                <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'center' }}><Leaf size={52} color="#00FF88" /></div>
                <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', marginBottom: 12, color: 'white' }}>Carbon-Aware Scheduling</h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', lineHeight: 1.7, marginBottom: 28, maxWidth: 480, margin: '0 auto 28px' }}>
                    OrQuanta will automatically detect real-time carbon intensity per region
                    and shift your GPU jobs to the lowest-carbon available locations.
                </p>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '7px 20px', border: '1px solid rgba(0,255,136,0.3)', borderRadius: 999, background: 'rgba(0,255,136,0.06)', color: '#00FF88', fontSize: 13 }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#00FF88', display: 'inline-block', animation: 'pulse 2s infinite' }} />
                    In Development — Available in v1.1
                </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                    { icon: Zap, title: 'Real-Time Carbon Intensity', desc: 'gCO2/kWh tracked per region via ElectricityMaps API', color: '#00FF88' },
                    { icon: Globe, title: 'Green Region Routing', desc: 'Automatic job migration to lowest-carbon providers', color: '#00D4FF' },
                    { icon: BarChart2, title: 'Emissions Reporting', desc: 'Monthly carbon footprint reports & offset tracking', color: '#7B2FFF' },
                ].map(c => (
                    <div key={c.title} className="glass-card p-5" style={{ opacity: 0.75 }}>
                        <div style={{ marginBottom: 12 }}><c.icon size={28} color={c.color} /></div>
                        <h3 className="font-semibold text-white text-sm mb-1.5">{c.title}</h3>
                        <p className="text-xs text-slate-500 leading-relaxed">{c.desc}</p>
                        <div className="mt-3 h-0.5 rounded-full" style={{ background: `${c.color}30` }} />
                    </div>
                ))}
            </div>
        </div>
    )
}

/* ── Live savings from platform metrics ── */
function useLiveSavings() {
    const { token } = useAuth()
    const [savings, setSavings] = useState(null)
    useEffect(() => {
        if (!token) return
        let cancelled = false
        fetch('/api/v1/metrics/cost/dashboard', { headers: { Authorization: `Bearer ${token}` } })
            .then(r => r.ok ? r.json() : null)
            .then(d => {
                if (!d || cancelled) return
                const spent = d.governor_spend?.daily_spend_usd ?? 0
                // AWS on-demand is ~2.5× our routed price on average
                const awsEquivalent = spent * 2.5
                const saved = awsEquivalent - spent
                setSavings(saved > 0 ? `$${saved.toFixed(2)} saved` : 'Tracking savings…')
            })
            .catch(() => {})
        return () => { cancelled = true }
    }, [token])
    return savings
}

/* ── Navigation Sidebar ── */
const VeroIcon = () => <Crown size={16} style={{ minWidth: 16, flexShrink: 0 }} />

/* ── Grouped nav structure ── */
const NAV_GROUPS = [
  {
    label: 'Compute',
    items: [
      { to: '/',         icon: LayoutDashboard, label: 'Dashboard',     exact: true },
      { to: '/goals',    icon: Target,          label: 'Submit Goal' },
      { to: '/agents',   icon: Zap,             label: 'Agent Monitor',  badge: { text: 'LIVE', cls: 'nav-badge-cyan' }, dot: true },
      { to: '/jobs',      icon: Server,          label: 'Job Manager' },
      { to: '/schedules', icon: Clock,           label: 'Schedules' },
    ]
  },
  {
    label: 'Finance',
    items: [
      { to: '/costs',    icon: DollarSign,       label: 'Cost Analytics' },
      { to: '/pricing',  icon: BarChart2,        label: 'Live Pricing',  badge: { text: 'LIVE', cls: 'nav-badge-cyan' } },
      { to: '/billing',  icon: CreditCard,       label: 'Billing & Plans' },
      { to: '/free',     icon: Gift,             label: 'Free GPU',       badge: { text: 'FREE', cls: 'nav-badge-green' } },
    ]
  },
  {
    label: 'Intelligence',
    items: [
      { to: '/nemoclaw', icon: Brain,            label: 'NemoClaw',       badge: { text: 'AI', cls: 'nav-badge-violet' } },
      { to: '/vero',     icon: VeroIcon,         label: 'Vero',           badge: { text: 'META', cls: 'nav-badge-violet' } },
      { to: '/uix',      icon: Wand2,            label: 'UIXAgent' },
    ]
  },
  {
    label: 'Compliance',
    items: [
      { to: '/audit',    icon: ScrollText,       label: 'Audit Log' },
      { to: '/carbon',   icon: Leaf,             label: 'Carbon Tracker' },
    ]
  },
  {
    label: 'Account',
    items: [
      { to: '/settings', icon: Settings,         label: 'Settings' },
      { to: '/help',     icon: HelpCircle,       label: 'Help Center' },
    ]
  },
]

function Sidebar({ collapsed, onToggle, mobileOpen, onMobileClose }) {
    const { logout, user } = useAuth()
    const liveSavings = useLiveSavings()
    const w = collapsed ? 64 : 228

    return (
        <>
            {mobileOpen && (
                <div
                    onClick={onMobileClose}
                    style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 49, backdropFilter: 'blur(2px)' }}
                />
            )}
            <aside
                className="orq-sidebar"
                data-mobile-open={mobileOpen}
                style={{
                    width: w, minHeight: '100vh',
                    background: 'var(--surface-800)',
                    borderRight: '1px solid var(--border)',
                    display: 'flex', flexDirection: 'column',
                    position: 'fixed', top: 0, left: 0,
                    zIndex: 50,
                    transition: 'width 0.25s ease, transform 0.25s ease',
                    overflow: 'hidden',
                }}
            >
                {/* Logo */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '18px 14px 12px', borderBottom: '1px solid var(--border)', minHeight: 64 }}>
                    <div style={{
                        width: 32, height: 32, minWidth: 32,
                        background: 'linear-gradient(135deg,#00D4FF20,#7B2FFF20)',
                        border: '1px solid rgba(0,212,255,0.3)',
                        borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
                    }}>
                        <Cpu size={16} color="#00D4FF" />
                    </div>
                    {!collapsed && (
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontWeight: 800, fontSize: 13.5, color: 'var(--text-primary)', whiteSpace: 'nowrap', letterSpacing: '-0.02em' }}>OrQuanta</div>
                            <div style={{ fontSize: 9.5, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase', marginTop: 1 }}>GPU Cloud · AI-Powered</div>
                        </div>
                    )}
                    <button onClick={onToggle} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', flexShrink: 0, padding: 3, borderRadius: 6 }}>
                        {collapsed ? <Menu size={15} /> : <X size={15} />}
                    </button>
                </div>

                {/* Session savings widget */}
                {!collapsed && (
                    <div className="sidebar-savings" style={{ marginTop: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <DollarSign size={13} color="var(--success)" style={{ flexShrink: 0 }} />
                            <div>
                                <div className="sidebar-savings-amount">{liveSavings ?? '—'}</div>
                                <div className="sidebar-savings-label">vs AWS on-demand · live</div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Grouped Navigation */}
                <nav style={{ flex: 1, padding: '4px 8px', overflowY: 'auto', overflowX: 'hidden' }}>
                    {NAV_GROUPS.map((group) => (
                        <div key={group.label}>
                            {!collapsed && (
                                <div className="nav-section-label">{group.label}</div>
                            )}
                            {group.items.map(({ to, icon: Icon, label, exact, badge, dot }) => (
                                <NavLink
                                    key={to} to={to} end={exact}
                                    onClick={onMobileClose}
                                    className={({ isActive }) => `nav-link orq-nav-link${isActive ? ' active' : ''}`}
                                    title={collapsed ? label : undefined}
                                    style={{ gap: 9, padding: '8px 10px', borderRadius: 8, marginBottom: 1 }}
                                >
                                    <Icon size={16} style={{ minWidth: 16, flexShrink: 0 }} />
                                    {!collapsed && (
                                        <>
                                            <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
                                            {dot && <span className="live-dot" />}
                                            {badge && <span className={`nav-badge ${badge.cls}`}>{badge.text}</span>}
                                        </>
                                    )}
                                </NavLink>
                            ))}
                        </div>
                    ))}
                </nav>

                {/* User footer */}
                <div style={{ padding: '10px 10px 14px', borderTop: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, overflow: 'hidden' }}>
                        <div className="user-avatar" style={{ flexShrink: 0, width: 30, height: 30, fontSize: 11 }}>
                            {user?.email?.[0]?.toUpperCase() || 'A'}
                        </div>
                        {!collapsed && (
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {user?.email?.split('@')[0] || 'Admin'}
                                </div>
                                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{user?.role === 'admin' ? '⚡ Admin · Active' : 'Member · Active'}</div>
                            </div>
                        )}
                        <button onClick={logout} title="Logout" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', flexShrink: 0, padding: 4, borderRadius: 6, transition: 'color 0.2s' }}
                            onMouseEnter={e => e.currentTarget.style.color = '#f87171'}
                            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
                        >
                            <LogOut size={13} />
                        </button>
                    </div>
                </div>
            </aside>
        </>
    )
}


/* ── Protected App Layout ── */
function AppLayout() {
    const [collapsed, setCollapsed] = useState(false)
    const [mobileOpen, setMobileOpen] = useState(false)
    const [isMobile, setIsMobile] = useState(
        () => typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches
    )
    const navigate = useNavigate()
    const { paletteOpen, setPaletteOpen, shortcutsOpen, setShortcutsOpen } = useCommandPalette(navigate)

    // matchMedia keeps sidebar correct across zoom levels — window.innerWidth is zoom-sensitive
    useEffect(() => {
        const mq = window.matchMedia('(max-width: 767px)')
        const handler = (e) => setIsMobile(e.matches)
        mq.addEventListener('change', handler)
        return () => mq.removeEventListener('change', handler)
    }, [])

    const ml = isMobile ? 0 : (collapsed ? 72 : 228)

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <Sidebar
                collapsed={collapsed}
                onToggle={() => setCollapsed(c => !c)}
                mobileOpen={mobileOpen}
                onMobileClose={() => setMobileOpen(false)}
            />

            {isMobile && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, height: 56,
                    background: 'var(--surface-800)',
                    borderBottom: '1px solid var(--border)',
                    display: 'flex', alignItems: 'center',
                    padding: '0 16px', gap: 12, zIndex: 48,
                }}>
                    <button onClick={() => setMobileOpen(true)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex' }}>
                        <Menu size={20} />
                    </button>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 26, height: 26, background: 'linear-gradient(135deg,#3a52eb,#7a9bfa)', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Cpu size={13} color="#fff" />
                        </div>
                        <span style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)' }}>OrQuanta</span>
                    </div>
                </div>
            )}

            <main style={{
                flex: 1,
                marginLeft: ml,
                padding: isMobile ? '76px 16px 24px' : 28,
                minHeight: '100vh',
                transition: 'margin-left 0.25s ease',
            }}>
                {/* Per-route error boundary — crash in one page doesn't kill the shell */}
                <ErrorBoundary>
                    <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/goals" element={<GoalSubmit />} />
                        <Route path="/agents" element={<AgentMonitor />} />
                        <Route path="/jobs" element={<JobManager />} />
                        <Route path="/schedules" element={<SchedulesPage />} />
                        <Route path="/costs" element={<CostAnalytics />} />
                        <Route path="/audit" element={<AuditLog />} />
                        <Route path="/carbon" element={<CarbonTrackerPage />} />
                        <Route path="/billing" element={<BillingPage />} />
                        <Route path="/free" element={<FreeTier />} />
                        <Route path="/pricing" element={<LivePricing />} />
                        <Route path="/settings" element={<ProfilePage />} />
                        <Route path="/vero" element={<VeroControl />} />
                        <Route path="/nemoclaw" element={<NemoClawPage />} />
                        <Route path="/uix" element={<UIXAgentPage />} />
                        <Route path="/help" element={<HelpPage />} />
                        <Route path="*" element={<Navigate to="/" />} />
                    </Routes>
                </ErrorBoundary>
            </main>

            <OrQuantaAssistant />
            {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} onNavigate={navigate} />}
            {shortcutsOpen && <ShortcutsModal onClose={() => setShortcutsOpen(false)} />}
        </div>
    )
}

/* ── Root App ── */
export default function App() {
    return (
        <ErrorBoundary>
            <AuthProvider>
                <BrowserRouter basename="/app">
                    <AppRouter />
                </BrowserRouter>
            </AuthProvider>
        </ErrorBoundary>
    )
}

function AppRouter() {
    const { isAuth } = useAuth()
    return isAuth ? <AppLayout /> : <LoginPage />
}
