import { useState, useEffect } from 'react'
import { DollarSign, TrendingDown, Cloud, RefreshCw } from 'lucide-react'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, RadarChart, Radar, PolarGrid, PolarAngleAxis } from 'recharts'
import { useAuth } from '../App.jsx'

const API = import.meta.env.VITE_API_URL || ''

// Simulated cost time series (in production: fetched from API)
function genCostHistory(n = 30) {
    let v = 45; let cum = 0
    return Array.from({ length: n }, (_, i) => {
        v = Math.max(10, Math.min(200, v + (Math.random() - 0.45) * 25))
        cum += v
        return { day: `Day ${i + 1}`, daily: Math.round(v), cumulative: Math.round(cum) }
    })
}

const costHistory = genCostHistory()

const providerData = [
    { provider: 'CoreWeave', H100: 3.89, A100: 2.40, T4: 0.35 },
    { provider: 'GCP', H100: 4.90, A100: 2.95, T4: 0.38 },
    { provider: 'Azure', H100: 5.10, A100: 3.05, T4: 0.39 },
    { provider: 'AWS', H100: 5.20, A100: 3.10, T4: 0.40 },
]

const providerRadar = [
    { metric: 'Cost', CoreWeave: 95, AWS: 65, GCP: 72, Azure: 68 },
    { metric: 'Speed', CoreWeave: 80, AWS: 90, GCP: 88, Azure: 85 },
    { metric: 'Avail.', CoreWeave: 75, AWS: 95, GCP: 92, Azure: 90 },
    { metric: 'Support', CoreWeave: 72, AWS: 88, GCP: 85, Azure: 90 },
    { metric: 'Regions', CoreWeave: 60, AWS: 98, GCP: 90, Azure: 92 },
]

