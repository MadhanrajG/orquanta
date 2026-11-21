import { useState, useEffect, useMemo, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../App.jsx'
import {
  Brain, Search, Filter, Zap, ExternalLink, Star, Cpu,
  ChevronDown, Layers, Eye, Mic, Code2, MessageSquare, Box,
  ArrowRight, TrendingUp, Clock, GitBranch, AlertTriangle,
  CheckCircle, XCircle, Info, Shield, Download, RefreshCw,
  Play, Settings, Server, BarChart2, Package, Lock
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════════
   OrQuanta Model Hub — Phase 3 — Live backend integration
   ═══════════════════════════════════════════════════════════════════ */

const API = import.meta.env.VITE_API_BASE_URL || ''

const CATEGORIES = [
  { id: 'all',        label: 'All Models',    icon: Layers,       color: '#7C6BF0' },
  { id: 'llm',        label: 'Language',      icon: MessageSquare,color: '#7C6BF0' },
  { id: 'vision',     label: 'Vision',        icon: Eye,          color: '#F472B6' },
  { id: 'audio',      label: 'Audio',         icon: Mic,          color: '#10B981' },
  { id: 'code',       label: 'Code',          icon: Code2,        color: '#F59E0B' },
  { id: 'embedding',  label: 'Embeddings',    icon: Box,          color: '#06B6D4' },
]

const LICENCE_BADGE = {
  true:  { label: 'Commercial OK',   color: '#10B981', bg: 'rgba(16,185,129,0.1)', icon: CheckCircle },
  false: { label: 'Non-Commercial',  color: '#F59E0B', bg: 'rgba(245,158,11,0.1)', icon: AlertTriangle },
  null:  { label: 'Licence Unknown', color: '#94A3B8', bg: 'rgba(148,163,184,0.1)', icon: Info },
}

const STATUS_COLOUR = {
  compatible:                 '#10B981',
  compatible_with_constraints:'#F59E0B',
  incompatible:               '#EF4444',
  insufficient_information:   '#94A3B8',
}

// ─── Fallback static data shown while API loads ───────────────────────────
const STATIC_FALLBACK = [
  { model_id: 'meta-llama/Llama-3.1-70B-Instruct', name: 'LLaMA 3.1 70B', publisher: 'Meta AI',
    model_family: 'llm', param_count: '70B', licence: 'llama3', commercial_ok: true,
    vram_fp16_gb: 140, gpu_min: '2×A100 80GB', tags: ['Production', '128K Context'],
    hf_downloads: 0, trending: true, supported_engines: ['vllm', 'sglang'] },
  { model_id: 'microsoft/phi-4', name: 'Phi-4', publisher: 'Microsoft Research',
    model_family: 'llm', param_count: '14B', licence: 'mit', commercial_ok: true,
    vram_fp16_gb: 28, gpu_min: '1×A10 24GB', tags: ['MIT License', 'Reasoning'],
    hf_downloads: 0, trending: true, supported_engines: ['vllm'] },
]

// ─── Hooks ────────────────────────────────────────────────────────────────

function useModels(token) {
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)
  const [isLive, setIsLive] = useState(false)

  useEffect(() => {
    if (!token) { setModels(STATIC_FALLBACK); setLoading(false); return }
    fetch(`${API}/api/v1/models`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(data => {
        const list = data.models || []
        setModels(list.length ? list : STATIC_FALLBACK)
        setIsLive(list.length > 0)
        setError(null)
      })
      .catch(e => { setModels(STATIC_FALLBACK); setError(e.message) })
      .finally(() => setLoading(false))
  }, [token])

  return { models, loading, error, isLive }
}

function useHFSearch(token) {
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)

  const search = useCallback(async (query) => {
    if (!query || query.length < 2) { setResults([]); return }
    setSearching(true)
    try {
      const r = await fetch(`${API}/api/v1/models/search/hf?q=${encodeURIComponent(query)}&limit=12`,
        { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) { const d = await r.json(); setResults(d.results || []) }
    } catch { /* network error */ }
    finally { setSearching(false) }
  }, [token])

  return { results, searching, search }
}

function useCompatibility(token) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const check = useCallback(async (payload) => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/api/v1/models/check-compatibility`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(payload),
      })
      if (r.ok) setResult(await r.json())
    } catch { /* network */ }
    finally { setLoading(false) }
  }, [token])

  return { result, loading, check }
}

// ─── Sub-components ───────────────────────────────────────────────────────

function LiveBadge({ isLive }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      fontSize: 11, fontWeight: 600, letterSpacing: '0.03em',
      color: isLive ? '#10B981' : '#F59E0B',
      background: isLive ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)',
      border: `1px solid ${isLive ? 'rgba(16,185,129,0.25)' : 'rgba(245,158,11,0.25)'}`,
      borderRadius: 20, padding: '2px 10px',
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%',
        background: isLive ? '#10B981' : '#F59E0B',
        animation: isLive ? 'pulse 2s infinite' : 'none',
      }} />
      {isLive ? 'Live Registry' : 'Demo Data'}
    </span>
  )
}

function LicenceBadge({ commercial_ok }) {
  const cfg = LICENCE_BADGE[String(commercial_ok)] ?? LICENCE_BADGE['null']
  const Icon = cfg.icon
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      fontSize: 10, fontWeight: 600, color: cfg.color, background: cfg.bg,
      border: `1px solid ${cfg.color}33`, borderRadius: 20, padding: '2px 8px',
    }}>
      <Icon size={10} /> {cfg.label}
    </span>
  )
}

function EngineChip({ engine }) {
  const colours = { vllm: '#7C6BF0', sglang: '#06B6D4', transformers: '#10B981', llamacpp: '#F59E0B' }
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, color: colours[engine] || '#94A3B8',
      background: (colours[engine] || '#94A3B8') + '18',
      border: `1px solid ${(colours[engine] || '#94A3B8')}33`,
      borderRadius: 4, padding: '1px 6px', textTransform: 'uppercase', letterSpacing: '0.05em',
    }}>
      {engine}
    </span>
  )
}

function CompatibilityIndicator({ status }) {
  const colour = STATUS_COLOUR[status] || '#94A3B8'
  const labels = {
    compatible: 'Compatible',
    compatible_with_constraints: 'Constraints',
    incompatible: 'Incompatible',
    insufficient_information: 'Unknown',
  }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      fontSize: 11, fontWeight: 600, color: colour,
      background: colour + '15', border: `1px solid ${colour}33`,
      borderRadius: 20, padding: '2px 10px',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: colour }} />
      {labels[status] || status}
    </span>
  )
}

function ModelCard({ model, onDeploy, onCheckCompat }) {
  const [expanded, setExpanded] = useState(false)
  const vram = model.vram_fp16_gb
    ? `${model.vram_fp16_gb} GB FP16 / ${(model.vram_fp16_gb * 0.52).toFixed(0)} GB INT8`
    : null

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      style={{
        background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 12, padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 10,
        transition: 'border-color 0.2s, box-shadow 0.2s',
      }}
      whileHover={{ borderColor: 'rgba(124,107,240,0.35)', boxShadow: '0 4px 24px rgba(124,107,240,0.08)' }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, justifyContent: 'space-between' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#F1F5F9', whiteSpace: 'nowrap' }}>
              {model.name}
            </span>
            {model.trending && (
              <span style={{ fontSize: 10, fontWeight: 700, color: '#F59E0B', background: 'rgba(245,158,11,0.1)',
                border: '1px solid rgba(245,158,11,0.25)', borderRadius: 20, padding: '1px 7px' }}>
                Trending
              </span>
            )}
          </div>
          <div style={{ fontSize: 11, color: '#64748B', marginTop: 2 }}>{model.publisher}</div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
          {model.param_count && (
            <span style={{ fontSize: 12, fontWeight: 700, color: '#7C6BF0', background: 'rgba(124,107,240,0.1)',
              borderRadius: 6, padding: '2px 8px', border: '1px solid rgba(124,107,240,0.2)' }}>
              {model.param_count}
            </span>
          )}
        </div>
      </div>

      {/* Licence + Engines */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <LicenceBadge commercial_ok={model.commercial_ok} />
        <span style={{ fontSize: 10, color: '#475569' }}>{model.licence}</span>
        <span style={{ flex: 1 }} />
        {(model.supported_engines || []).map(e => <EngineChip key={e} engine={e} />)}
      </div>

      {/* Description */}
      {model.description && (
        <p style={{ fontSize: 12, color: '#94A3B8', margin: 0, lineHeight: 1.5,
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {model.description}
        </p>
      )}

      {/* VRAM / GPU */}
      {(vram || model.gpu_min) && (
        <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#64748B' }}>
          {vram && <span><Cpu size={11} style={{ marginRight: 4 }} />{vram}</span>}
          {model.gpu_min && <span>Min: {model.gpu_min}</span>}
        </div>
      )}

      {/* Tags */}
      {model.tags?.length > 0 && (
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
          {model.tags.slice(0, 4).map(t => (
            <span key={t} style={{ fontSize: 10, color: '#475569', background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.07)', borderRadius: 4, padding: '1px 7px' }}>
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
        <button
          onClick={() => onCheckCompat(model)}
          style={{ flex: 1, fontSize: 12, fontWeight: 600, color: '#94A3B8',
            background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.09)',
            borderRadius: 7, padding: '7px 12px', cursor: 'pointer', display: 'flex',
            alignItems: 'center', justifyContent: 'center', gap: 5 }}
        >
          <Cpu size={12} /> Check Fit
        </button>
        <button
          onClick={() => onDeploy(model)}
          style={{ flex: 1, fontSize: 12, fontWeight: 700, color: '#fff',
            background: 'linear-gradient(135deg, #7C6BF0, #5B50D6)',
            border: 'none', borderRadius: 7, padding: '7px 14px', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}
        >
          <Zap size={12} /> Deploy
        </button>
      </div>
    </motion.div>
  )
}

function CompatibilityModal({ model, token, onClose }) {
  const [gpu, setGpu]   = useState('a100-80gb')
  const [count, setCount] = useState(1)
  const [quant, setQuant] = useState('int8')
  const [engine, setEngine] = useState((model.supported_engines || ['vllm'])[0] || 'vllm')
  const { result, loading, check } = useCompatibility(token)

  useEffect(() => {
    if (model?.vram_fp16_gb) check({ model_id: model.model_id, gpu_model: gpu, gpu_count: count, quantisation: quant, engine })
  }, [model, gpu, count, quant, engine])

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }}
        style={{ background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 16,
          padding: 28, maxWidth: 540, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#F1F5F9' }}>GPU Compatibility Check</div>
            <div style={{ fontSize: 12, color: '#64748B', marginTop: 2 }}>{model.name}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#64748B',
            cursor: 'pointer', fontSize: 20 }}>×</button>
        </div>

        {/* Config selectors */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
          {[
            { label: 'GPU Model', value: gpu, set: setGpu, options: [
              ['a100-80gb','A100 80GB'],['a100-40gb','A100 40GB'],['h100-sxm','H100 SXM'],
              ['a40','A40 48GB'],['a10','A10 24GB'],['l40s','L40S 48GB'],['t4','T4 16GB'],
              ['rtx-4090','RTX 4090'],['v100-32gb','V100 32GB'],
            ]},
            { label: 'GPU Count', value: count, set: v => setCount(Number(v)), options: [[1,'1'],[2,'2'],[4,'4'],[8,'8']] },
            { label: 'Quantisation', value: quant, set: setQuant, options: [
              ['fp16','FP16'],['int8','INT8'],['int4','INT4'],['awq','AWQ'],['gptq','GPTQ'],
            ]},
            { label: 'Engine', value: engine, set: setEngine, options:
              (model.supported_engines || ['vllm']).map(e => [e, e.toUpperCase()]) },
          ].map(({ label, value, set, options }) => (
            <div key={label}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#64748B', marginBottom: 5 }}>{label}</div>
              <select value={value} onChange={e => set(e.target.value)}
                style={{ width: '100%', background: '#1E293B', border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 7, color: '#F1F5F9', fontSize: 13, padding: '7px 10px' }}>
                {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          ))}
        </div>

        {/* Result */}
        {loading && <div style={{ textAlign: 'center', color: '#64748B', fontSize: 13, padding: 20 }}>
          <RefreshCw size={16} style={{ animation: 'spin 1s linear infinite', marginBottom: 8, display: 'block', margin: '0 auto 8px' }} />
          Checking compatibility...
        </div>}

        {result && !loading && (
          <div style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${STATUS_COLOUR[result.status]}33`,
            borderRadius: 10, padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <CompatibilityIndicator status={result.status} />
              <span style={{ fontSize: 12, color: '#64748B' }}>
                {result.total_vram_available_gb} GB available · {result.estimated_vram_required_gb} GB required
              </span>
            </div>

            {result.reasons?.map((r, i) => (
              <div key={i} style={{ fontSize: 12, color: '#94A3B8', marginBottom: 6, lineHeight: 1.5 }}>{r}</div>
            ))}
            {result.constraints?.map((c, i) => (
              <div key={i} style={{ fontSize: 12, color: '#F59E0B', marginTop: 6, display: 'flex', gap: 6 }}>
                <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: 2 }} />{c}
              </div>
            ))}
            {result.warnings?.map((w, i) => (
              <div key={i} style={{ fontSize: 11, color: '#64748B', marginTop: 4, display: 'flex', gap: 6 }}>
                <Info size={11} style={{ flexShrink: 0, marginTop: 2 }} />{w}
              </div>
            ))}
            {result.estimated_tokens_per_second && (
              <div style={{ marginTop: 10, fontSize: 12, color: '#7C6BF0', fontWeight: 600 }}>
                Estimated throughput: ~{result.estimated_tokens_per_second.toLocaleString()} tok/s
                <span style={{ fontSize: 10, color: '#64748B', fontWeight: 400, marginLeft: 6 }}>
                  (rough estimate — actual depends on batch size and kernels)
                </span>
              </div>
            )}
          </div>
        )}
      </motion.div>
    </motion.div>
  )
}

