/**
 * OrQuanta - Live GPU Pricing Page
 * Shows real-time GPU spot prices from Lambda Labs, RunPod, Vast.ai, and AWS
 * Data sourced from /api/v1/pricing (refreshed every 60s server-side)
 */
import { useState, useEffect } from'react'
import { motion } from 'framer-motion'
import { RefreshCw, TrendingDown, Zap, Filter, ChevronDown, ExternalLink } from'lucide-react'

const API = import.meta.env.VITE_API_URL ||''

const PROVIDER_INFO = {
 lambda: { label:'Lambda Labs', color:'#7C6BF0', dot:'#9B8BF4', url:'https://cloud.lambdalabs.com' },
 runpod: { label:'RunPod', color:'#7C6BF0', dot:'#7C6BF0', url:'https://www.runpod.io' },
 vastai: { label:'Vast.ai', color:'#10B981', dot:'#10B981', url:'https://vast.ai' },
 aws: { label:'AWS', color:'#F59E0B', dot:'#F59E0B', url:'https://aws.amazon.com/ec2/pricing' },
}

const GPU_CLASSES = ['All','A10','A100','H100','RTX 4090','RTX 3090','T4','V100']

export default function LivePricing() {
 const [listings, setListings] = useState([])
 const [summary, setSummary] = useState(null)
 const [health, setHealth] = useState(null)
 const [loading, setLoading] = useState(true)
 const [lastRefresh, setLastRefresh] = useState(null)
 const [filter, setFilter] = useState({ gpu:'All', maxPrice:'', minVram:'', provider:'' })
 const [view, setView] = useState('listings') //'listings' |'summary'

 const fetchData = async () => {
 try {
 const params = new URLSearchParams()
 if (filter.gpu !=='All') params.set('gpu_type', filter.gpu)
 if (filter.maxPrice) params.set('max_price', filter.maxPrice)
 if (filter.minVram) params.set('min_vram', filter.minVram)
 if (filter.provider) params.set('provider', filter.provider)
 params.set('limit','100')

 const [pRes, sRes, hRes] = await Promise.all([
 fetch(`${API}/api/v1/pricing?${params}`),
 fetch(`${API}/api/v1/pricing/summary`),
 fetch(`${API}/api/v1/pricing/providers`),
 ])

 if (pRes.ok) { const d = await pRes.json(); setListings(d.listings || []); setLastRefresh(d.updated_at) }
 if (sRes.ok) { const d = await sRes.json(); setSummary(d) }
 if (hRes.ok) { const d = await hRes.json(); setHealth(d) }
 } catch (e) {
 console.error('Pricing fetch error:', e)
 } finally {
 setLoading(false)
 }
 }

 useEffect(() => { fetchData() }, [filter])

 const cheapestByClass = summary?.summary || {}

 return (
 <motion.div
    initial={{ opacity: 0, y: 12 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
    className="space-y-6 animate-fade-in">
 {/* Header */}
 <div className="flex items-start justify-between flex-wrap gap-4">
 <div>
 <h1 className="text-2xl font-bold text-slate-800" style={{ display:'flex', alignItems:'center', gap: 10 }}>
 <span style={{ fontSize: 24 }}></span> Live GPU Pricing
 </h1>
 <p className="text-slate-500 text-sm mt-1">
 Real-time prices from Lambda Labs . RunPod . Vast.ai . AWS - sorted cheapest first
 </p>
 {lastRefresh && (
 <p style={{ fontSize: 11, color:'#94A3B8', marginTop: 4 }}>
 Last updated: {new Date(lastRefresh).toLocaleTimeString()}
 </p>
 )}
 </div>
 <button onClick={fetchData} disabled={loading}
 style={{
 display:'flex', alignItems:'center', gap: 6, padding:'8px 16px',
 background:'rgba(124,107,240,0.08)', border:'1px solid rgba(124,107,240,0.25)',
 borderRadius: 8, color:'#7C6BF0', cursor:'pointer', fontSize: 13, fontWeight: 600
 }}>
 <RefreshCw size={14} className={loading ?'animate-spin' :''} />
 {loading ?'Refreshing...' :'Refresh Prices'}
 </button>
 </div>

 {/* Provider Health Strip */}
 {health && (
 <div style={{ display:'flex', gap: 8, flexWrap:'wrap' }}>
 {Object.entries(health.providers).map(([key, info]) => {
 const pi = PROVIDER_INFO[key] || {}
 const isLive = info.status ==='ok'
 return (
 <div key={key} style={{
 display:'flex', alignItems:'center', gap: 6,
 padding:'5px 12px', borderRadius: 20,
 background: `${pi.dot ||'#888'}0A`,
 border: `1px solid ${pi.dot ||'#888'}20`,
 }}>
 <span style={{
 width: 7, height: 7, borderRadius:'50%',
 background: isLive ?'#10B981' : info.status ==='fallback' ?'#F59E0B' :'#EF4444',
 display:'inline-block',
 animation: isLive ? 'telemetryPulse 2s ease-in-out infinite' : 'none',
 }} />
 <span style={{ fontSize: 12, fontWeight: 600, color: pi.color ||'#0F172A' }}>
 {info.name}
 </span>
 <span style={{ fontSize: 10, color:'#94A3B8' }}>
 {isLive ?'Live' : info.status ==='fallback' ?'Cached' :'Offline'}
 </span>
 </div>
 )
 })}
 </div>
 )}

 {/* View toggle */}
 <div style={{ display:'flex', gap: 8 }}>
 {[['listings','All Listings'], ['summary','Best Per GPU Class']].map(([v, label]) => (
 <button key={v} onClick={() => setView(v)} style={{
 padding:'8px 18px', borderRadius: 8, border:'none', cursor:'pointer',
 fontSize: 13, fontWeight: 600,
 background: view === v ?'linear-gradient(135deg,#7C6BF0,#9B8BF4)' :'#F1F5F9',
 color: view === v ?'#fff' :'#475569',
 }}>{label}</button>
 ))}
 </div>

 {view ==='summary' && summary && (
 <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
 {Object.entries(cheapestByClass).map(([gpuClass, data]) => {
 const best = data.cheapest
 const pi = PROVIDER_INFO[best.provider] || {}
 return (
 <div key={gpuClass} className="glass-card p-5">
 <div style={{ fontWeight: 700, color: '#0F172A', marginBottom: 4, fontSize: 14 }}>{gpuClass}</div>
 <div style={{ fontSize: 26, fontWeight: 800, color:'#10B981', marginBottom: 4, fontFamily: "'JetBrains Mono', monospace", fontVariantNumeric: 'tabular-nums' }}>
 {best.price_per_hr_fmt}
 </div>
 <div style={{ display:'flex', gap: 8, alignItems:'center', marginBottom: 8 }}>
 <span style={{ fontSize: 12, color: pi.color ||'#0F172A' }}>via {pi.label || best.provider_label}</span>
 <span style={{ fontSize: 11, color:'#94A3B8' }}>{best.vram_gb}GB VRAM</span>
 </div>
 {data.savings_vs_aws_pct > 0 && (
 <div style={{
 display:'flex', alignItems:'center', gap: 4,
 color:'#10B981', fontSize: 12, fontWeight: 600
 }}>
 <TrendingDown size={12} />
 {data.savings_vs_aws_pct}% cheaper than AWS
 </div>
 )}
 <div style={{ marginTop: 8, fontSize: 11, color:'#94A3B8' }}>
 {data.options_count} option{data.options_count !== 1 ?'s' :''} available
 </div>
 </div>
 )
 })}
 </div>
 )}

 {view ==='listings' && (
 <>
 {/* Filters */}
 <div className="glass-card p-4" style={{ display:'flex', gap: 12, flexWrap:'wrap', alignItems:'center' }}>
 <div style={{ display:'flex', alignItems:'center', gap: 6, color:'#475569', fontSize: 13 }}>
 <Filter size={14} /> Filters:
 </div>
 <select value={filter.gpu} onChange={e => setFilter(p => ({ ...p, gpu: e.target.value }))}
 style={{
 padding:'5px 10px', borderRadius: 6, background:'#FFFFFF',
 border:'1px solid #E2E8F0', color:'#0F172A', fontSize: 13
 }}>
 {GPU_CLASSES.map(g => <option key={g} value={g}>{g}</option>)}
 </select>
 <input type="number" placeholder="Max $/hr" value={filter.maxPrice}
 onChange={e => setFilter(p => ({ ...p, maxPrice: e.target.value }))}
 style={{
 width: 100, padding:'5px 10px', borderRadius: 6,
 background:'#FFFFFF', border:'1px solid #E2E8F0',
 color:'#0F172A', fontSize: 13
 }} />
 <input type="number" placeholder="Min VRAM GB" value={filter.minVram}
 onChange={e => setFilter(p => ({ ...p, minVram: e.target.value }))}
 style={{
 width: 120, padding:'5px 10px', borderRadius: 6,
 background:'#FFFFFF', border:'1px solid #E2E8F0',
 color:'#0F172A', fontSize: 13
 }} />
 <select value={filter.provider} onChange={e => setFilter(p => ({ ...p, provider: e.target.value }))}
 style={{
 padding:'5px 10px', borderRadius: 6, background:'#FFFFFF',
 border:'1px solid #E2E8F0', color:'#0F172A', fontSize: 13
 }}>
 <option value="">All Providers</option>
 {Object.entries(PROVIDER_INFO).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
 </select>
 {(filter.gpu !=='All' || filter.maxPrice || filter.minVram || filter.provider) && (
 <button onClick={() => setFilter({ gpu:'All', maxPrice:'', minVram:'', provider:'' })}
 style={{
 padding:'4px 10px', borderRadius: 6, border:'1px solid rgba(239,68,68,0.3)',
 background:'rgba(239,68,68,0.06)', color:'#EF4444', fontSize: 12, cursor:'pointer'
 }}>
 Clear
 </button>
 )}
 <span style={{ marginLeft:'auto', fontSize: 12, color:'#94A3B8' }}>
 {listings.length} results
 </span>
 </div>

 {/* Listings Table */}
 <div className="glass-card overflow-hidden">
 <div style={{ overflowX:'auto' }}>
 <table style={{ width:'100%', borderCollapse:'collapse', fontSize: 13 }}>
 <thead>
 <tr style={{ borderBottom:'1px solid #E2E8F0', background: '#F8FAFC' }}>
 {['Provider','GPU','VRAM','Count','Region','Price / hr','8hr Cost','Tags',''].map(h => (
 <th key={h} style={{
 padding:'10px 14px', textAlign:'left',
 fontSize: 11, fontWeight: 700, color:'#475569',
 textTransform:'uppercase', letterSpacing: 1, whiteSpace:'nowrap'
 }}>
 {h}
 </th>
 ))}
 </tr>
 </thead>
 <tbody>
 {loading ? (
 Array.from({ length: 6 }).map((_, i) => (
 <tr key={i} style={{ borderBottom:'1px solid #F1F5F9' }}>
 {Array.from({ length: 9 }).map((__, j) => (
 <td key={j} style={{ padding:'12px 14px' }}>
 <div style={{
 height: 14, background:'#E2E8F0',
 borderRadius: 4, width: j === 1 ? 120 : 60,
 animation:'pulse 1.5s infinite'
 }} />
 </td>
 ))}
 </tr>
 ))
 ) : listings.length === 0 ? (
 <tr>
 <td colSpan={9} style={{ textAlign:'center', padding:'40px 20px', color:'#94A3B8' }}>
 No GPU listings found for your filters. Try adjusting them.
 </td>
 </tr>
 ) : listings.map((l, i) => {
 const pi = PROVIDER_INFO[l.provider] || {}
 const isAws = l.provider ==='aws'
 return (
 <tr key={`${l.provider}-${l.instance_id}-${i}`}
 style={{
 borderBottom:'1px solid #F1F5F9',
 background: i % 2 === 0 ?'transparent' :'#FAFBFC',
 opacity: isAws ? 0.6 : 1
 }}
 onMouseEnter={e => e.currentTarget.style.background = 'rgba(124,107,240,0.03)'}
 onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : '#FAFBFC'}>
 <td style={{ padding:'12px 14px' }}>
 <div style={{ display:'flex', alignItems:'center', gap: 6 }}>
 <span style={{
 width: 8, height: 8, borderRadius:'50%',
 background: pi.dot ||'#888', flexShrink: 0,
 animation: !isAws ? 'telemetryPulse 2s ease-in-out infinite' : 'none',
 }} />
 <span style={{ color: pi.color ||'#0F172A', fontWeight: 600, whiteSpace:'nowrap' }}>
 {l.provider_label}
 </span>
 </div>
 </td>
 <td style={{ padding:'12px 14px', color:'#0F172A', fontWeight: 600 }}>{l.gpu_model}</td>
 <td style={{ padding:'12px 14px', color:'#7C6BF0' }}>{l.vram_gb}GB</td>
 <td style={{ padding:'12px 14px', color:'#475569' }}>x{l.gpu_count}</td>
 <td style={{ padding:'12px 14px', color:'#94A3B8', fontSize: 11 }}>{l.region}</td>
 <td style={{ padding:'12px 14px' }}>
 <span style={{
 fontWeight: 800, fontSize: 15,
 color: isAws ?'#F59E0B' :'#10B981',
 fontFamily: "'JetBrains Mono', monospace",
 fontVariantNumeric: 'tabular-nums',
 }}>
 {l.price_per_hr_fmt}
 </span>
 {isAws && <span style={{ fontSize: 10, color:'#F59E0B', marginLeft: 4 }}>ref</span>}
 </td>
 <td style={{ padding:'12px 14px', color:'#475569', fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>{l.cost_8hr_fmt}</td>
 <td style={{ padding:'12px 14px' }}>
 <div style={{ display:'flex', gap: 4, flexWrap:'wrap' }}>
 {(l.tags || []).slice(0, 2).map(t => (
 <span key={t} style={{
 fontSize: 10, padding:'1px 6px',
 borderRadius: 999, background:'#EDE9FE',
 color:'#7C6BF0', border:'1px solid rgba(124,107,240,0.2)'
 }}>
 {t}
 </span>
 ))}
 </div>
 </td>
 <td style={{ padding:'12px 14px' }}>
 {!isAws && (
 <a href={pi.url} target="_blank" rel="noopener noreferrer"
 style={{
 color:'#7C6BF0', fontSize: 11, textDecoration:'none',
 display:'flex', alignItems:'center', gap: 3
 }}>
 <ExternalLink size={11} /> View
 </a>
 )}
 </td>
 </tr>
 )
 })}
 </tbody>
 </table>
 </div>
 </div>

 <p style={{ fontSize: 11, color:'#94A3B8', textAlign:'center' }}>
 Prices refreshed every 60 seconds. AWS shown as reference only.
 OrQuanta automatically routes your jobs to the cheapest available provider.
 </p>
 </>
 )}
 </motion.div>
 )
}
