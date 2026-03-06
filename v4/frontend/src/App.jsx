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
import FreeTier from './pages/FreeTier.jsx'
import OrQuantaAssistant from './components/OrQuantaAssistant.jsx'
import { CommandPalette, ShortcutsModal, useCommandPalette } from './components/CommandPalette.jsx'

/* â”€â”€â”€ Auth Context â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
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

/* â”€â”€â”€ Login Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
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
            <div style={{ position:'absolute',top:'20%',left:'20%',width:'500px',height:'500px',background:'rgba(82,113,245,0.07)',borderRadius:'50%',filter:'blur(100px)',pointerEvents:'none' }} />
            <div style={{ position:'absolute',bottom:'20%',right:'20%',width:'350px',height:'350px',background:'rgba(139,92,246,0.06)',borderRadius:'50%',filter:'blur(80px)',pointerEvents:'none' }} />
            <div style={{ width:'100%',maxWidth:'440px',padding:'0 16px',position:'relative',zIndex:1 }}>
                <div className="auth-card fade-in">
                    <div className="auth-logo">
                        <div style={{ display:'flex',alignItems:'center',gap:'12px',justifyContent:'center',marginBottom:'6px' }}>
                            <div style={{ width:44,height:44,background:'linear-gradient(135deg,#3a52eb,#7a9bfa)',borderRadius:12,display:'flex',alignItems:'center',justifyContent:'center' }}>
                                <Cpu size={22} color="#fff" />
                            </div>
                            <div style={{ textAlign:'left' }}>
                                <div className="logo-text">OrQuanta</div>
                                <div className="logo-sub">Agentic GPU Cloud v1.0</div>
                            </div>
                        </div>
                    </div>
                    <div style={{ display:'flex',background:'rgba(255,255,255,0.04)',borderRadius:10,padding:4,marginBottom:24,border:'1px solid rgba(255,255,255,0.08)' }}>
                        {[['login','Sign In'],['register','Create Account']].map(([m,label]) => (
                            <button key={m} onClick={() => switchMode(m)} style={{
                                flex:1,padding:'8px 0',borderRadius:7,border:'none',cursor:'pointer',
                                fontSize:14,fontWeight:600,transition:'all 0.2s',
                                background:mode===m?'linear-gradient(135deg,#3a52eb,#5a72fb)':'transparent',
                                color:mode===m?'#fff':'var(--text-muted)',
                                boxShadow:mode===m?'0 2px 12px rgba(58,82,235,0.4)':'none',
                            }}>{label}</button>
                        ))}
                    </div>
                    <h2 className="auth-title" style={{ marginBottom:4 }}>
                        {mode==='login' ? 'Welcome back' : 'Start for free'}
                    </h2>
                    <p className="auth-sub" style={{ marginBottom:20 }}>
                        {mode==='login' ? 'Sign in to manage your GPU infrastructure' : '14-day free trial · No credit card required'}
                    </p>
                    {error && (
                        <div className="alert alert-error" style={{ marginBottom:16 }}>
                            <AlertTriangle size={15} style={{ flexShrink:0,marginTop:1 }} />
                            <span>{error}</span>
                        </div>
                    )}
                    <form onSubmit={mode==='login' ? handleLogin : handleRegister}>
                        {mode==='register' && (
                            <div className="input-group" style={{ marginBottom:14 }}>
                                <label className="input-label">Full Name</label>
                                <input id="reg-name" type="text" value={name} onChange={e => setName(e.target.value)} required minLength={2} placeholder="Ada Lovelace" />
                            </div>
                        )}
                        <div className="input-group" style={{ marginBottom:14 }}>
                            <label className="input-label">Email address</label>
                            <input id="auth-email" type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@company.ai" />
                        </div>
                        <div className="input-group" style={{ marginBottom:mode==='register'?8:20 }}>
                            <label className="input-label">Password</label>
                            <input id="auth-password" type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} placeholder="Min. 8 characters" />
                        </div>
                        {mode==='register' && (
                            <p style={{ fontSize:12,color:'var(--text-muted)',marginBottom:18,lineHeight:1.5 }}>By signing up you agree to our Terms of Service.</p>
                        )}
                        <button id="auth-submit" type="submit" className="btn btn-primary w-full btn-lg" disabled={loading} style={{ width:'100%' }}>
                            {loading ? <><span className="spinner" style={{ width:16,height:16 }} />{' '}{mode==='login'?'Signing in...':'Creating account...'}</> : mode==='login' ? 'Sign In →' : 'Create Free Account →'}
                        </button>
                    </form>
                    <div style={{ marginTop:20,paddingTop:20,borderTop:'1px solid rgba(255,255,255,0.06)',textAlign:'center' }}>
                        <p style={{ fontSize:13,color:'var(--text-muted)' }}>
                            Want to explore first?{' '}<a href="/demo" style={{ color:'#7a9bfa',textDecoration:'none',fontWeight:600 }}>View live demo →</a>
                        </p>
                    </div>
                </div>
                <div style={{ display:'flex',justifyContent:'center',gap:20,marginTop:18,flexWrap:'wrap' }}>
                    {['🔒 Secure JWT auth','⚡ Live in seconds','🌍 Free 14-day trial'].map(b => (
                        <span key={b} style={{ fontSize:12,color:'var(--text-muted)' }}>{b}</span>
                    ))}
                </div>
            </div>
        </div>
    )
}

/* â”€â”€â”€ Carbon Tracker (Coming Soon) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function CarbonTrackerPage() {
    return (
        <div className="space-y-6 animate-fade-in">
            <div>
                <h1 className="text-2xl font-bold text-white">Carbon Tracker</h1>
                <p className="text-slate-400 text-sm mt-0.5">Route workloads to the greenest regions automatically</p>
            </div>
            {/* Coming soon banner */}
            <div className="glass-card p-8 text-center relative overflow-hidden">
                <div className="absolute inset-0 opacity-5" style={{ background: 'radial-gradient(ellipse at 50% 0%, #00FF88, transparent 70%)' }} />
                <div style={{ fontSize: 56, marginBottom: 16 }}>ðŸŒ¿</div>
                <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', marginBottom: 12, color: 'white' }}>Carbon-Aware Scheduling</h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', lineHeight: 1.7, marginBottom: 28, maxWidth: 480, margin: '0 auto 28px' }}>
                    OrQuanta will automatically detect real-time carbon intensity per region
                    and shift your GPU jobs to the lowest-carbon available locations.
                </p>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '7px 20px', border: '1px solid rgba(0,255,136,0.3)', borderRadius: 999, background: 'rgba(0,255,136,0.06)', color: '#00FF88', fontSize: 13 }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#00FF88', display: 'inline-block', animation: 'pulse 2s infinite' }} />
                    In Development â€” Available in v1.1
                </div>
            </div>
            {/* Preview cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                    { icon: 'âš¡', title: 'Real-Time Carbon Intensity', desc: 'gCOâ‚‚eq/kWh tracked per region via ElectricityMaps API', color: '#00FF88' },
                    { icon: 'ðŸ—ºï¸', title: 'Green Region Routing', desc: 'Automatic job migration to lowest-carbon providers', color: '#00D4FF' },
                    { icon: 'ðŸ“Š', title: 'Emissions Reporting', desc: 'Monthly carbon footprint reports & offset tracking', color: '#7B2FFF' },
                ].map(c => (
                    <div key={c.title} className="glass-card p-5" style={{ opacity: 0.75 }}>
                        <div className="text-3xl mb-3">{c.icon}</div>
                        <h3 className="font-semibold text-white text-sm mb-1.5">{c.title}</h3>
                        <p className="text-xs text-slate-500 leading-relaxed">{c.desc}</p>
                        <div className="mt-3 h-0.5 rounded-full" style={{ background: `${c.color}30` }} />
                    </div>
                ))}
            </div>
        </div>
    )
}

/* â”€â”€â”€ Navigation Sidebar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
const navItems = [
    { to: '/', icon: LayoutDashboard, label: 'Dashboard', exact: true },
    { to: '/goals', icon: Target, label: 'Submit Goal' },
    { to: '/agents', icon: Zap, label: 'Agent Monitor' },
    { to: '/jobs', icon: Server, label: 'Job Manager' },
    { to: '/costs', icon: DollarSign, label: 'Cost Analytics' },
    { to: '/audit', icon: ScrollText, label: 'Audit Log' },
    { to: '/carbon', icon: Leaf, label: 'Carbon Tracker' },
    { to: '/free', icon: Zap, label: 'Free GPU 🆓' },
]

function Sidebar({ collapsed, onToggle, mobileOpen, onMobileClose }) {
    const { logout, user } = useAuth()
    const w = collapsed ? 64 : 220

    return (
        <>
            {/* Mobile backdrop overlay */}
            {mobileOpen && (
                <div
                    onClick={onMobileClose}
                    style={{
                        position: 'fixed', inset: 0,
                        background: 'rgba(0,0,0,0.6)',
                        zIndex: 49, backdropFilter: 'blur(2px)',
                    }}
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
                            onClick={onMobileClose}
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
        </>
    )
}