export default function CostAnalytics() {
    const { token } = useAuth()
    const [dashboard, setDashboard] = useState(null)
    const [prices, setPrices] = useState(null)
    const [forecast, setForecast] = useState(null)

    useEffect(() => {
        const headers = { Authorization: `Bearer ${token}` }
        const fetchAll = async () => {
            try {
                const [d, p, f] = await Promise.all([
                    fetch(`${API}/api/v1/metrics/cost/dashboard`, { headers }).then(r => r.ok ? r.json() : null),
                    fetch(`${API}/api/v1/metrics/spot-prices/H100`, { headers }).then(r => r.ok ? r.json() : null),
                    fetch(`${API}/api/v1/metrics/forecast`, { headers }).then(r => r.ok ? r.json() : null),
                ])
                if (d) setDashboard(d)
                if (p) setPrices(p)
                if (f) setForecast(f)
            } catch { }
        }
        fetchAll()
        const t = setInterval(fetchAll, 30000)
        return () => clearInterval(t)
    }, [])

    const cheapest = prices?.prices?.[0]
    const savings = cheapest ? `${(((5.20 - cheapest.current_price_usd_hr) / 5.20) * 100).toFixed(1)}%` : '—'

    return (
        <div className="space-y-6 animate-fade-in">
            <div>
                <h1 className="text-2xl font-bold text-white">Cost Analytics</h1>
                <p className="text-slate-400 text-sm mt-0.5">Real-time cost intelligence across all GPU providers</p>
            </div>

            {/* KPI Row */}
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                {[
                    { label: 'Today Spend', value: `$${(dashboard?.governor_spend?.daily_spend_usd ?? 0).toFixed(2)}`, icon: DollarSign, color: 'brand' },
                    { label: 'Daily Budget Left', value: `$${(dashboard?.governor_spend?.remaining_usd ?? 5000).toFixed(0)}`, icon: TrendingDown, color: 'green' },
                    { label: 'Cheapest H100/hr', value: cheapest ? `$${cheapest.current_price_usd_hr.toFixed(2)}` : '—', icon: Cloud, color: 'purple' },
                    { label: 'Savings vs On-Demand', value: savings, icon: DollarSign, color: 'amber' },
                ].map(({ label, value, icon: Icon, color }) => {
                    const clr = { brand: 'text-brand-400 bg-brand-500/10', green: 'text-emerald-400 bg-emerald-500/10', purple: 'text-purple-400 bg-purple-500/10', amber: 'text-amber-400 bg-amber-500/10' }[color]
                    return (
                        <div key={label} className="glass-card p-5">
                            <div className={`inline-flex p-2 rounded-lg ${clr} mb-3`}><Icon size={16} /></div>
                            <p className="text-2xl font-bold text-white">{value}</p>
                            <p className="text-xs text-slate-500 mt-0.5">{label}</p>
                        </div>
                    )
                })}
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {/* Daily Cost */}
                <div className="glass-card p-5">
                    <h3 className="font-semibold text-white mb-4">Daily Spend (30-day)</h3>
                    <ResponsiveContainer width="100%" height={200}>
                        <AreaChart data={costHistory}>
                            <defs>
                                <linearGradient id="cost" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <XAxis dataKey="day" hide />
                            <YAxis hide />
                            <Tooltip contentStyle={{ background: '#0f1120', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, fontSize: 12 }} formatter={v => [`$${v}`, 'Daily']} />
                            <Area type="monotone" dataKey="daily" stroke="#10b981" strokeWidth={2} fill="url(#cost)" />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>

                {/* Provider Comparison */}
                <div className="glass-card p-5">
                    <h3 className="font-semibold text-white mb-4">Spot Prices by Provider ($/hr)</h3>
                    <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={providerData}>
                            <XAxis dataKey="provider" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                            <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
                            <Tooltip contentStyle={{ background: '#0f1120', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, fontSize: 12 }} formatter={v => [`$${v}/hr`, '']} />
                            <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                            <Bar dataKey="H100" fill="#7c3aed" radius={[3, 3, 0, 0]} />
                            <Bar dataKey="A100" fill="#5271f5" radius={[3, 3, 0, 0]} />
                            <Bar dataKey="T4" fill="#10b981" radius={[3, 3, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Provider radar + spot price table */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <div className="glass-card p-5">
                    <h3 className="font-semibold text-white mb-4">Provider Capability Radar</h3>
                    <ResponsiveContainer width="100%" height={220}>
                        <RadarChart data={providerRadar}>
                            <PolarGrid stroke="rgba(255,255,255,0.06)" />
                            <PolarAngleAxis dataKey="metric" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                            <Radar name="CoreWeave" dataKey="CoreWeave" stroke="#10b981" fill="#10b981" fillOpacity={0.15} />
                            <Radar name="AWS" dataKey="AWS" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.1} />
                            <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                        </RadarChart>
                    </ResponsiveContainer>
                </div>

                {/* Live spot prices H100 */}
                <div className="glass-card p-5">
                    <h3 className="font-semibold text-white mb-4">H100 Live Spot Prices</h3>
                    <div className="space-y-2">
                        {(prices?.prices || [
                            { provider: 'coreweave', region: 'us-east1', current_price_usd_hr: 3.89, availability: 'high' },
                            { provider: 'gcp', region: 'us-central1', current_price_usd_hr: 4.90, availability: 'medium' },
                            { provider: 'azure', region: 'eastus', current_price_usd_hr: 5.10, availability: 'high' },
                            { provider: 'aws', region: 'us-east-1', current_price_usd_hr: 5.20, availability: 'low' },
                        ]).map((p, i) => (
                            <div key={i} className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.04]">
                                {i === 0 && <span className="badge badge-green text-xs">Best</span>}
                                {i > 0 && <span className="text-xs text-slate-600 w-8 text-center">#{i + 1}</span>}
                                <span className="text-sm text-slate-300 flex-1">{p.provider} — {p.region}</span>
                                <span className={`badge ${p.availability === 'high' ? 'badge-green' : p.availability === 'medium' ? 'badge-yellow' : 'badge-red'}`}>{p.availability}</span>
                                <span className="text-sm font-bold text-white">${(p.current_price_usd_hr ?? 0).toFixed(2)}<span className="text-xs text-slate-500">/hr</span></span>
                            </div>
                        ))}
                    </div>
                    {forecast && (
                        <div className="mt-4 pt-3 border-t border-white/[0.06]">
                            <p className="text-xs text-slate-500 uppercase tracking-wider font-medium mb-2">24h Demand Forecast</p>
                            <p className="text-sm text-slate-300">{forecast.recommendation === 'pre-provision' ? '⚡ Recommend pre-provisioning — demand spike predicted' :
                                forecast.recommendation === 'scale-down' ? '📉 Scale down — demand trending lower' : '✅ Hold current capacity'}</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