function HFSearchPanel({ token, onImport }) {
  const [q, setQ] = useState('')
  const { results, searching, search } = useHFSearch(token)

  useEffect(() => {
    const t = setTimeout(() => search(q), 400)
    return () => clearTimeout(t)
  }, [q])

  return (
    <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.07)',
      borderRadius: 10, padding: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: '#F1F5F9', marginBottom: 12,
        display: 'flex', alignItems: 'center', gap: 8 }}>
        <Download size={14} color="#7C6BF0" /> Discover on Hugging Face Hub
      </div>
      <input
        value={q}
        onChange={e => setQ(e.target.value)}
        placeholder="Search HF Hub — e.g. mistral, gemma, falcon..."
        style={{ width: '100%', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 7, color: '#F1F5F9', fontSize: 13, padding: '8px 12px', boxSizing: 'border-box' }}
      />
      {searching && <div style={{ fontSize: 11, color: '#64748B', marginTop: 8 }}>Searching HF Hub...</div>}
      {results.length > 0 && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 300, overflowY: 'auto' }}>
          {results.map(r => (
            <div key={r.hf_id} style={{ display: 'flex', alignItems: 'center', gap: 10,
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)',
              borderRadius: 8, padding: '8px 12px' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#F1F5F9', whiteSpace: 'nowrap',
                  overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.hf_id}</div>
                <div style={{ display: 'flex', gap: 6, marginTop: 3 }}>
                  <LicenceBadge commercial_ok={r.licence_info?.commercial ?? null} />
                  <span style={{ fontSize: 10, color: '#64748B' }}>{r.hf_downloads?.toLocaleString() || 0} downloads</span>
                </div>
              </div>
              {r.in_registry ? (
                <span style={{ fontSize: 10, color: '#10B981', fontWeight: 600 }}>In Registry</span>
              ) : (
                <button onClick={() => onImport(r)}
                  style={{ fontSize: 11, fontWeight: 600, color: '#7C6BF0', background: 'rgba(124,107,240,0.1)',
                    border: '1px solid rgba(124,107,240,0.2)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer' }}>
                  Import
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────

export default function ModelHubPage() {
  const { token } = useAuth()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [commercialOnly, setCommercialOnly] = useState(false)
  const [compatModal, setCompatModal] = useState(null)
  const [showHFSearch, setShowHFSearch] = useState(false)
  const [notification, setNotification] = useState(null)

  const { models, loading, error, isLive } = useModels(token)

  const filtered = useMemo(() => {
    let list = models
    if (category !== 'all') {
      list = list.filter(m => {
        const fam = (m.model_family || '').toLowerCase()
        const tags = (m.tags || []).join(' ').toLowerCase()
        if (category === 'llm')       return ['llama','mistral','qwen','gemma','deepseek','phi','gpt','claude','llm'].some(k => fam.includes(k))
        if (category === 'code')      return tags.includes('code') || fam.includes('code') || (m.name||'').toLowerCase().includes('code')
        if (category === 'embedding') return fam.includes('embed') || fam.includes('bge') || tags.includes('embed')
        if (category === 'vision')    return tags.includes('vision') || tags.includes('image') || fam.includes('vision')
        if (category === 'audio')     return tags.includes('audio') || tags.includes('speech') || fam.includes('whisper')
        return true
      })
    }
    if (commercialOnly) list = list.filter(m => m.commercial_ok === true)
    if (search) {
      const q = search.toLowerCase()
      list = list.filter(m =>
        (m.name||'').toLowerCase().includes(q) ||
        (m.publisher||'').toLowerCase().includes(q) ||
        (m.description||'').toLowerCase().includes(q) ||
        (m.tags||[]).join(' ').toLowerCase().includes(q) ||
        (m.model_id||'').toLowerCase().includes(q)
      )
    }
    return list
  }, [models, category, commercialOnly, search])

  const handleDeploy = useCallback((model) => {
    setNotification({ type: 'info', message: `Deployment wizard for ${model.name} — coming in Phase 3F.` })
    setTimeout(() => setNotification(null), 4000)
  }, [])

  const handleImport = useCallback((hfModel) => {
    setNotification({ type: 'success', message: `Model ${hfModel.hf_id} imported into session registry.` })
    setTimeout(() => setNotification(null), 3000)
  }, [])

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 20px' }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Brain size={22} color="#7C6BF0" />
            <h1 style={{ fontSize: 22, fontWeight: 800, color: '#F1F5F9', margin: 0 }}>Model Hub</h1>
            <LiveBadge isLive={isLive} />
          </div>
          <p style={{ fontSize: 13, color: '#64748B', margin: '6px 0 0' }}>
            Discover, evaluate and deploy open-source AI models. GPU compatibility checked before deployment.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => setShowHFSearch(v => !v)}
            style={{ fontSize: 12, fontWeight: 600, color: showHFSearch ? '#7C6BF0' : '#94A3B8',
              background: showHFSearch ? 'rgba(124,107,240,0.1)' : 'rgba(255,255,255,0.04)',
              border: `1px solid ${showHFSearch ? 'rgba(124,107,240,0.3)' : 'rgba(255,255,255,0.09)'}`,
              borderRadius: 8, padding: '8px 14px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}>
            <Download size={13} /> HF Hub
          </button>
          <button onClick={() => navigate('/goals')}
            style={{ fontSize: 12, fontWeight: 700, color: '#fff',
              background: 'linear-gradient(135deg, #7C6BF0, #5B50D6)',
              border: 'none', borderRadius: 8, padding: '8px 16px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 5 }}>
            <Zap size={12} /> Custom Deploy
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)',
          borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: '#F59E0B',
          display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertTriangle size={13} />
          Could not load live registry ({error}). Showing curated fallback data.
        </div>
      )}

      {/* Notification */}
      <AnimatePresence>
        {notification && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            style={{ background: notification.type === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(124,107,240,0.1)',
              border: `1px solid ${notification.type === 'success' ? 'rgba(16,185,129,0.25)' : 'rgba(124,107,240,0.25)'}`,
              borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 12,
              color: notification.type === 'success' ? '#10B981' : '#7C6BF0' }}>
            {notification.message}
          </motion.div>
        )}
      </AnimatePresence>

      {/* HF Search Panel */}
      <AnimatePresence>
        {showHFSearch && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            style={{ overflow: 'hidden', marginBottom: 16 }}>
            <HFSearchPanel token={token} onImport={handleImport} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: '1 1 240px', minWidth: 200 }}>
          <Search size={14} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: '#475569' }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search models..."
            style={{ width: '100%', paddingLeft: 32, paddingRight: 12, paddingTop: 9, paddingBottom: 9,
              background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.09)',
              borderRadius: 8, color: '#F1F5F9', fontSize: 13, boxSizing: 'border-box' }}
          />
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {CATEGORIES.map(cat => {
            const Icon = cat.icon
            const active = category === cat.id
            return (
              <button key={cat.id} onClick={() => setCategory(cat.id)}
                style={{ fontSize: 12, fontWeight: active ? 700 : 500,
                  color: active ? cat.color : '#64748B',
                  background: active ? `${cat.color}15` : 'rgba(255,255,255,0.03)',
                  border: `1px solid ${active ? cat.color + '33' : 'rgba(255,255,255,0.08)'}`,
                  borderRadius: 7, padding: '6px 12px', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 5 }}>
                <Icon size={12} /> {cat.label}
              </button>
            )
          })}
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12,
          color: commercialOnly ? '#10B981' : '#64748B', cursor: 'pointer' }}>
          <input type="checkbox" checked={commercialOnly} onChange={e => setCommercialOnly(e.target.checked)}
            style={{ accentColor: '#10B981' }} />
          <Shield size={12} /> Commercial OK only
        </label>
      </div>

      {/* Stats bar */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 20, fontSize: 12, color: '#475569' }}>
        <span>{filtered.length} of {models.length} models</span>
        {search && <button onClick={() => setSearch('')}
          style={{ fontSize: 11, color: '#EF4444', background: 'rgba(239,68,68,0.06)',
            border: '1px solid rgba(239,68,68,0.15)', borderRadius: 6, padding: '2px 8px', cursor: 'pointer' }}>
          Clear
        </button>}
      </div>

      {/* Loading state */}
      {loading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
          {[1,2,3,4,5,6].map(i => (
            <div key={i} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: 12, padding: 20, height: 180, animation: 'shimmer 1.5s infinite' }} />
          ))}
        </div>
      )}

      {/* Model grid */}
      {!loading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
          <AnimatePresence mode="popLayout">
            {filtered.map((model, i) => (
              <ModelCard
                key={model.model_id || model.id}
                model={model}
                onDeploy={handleDeploy}
                onCheckCompat={m => setCompatModal(m)}
              />
            ))}
          </AnimatePresence>
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#94A3B8' }}>
          <Search size={32} style={{ display: 'block', margin: '0 auto 12px', opacity: 0.4 }} />
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>No models found</div>
          <div style={{ fontSize: 13 }}>Try adjusting your search or filters</div>
        </div>
      )}

      {/* Compatibility Modal */}
      <AnimatePresence>
        {compatModal && (
          <CompatibilityModal
            model={compatModal}
            token={token}
            onClose={() => setCompatModal(null)}
          />
        )}
      </AnimatePresence>

      {/* Footer CTA */}
      <div style={{ marginTop: 32, background: 'rgba(124,107,240,0.05)',
        border: '1px solid rgba(124,107,240,0.15)', borderRadius: 12, padding: '16px 20px',
        display: 'flex', alignItems: 'center', gap: 14 }}>
        <Brain size={20} color="#7C6BF0" style={{ flexShrink: 0 }} />
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#F1F5F9' }}>Submit any Hugging Face model</div>
          <div style={{ fontSize: 12, color: '#64748B', marginTop: 2 }}>
            Paste any HF model URL as a goal — OrQuanta will auto-configure GPU, provider and runtime.
          </div>
        </div>
        <button onClick={() => navigate('/goals')} style={{ marginLeft: 'auto', flexShrink: 0,
          fontSize: 12, fontWeight: 700, color: '#fff', background: 'linear-gradient(135deg,#7C6BF0,#5B50D6)',
          border: 'none', borderRadius: 8, padding: '8px 16px', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 5 }}>
          <ArrowRight size={13} /> Open Goals
        </button>
      </div>
    </motion.div>
  )
}
