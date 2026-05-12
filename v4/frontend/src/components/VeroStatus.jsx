/**
 * VeroStatus — compact Vero widget for Dashboard
 * Shows live safety status: Vero health badge, agents monitored, active users, trend alerts.
 * Polls /api/v1/vero/status every 15s.
 */
import { useState, useEffect, useContext } from 'react'
import { AuthContext } from '../App.jsx'
import { Crown, Users, TrendingUp, AlertTriangle, CheckCircle, Wifi } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || ''

export default function VeroStatus() {
    const { token } = useContext(AuthContext)
    const [data, setData] = useState(null)
    const [blip, setBlip] = useState(false)

    useEffect(() => {
        const load = async () => {
            try {
                const r = await fetch(`${API}/api/v1/vero/status`, {
                    headers: { Authorization: `Bearer ${token}` }
                })
                if (r.ok) { setData(await r.json()); setBlip(b => !b) }
            } catch {}
        }
        load()
        const t = setInterval(load, 15000)
        return () => clearInterval(t)
    }, [token])

    const statusColor = data?.vero_status === 'nominal' ? '#10B981'
        : data?.vero_status === 'alert' ? '#F59E0B'
        : data?.vero_status === 'critical' ? '#ef4444'
        : '#64748b'

    return (
        <div style={{
            background: 'linear-gradient(135deg, rgba(123,47,255,0.12), rgba(0,145,255,0.08))',
            border: `1px solid ${statusColor}30`,
            borderRadius: 16, padding: '16px 20px',
            display: 'flex', alignItems: 'center', gap: 16,
            position: 'relative', overflow: 'hidden',
        }}>
            {/* Glow bg */}
            <div style={{
                position: 'absolute', top: -30, left: -30, width: 100, height: 100,
                background: `radial-gradient(circle, ${statusColor}15, transparent 70%)`,
                pointerEvents: 'none',
            }} />

            {/* Crown icon */}
            <div style={{
                width: 44, height: 44, borderRadius: 12, flexShrink: 0,
                background: `linear-gradient(135deg, #7B2FFF25, #0091FF15)`,
                border: `1px solid ${statusColor}40`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: `0 0 16px ${statusColor}25`,
            }}>
                <Crown size={20} color={statusColor} />
            </div>

            {/* Vero label */}
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                    <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)', letterSpacing: 1 }}>
                        VERO
                    </span>
                    <span style={{
                        fontSize: 10, color: statusColor,
                        background: `${statusColor}15`, padding: '1px 8px',
                        borderRadius: 999, border: `1px solid ${statusColor}30`,
                        textTransform: 'uppercase', letterSpacing: 1,
                    }}>
                        {data?.vero_status || 'initializing'}
                    </span>
                    {/* Pulse dot */}
                    <span style={{
                        width: 6, height: 6, borderRadius: '50%',
                        background: statusColor,
                        boxShadow: `0 0 6px ${statusColor}`,
                        animation: 'pulse 1.5s infinite',
                        marginLeft: 'auto',
                    }} />
                </div>
                <div style={{ fontSize: 11, color: '#64748b' }}>
                    Superior Intelligence Meta-Agent
                </div>
            </div>

            {/* KPI chips */}
            <div style={{ display: 'flex', gap: 12, flexShrink: 0 }}>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#10B981' }}>
                        {data ? `${data.agent_summary?.healthy ?? '—'}/5` : '—'}
                    </div>
                    <div style={{ fontSize: 10, color: '#64748b', marginTop: 1 }}>Agents</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#0091FF' }}>
                        {data?.user_intelligence?.active_sessions ?? '—'}
                    </div>
                    <div style={{ fontSize: 10, color: '#64748b', marginTop: 1 }}>Online</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#F472B6' }}>
                        {data?.market_intelligence?.ui_recommendations_count ?? '—'}
                    </div>
                    <div style={{ fontSize: 10, color: '#64748b', marginTop: 1 }}>Trends</div>
                </div>
            </div>
        </div>
    )
}