/* â”€â”€â”€ Protected Layout â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function AppLayout() {
    const [collapsed, setCollapsed] = useState(false)
    const [mobileOpen, setMobileOpen] = useState(false)
    const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && window.innerWidth < 768)
    const navigate = useNavigate()
    const { paletteOpen, setPaletteOpen, shortcutsOpen, setShortcutsOpen } = useCommandPalette(navigate)

    useEffect(() => {
        const handler = () => setIsMobile(window.innerWidth < 768)
        window.addEventListener('resize', handler)
        return () => window.removeEventListener('resize', handler)
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

            {/* Mobile top bar */}
            {isMobile && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, height: 56,
                    background: 'var(--surface-800)',
                    borderBottom: '1px solid var(--border)',
                    display: 'flex', alignItems: 'center',
                    padding: '0 16px', gap: 12, zIndex: 48,
                }}>
                    <button
                        onClick={() => setMobileOpen(true)}
                        style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex' }}
                    >
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
                <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/goals" element={<GoalSubmit />} />
                    <Route path="/agents" element={<AgentMonitor />} />
                    <Route path="/jobs" element={<JobManager />} />
                    <Route path="/costs" element={<CostAnalytics />} />
                    <Route path="/audit" element={<AuditLog />} />
                    <Route path="/carbon" element={<CarbonTrackerPage />} />
                    <Route path="/free" element={<FreeTier />} />
                    <Route path="*" element={<Navigate to="/" />} />
                </Routes>
            </main>

            <OrQuantaAssistant />
            {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} onNavigate={navigate} />}
            {shortcutsOpen && <ShortcutsModal onClose={() => setShortcutsOpen(false)} />}
        </div>
    )
}

/* â”€â”€â”€ Root App â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
export default function App() {
    return (
        <AuthProvider>
            <BrowserRouter basename="/app">
                <AppRouter />
            </BrowserRouter>
        </AuthProvider>
    )
}

function AppRouter() {
    const { isAuth } = useAuth()
    return isAuth ? <AppLayout /> : <LoginPage />
}
