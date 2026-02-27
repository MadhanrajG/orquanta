import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate } from 'react-router-dom'
import { useState, useEffect, createContext, useContext } from 'react'
import {
    LayoutDashboard, Target, Activity, Server, DollarSign,
    ScrollText, Cpu, Zap, LogOut, Menu, X, AlertTriangle, Leaf
} from 'lucide-react'
import Dashboard from './pages/Dashboard.jsx'
import GoalSubmit from './pages/GoalSubmit.jsx'
import AgentMonitor from './pages/AgentMonitor.jsx'
import JobManager from './pages/JobManager.jsx'
import CostAnalytics from './pages/CostAnalytics.jsx'
import AuditLog from './pages/AuditLog.jsx'
import OrQuantaAssistant from './components/OrQuantaAssistant.jsx'
import { CommandPalette, ShortcutsModal, useCommandPalette } from './components/CommandPalette.jsx'

/* ─── Auth Context ─────────────────────────────────────────────────────── */
export const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

function AuthProvider({ children }) {
    const [token, setToken] = useState(() => localStorage.getItem('orquanta_token'))
    const [user, setUser] = useState(() => {
        try { return JSON.parse(localStorage.getItem('orquanta_user')) } catch { return null }
    })

    const login = async (email, password) => {
        const res = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        })
        if (!res.ok) {
            const err = await res.json().catch(() => ({}))
            throw new Error(err.error || 'Invalid credentials')
        }
        const data = await res.json()
        setToken(data.access_token)
        const u = { email }
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

