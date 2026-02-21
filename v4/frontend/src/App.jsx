import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate } from 'react-router-dom'
import { useState, useEffect, createContext, useContext } from 'react'
import {
    LayoutDashboard, Target, Activity, Server, DollarSign,
    ScrollText, Cpu, Zap, LogOut, Menu, X, AlertTriangle, Leaf, Smartphone
} from 'lucide-react'
import Dashboard from './pages/Dashboard.jsx'
import GoalSubmit from './pages/GoalSubmit.jsx'
import AgentMonitor from './pages/AgentMonitor.jsx'
import JobManager from './pages/JobManager.jsx'
import CostAnalytics from './pages/CostAnalytics.jsx'
import AuditLog from './pages/AuditLog.jsx'
import OrQuantaAssistant from './components/OrQuantaAssistant.jsx'
import { CommandPalette, ShortcutsModal, useCommandPalette } from './components/CommandPalette.jsx'

/* ─── Auth Context ─────────────────────────────────────────────────── */
export const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

const API = import.meta.env.VITE_API_URL || ''

function AuthProvider({ children }) {
    const [token, setToken] = useState(() => localStorage.getItem('orquanta_token'))
    const [user, setUser] = useState(null)

    const login = async (email, password) => {
        const res = await fetch(`${API}/auth/login`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        })
        if (!res.ok) throw new Error('Invalid credentials')
        const data = await res.json()
        setToken(data.access_token)
        localStorage.setItem('orquanta_token', data.access_token)
        setUser({ email })
    }

    const logout = () => {
        setToken(null); setUser(null)
        localStorage.removeItem('orquanta_token')
    }

    return (
        <AuthContext.Provider value={{ token, user, login, logout, isAuth: !!token }}>
            {children}
        </AuthContext.Provider>
    )
}

/* ─── Login Page ───────────────────────────────────────────────────── */
function LoginPage() {
    const { login } = useAuth()
    const [email, setEmail] = useState('admin@orquanta.ai')
    const [password, setPassword] = useState('orquanta-admin-2026')
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    const handleSubmit = async (e) => {
        e.preventDefault(); setError(''); setLoading(true)
        try { await login(email, password) }
        catch { setError('Invalid credentials. Check API is running.') }
        finally { setLoading(false) }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-surface-900 bg-grid-pattern bg-grid-pattern">
            {/* Glow orbs */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-600/20 rounded-full blur-3xl" />
                <div className="absolute bottom-1/4 right-1/4 w-72 h-72 bg-purple-600/15 rounded-full blur-3xl" />
            </div>
            <div className="relative z-10 w-full max-w-md px-4">
                <div className="glass-card p-8 animate-fade-in">
                    <div className="flex items-center gap-3 mb-8">
                        <div className="w-10 h-10 bg-gradient-to-br from-brand-500 to-purple-500 rounded-xl flex items-center justify-center">
                            <Cpu size={20} className="text-white" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold text-white">OrQuanta Agentic</h1>
                            <p className="text-xs text-brand-400 font-medium">v1.0 — Agentic GPU Cloud Platform</p>
                        </div>
                    </div>
                    <h2 className="text-2xl font-bold text-white mb-1">Welcome back</h2>
                    <p className="text-slate-400 text-sm mb-6">Sign in to manage your GPU infrastructure</p>
                    {error && (
                        <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/20 rounded-xl p-3 mb-4 text-red-400 text-sm">
                            <AlertTriangle size={14} />{error}
                        </div>
                    )}
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-300 mb-1.5">Email</label>
                            <input id="email" type="email" className="input-field" value={email} onChange={e => setEmail(e.target.value)} required />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-300 mb-1.5">Password</label>
                            <input id="password" type="password" className="input-field" value={password} onChange={e => setPassword(e.target.value)} required />
                        </div>
                        <button id="login-btn" type="submit" className="btn-primary w-full mt-2" disabled={loading}>
                            {loading ? 'Authenticating…' : 'Sign In'}
                        </button>
                    </form>
                    <p className="text-xs text-slate-600 text-center mt-6">Default: admin@orquanta.ai / orquanta-admin-2026</p>
                </div>
            </div>
        </div>
    )
}

/* ─── Navigation Sidebar ───────────────────────────────────────────── */
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
    return (
        <aside className={`fixed left-0 top-0 h-full z-30 flex flex-col transition-all duration-300 ${collapsed ? 'w-16' : 'w-56'}`}>
            <div className="glass-card h-full m-2 flex flex-col rounded-2xl overflow-hidden">
                {/* Logo */}
                <div className="flex items-center gap-3 px-4 py-4 border-b border-white/[0.06]">
                    <div className="w-8 h-8 min-w-[2rem] bg-gradient-to-br from-brand-500 to-purple-500 rounded-lg flex items-center justify-center">
                        <Cpu size={16} className="text-white" />
                    </div>
                    {!collapsed && <span className="font-bold text-white text-sm">OrQuanta v1.0</span>}
                    <button onClick={onToggle} className="ml-auto text-slate-500 hover:text-white transition-colors">
                        {collapsed ? <Menu size={16} /> : <X size={16} />}
                    </button>
                </div>
                {/* Nav */}
                <nav className="flex-1 p-2 space-y-0.5">
                    {navItems.map(({ to, icon: Icon, label, exact }) => (
                        <NavLink key={to} to={to} end={exact} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                            <Icon size={18} className="min-w-[1.125rem]" />
                            {!collapsed && <span>{label}</span>}
                        </NavLink>
                    ))}
                </nav>
                {/* User */}
                <div className="p-3 border-t border-white/[0.06]">
                    <div className="flex items-center gap-2 px-2">
                        <div className="w-7 h-7 bg-brand-600/30 rounded-full flex items-center justify-center text-brand-400 text-xs font-bold min-w-[1.75rem]">
                            {user?.email?.[0]?.toUpperCase() || 'A'}
                        </div>
                        {!collapsed && <span className="text-xs text-slate-400 truncate">{user?.email || 'Admin'}</span>}
                        <button onClick={logout} className="ml-auto text-slate-600 hover:text-red-400 transition-colors" title="Logout">
                            <LogOut size={14} />
                        </button>
                    </div>
                </div>
            </div>
        </aside>
    )
}

/* ─── Protected Layout ─────────────────────────────────────────────── */
function AppLayout() {
    const [collapsed, setCollapsed] = useState(false)
    const navigate = useNavigate()
    const { paletteOpen, setPaletteOpen, shortcutsOpen, setShortcutsOpen } = useCommandPalette(navigate)
    return (
        <div className="flex min-h-screen">
            <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
            <main className={`flex-1 transition-all duration-300 ${collapsed ? 'ml-[4.5rem]' : 'ml-[15rem]'} p-6 min-h-screen`}>
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
            {/* Global overlays */}
            <OrQuantaAssistant />
            {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} onNavigate={navigate} />}
            {shortcutsOpen && <ShortcutsModal onClose={() => setShortcutsOpen(false)} />}
        </div>
    )
}

/* ─── Root App ─────────────────────────────────────────────────────── */
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
