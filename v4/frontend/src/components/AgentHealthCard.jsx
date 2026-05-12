/**
 * AgentHealthCard — Live Safety Governor stats widget
 *
 * Polls /admin/safety/status every 10s and displays:
 * - Daily spend vs cap
 * - Emergency stop state
 * - Actions logged total
 * - PolicyRails config summary
 *
 * Shown at the top of AgentMonitor page.
 */
import { useState, useEffect, useContext } from 'react'
import { AlertTriangle, ShieldCheck, DollarSign, Activity } from 'lucide-react'
import { AuthContext } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

export default function AgentHealthCard() {
    const { token } = useContext(AuthContext)
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const fetch_data = async () => {
            try {
                const r = await fetch(`${API}/admin/safety/status`, {
                    headers: { Authorization: `Bearer ${token}` }
                })
                if (r.ok) {
                    setData(await r.json())
                }
            } catch {
                // Non-fatal — endpoint requires admin role
            } finally {
                setLoading(false)
            }
        }
        fetch_data()
        const t = setInterval(fetch_data, 10000)
        return () => clearInterval(t)
    }, [token])

    // Hidden for non-admin users (endpoint returns 403)
    if (loading || !data) return null

    const gov = data.governor || {}
    const policy = data.policy || {}
    const isEmergencyStop = gov.emergency_stop_active === true

    const spendPct = policy.budget_rails?.daily_spend_cap_usd
        ? (gov.daily_spend_usd / policy.budget_rails.daily_spend_cap_usd) * 100
        : 0

    return (
        <div
            className="glass-card p-4 mb-4"
            style={{
                border: isEmergencyStop
                    ? '1px solid rgba(239,68,68,0.6)'
                    : '1px solid rgba(0,255,136,0.15)',
                background: isEmergencyStop
                    ? 'rgba(239,68,68,0.06)'
                    : 'rgba(0,255,136,0.03)',
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {isEmergencyStop
                        ? <AlertTriangle size={16} color="#ef4444" />
                        : <ShieldCheck size={16} color="#10B981" />
                    }
                    <span style={{ fontWeight: 700, fontSize: 13, color: isEmergencyStop ? '#ef4444' : '#10B981' }}>
                        {isEmergencyStop ? '🛑 Emergency Stop Active' : '✅ NeMo Guardrails Active'}
                    </span>
                </div>
                <span style={{
                    fontSize: 11, color: '#64748b', background: 'rgba(0,0,0,0.03)',
                    padding: '2px 10px', borderRadius: 999, border: '1px solid rgba(0,0,0,0.08)'
                }}>
                    PolicyRails v{policy.version || '1.0'}
                </span>
            </div>

            {isEmergencyStop && gov.stop_reason && (
                <div style={{
                    background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
                    borderRadius: 8, padding: '8px 12px', marginBottom: 12, fontSize: 12, color: '#fca5a5'
                }}>
                    <strong>Reason:</strong> {gov.stop_reason}
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
                {/* Daily Spend */}
                <div style={{ background: 'rgba(0,0,0,0.02)', borderRadius: 10, padding: '10px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                        <DollarSign size={12} color="#F59E0B" />
                        <span style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1 }}>Daily Spend</span>
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#F59E0B' }}>
                        ${(gov.daily_spend_usd || 0).toFixed(2)}
                    </div>
                    <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
                        of ${(policy.budget_rails?.daily_spend_cap_usd || 5000).toLocaleString()} cap
                    </div>
                    <div style={{ marginTop: 6, height: 4, borderRadius: 999, background: 'rgba(0,0,0,0.06)' }}>
                        <div style={{
                            height: '100%', borderRadius: 999,
                            width: `${Math.min(spendPct, 100)}%`,
                            background: spendPct > 80 ? '#ef4444' : spendPct > 50 ? '#F59E0B' : '#10B981',
                            transition: 'width 0.5s ease'
                        }} />
                    </div>
                </div>

                {/* Actions Logged */}
                <div style={{ background: 'rgba(0,0,0,0.02)', borderRadius: 10, padding: '10px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                        <Activity size={12} color="#0091FF" />
                        <span style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1 }}>Actions Logged</span>
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#0091FF' }}>
                        {gov.total_actions_logged || 0}
                    </div>
                    <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
                        {gov.successful_actions || 0} success · {gov.failed_actions || 0} failed
                    </div>
                </div>

                {/* Auto-approve threshold */}
                <div style={{ background: 'rgba(0,0,0,0.02)', borderRadius: 10, padding: '10px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                        <ShieldCheck size={12} color="#7B2FFF" />
                        <span style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1 }}>Auto-Approve</span>
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#7B2FFF' }}>
                        &lt;${(policy.budget_rails?.auto_approve_threshold_usd || 100).toLocaleString()}
                    </div>
                    <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>per action</div>
                </div>

                {/* Blocked Actions */}
                <div style={{ background: 'rgba(0,0,0,0.02)', borderRadius: 10, padding: '10px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                        <AlertTriangle size={12} color="#F472B6" />
                        <span style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1 }}>Blocked Actions</span>
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#F472B6' }}>
                        {(policy.blocked_actions || []).length}
                    </div>
                    <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>permanently blocked</div>
                </div>
            </div>
        </div>
    )
}