/* ─── Login Page ───────────────────────────────────────────────────────── */
function LoginPage() {
    const { login } = useAuth()
    const [email, setEmail] = useState('admin@orquanta.ai')
    const [password, setPassword] = useState('orquanta-admin-2024')
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    const handleSubmit = async (e) => {
        e.preventDefault(); setError(''); setLoading(true)
        try { await login(email, password) }
        catch (err) { setError(err.message || 'Login failed. Ensure the API is running on :8000') }
        finally { setLoading(false) }
    }

    return (
        <div className="auth-page">
            {/* Ambient glow orbs */}
            <div style={{ position: 'absolute', top: '25%', left: '25%', width: '400px', height: '400px', background: 'rgba(82,113,245,0.08)', borderRadius: '50%', filter: 'blur(80px)', pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', bottom: '25%', right: '25%', width: '300px', height: '300px', background: 'rgba(139,92,246,0.06)', borderRadius: '50%', filter: 'blur(80px)', pointerEvents: 'none' }} />

            <div style={{ width: '100%', maxWidth: '420px', padding: '0 16px', position: 'relative', zIndex: 1 }}>
                <div className="auth-card fade-in">
                    {/* Logo */}
                    <div className="auth-logo">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', justifyContent: 'center', marginBottom: '6px' }}>
                            <div style={{ width: 44, height: 44, background: 'linear-gradient(135deg,#3a52eb,#7a9bfa)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <Cpu size={22} color="#fff" />
                            </div>
                            <div style={{ textAlign: 'left' }}>
                                <div className="logo-text">OrQuanta</div>
                                <div className="logo-sub">Agentic GPU Cloud v1.0</div>
                            </div>
                        </div>
                    </div>

                    <h2 className="auth-title">Welcome back</h2>
                    <p className="auth-sub">Sign in to manage your GPU infrastructure</p>

                    {error && (
                        <div className="alert alert-error" style={{ marginBottom: 16 }}>
                            <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
                            <span>{error}</span>
                        </div>
                    )}

                    <form onSubmit={handleSubmit}>
                        <div className="input-group" style={{ marginBottom: 14 }}>
                            <label className="input-label">Email address</label>
                            <input id="login-email" type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="admin@orquanta.ai" />
                        </div>
                        <div className="input-group" style={{ marginBottom: 20 }}>
                            <label className="input-label">Password</label>
                            <input id="login-password" type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••••••" />
                        </div>
                        <button id="login-submit" type="submit" className="btn btn-primary w-full btn-lg" disabled={loading} style={{ width: '100%' }}>
                            {loading
                                ? <><span className="spinner" style={{ width: 16, height: 16 }} /> Authenticating…</>
                                : 'Sign In →'
                            }
                        </button>
                    </form>

                    <p style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', marginTop: 20 }}>
                        Default: admin@orquanta.ai / orquanta-admin-2024
                    </p>
                </div>
            </div>
        </div>
    )
}

/* ─── Navigation Sidebar ────────────────────────────────────────────────── */
const navItems = [
    { to: '/', icon: LayoutDashboard, label: 'Dashboard', exact: true },
    { to: '/goals', icon: Target, label: 'Submit Goal' },
    { to: '/agents', icon: Zap, label: 'Agent Monitor' },
    { to: '/jobs', icon: Server, label: 'Job Manager' },
    { to: '/costs', icon: DollarSign, label: 'Cost Analytics' },
    { to: '/audit', icon: ScrollText, label: 'Audit Log' },
    { to: '/carbon', icon: Leaf, label: 'Carbon Tracker' },
]

function Sidebar({ collapsed, onToggle }) {
    const { logout, user } = useAuth()
    const w = collapsed ? 64 : 220

    return (
        <aside style={{ width: w, minHeight: '100vh', background: 'var(--surface-800)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', position: 'fixed', top: 0, left: 0, zIndex: 50, transition: 'width 0.25s ease', overflow: 'hidden' }}>
            {/* Logo strip */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '18px 14px 14px', borderBottom: '1px solid var(--border)', minHeight: 64 }}>
                <div style={{ width: 32, height: 32, minWidth: 32, background: 'linear-gradient(135deg,#3a52eb,#7a9bfa)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <Cpu size={16} color="#fff" />
                </div>
                {!collapsed && <span style={{ fontWeight: 800, fontSize: 14, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>OrQuanta v1.0</span>}
                <button onClick={onToggle} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', flexShrink: 0 }}>
                    {collapsed ? <Menu size={16} /> : <X size={16} />}
                </button>
            </div>

            {/* Nav items */}
            <nav style={{ flex: 1, padding: '10px 8px' }}>
                {!collapsed && <div className="nav-label">Platform</div>}
                {navItems.map(({ to, icon: Icon, label, exact }) => (
                    <NavLink
                        key={to} to={to} end={exact}
                        className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                        title={collapsed ? label : undefined}
                    >
                        <Icon size={17} style={{ minWidth: 17 }} />
                        {!collapsed && <span>{label}</span>}
                    </NavLink>
                ))}
            </nav>

            {/* User footer */}
            <div style={{ padding: '12px 10px', borderTop: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, overflow: 'hidden' }}>
                    <div className="user-avatar" style={{ flexShrink: 0 }}>
                        {user?.email?.[0]?.toUpperCase() || 'A'}
                    </div>
                    {!collapsed && (
                        <span style={{ fontSize: 12, color: 'var(--text-muted)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {user?.email || 'Admin'}
                        </span>
                    )}
                    <button onClick={logout} title="Logout" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', flexShrink: 0 }}>
                        <LogOut size={14} />
                    </button>
                </div>
            </div>
        </aside>
    )
}

/* ─── Protected Layout ──────────────────────────────────────────────────── */
function AppLayout() {
    const [collapsed, setCollapsed] = useState(false)
    const navigate = useNavigate()
    const { paletteOpen, setPaletteOpen, shortcutsOpen, setShortcutsOpen } = useCommandPalette(navigate)
    const ml = collapsed ? 72 : 228

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
            <main style={{ flex: 1, marginLeft: ml, padding: 28, minHeight: '100vh', transition: 'margin-left 0.25s ease' }}>
                <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/goals" element={<GoalSubmit />} />
                    <Route path="/agents" element={<AgentMonitor />} />
                    <Route path="/jobs" element={<JobManager />} />
                    <Route path="/costs" element={<CostAnalytics />} />
                    <Route path="/audit" element={<AuditLog />} />
                    <Route path="/carbon" element={<CostAnalytics />} />
                    <Route path="*" element={<Navigate to="/" />} />
                </Routes>
            </main>

            <OrQuantaAssistant />
            {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} onNavigate={navigate} />}
            {shortcutsOpen && <ShortcutsModal onClose={() => setShortcutsOpen(false)} />}
        </div>
    )
}

/* ─── Root App ──────────────────────────────────────────────────────────── */
export default function App() {
    return (
        <AuthProvider>
            <BrowserRouter>
                <AppRouter />
            </BrowserRouter>
        </AuthProvider>
    )
}

function AppRouter() {
    const { isAuth } = useAuth()
    return isAuth ? <AppLayout /> : <LoginPage />
}
