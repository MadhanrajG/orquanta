// Copyright 2026 OrQuanta — Apache License 2.0
/**
 * OrQuanta Deployment Wizard — Phase 3F
 * Five-step guided model deployment workflow.
 * Uses real backend APIs for all state transitions.
 */
import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../App.jsx'
import {
  Brain, Server, MapPin, Shield, Zap, Check, X, AlertTriangle,
  ChevronRight, ChevronLeft, Cpu, RefreshCw, Info, Lock, Clock,
  CheckCircle, XCircle, Loader, ExternalLink, Copy, Eye, EyeOff
} from 'lucide-react'

const API = import.meta.env.VITE_API_BASE_URL || ''

// ─── Step config ─────────────────────────────────────────────────────────────

const STEPS = [
  { id: 1, label: 'Select Model',    icon: Brain,   key: 'model' },
  { id: 2, label: 'Engine & GPU',    icon: Cpu,     key: 'engine' },
  { id: 3, label: 'Provider',        icon: Server,  key: 'provider' },
  { id: 4, label: 'Review Policy',   icon: Shield,  key: 'review' },
  { id: 5, label: 'Deploy',          icon: Zap,     key: 'deploy' },
]

// ─── API helpers ──────────────────────────────────────────────────────────────

async function apiPost(path, body, token) {
  const r = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }))
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail))
  }
  return r.json()
}

async function apiGet(path, token) {
  const r = await fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

// ─── Status indicator ────────────────────────────────────────────────────────

const STATUS_STYLE = {
  APPROVED:         { color: '#10B981', bg: 'rgba(16,185,129,0.1)', icon: CheckCircle },
  REQUIRES_REVIEW:  { color: '#F59E0B', bg: 'rgba(245,158,11,0.1)', icon: AlertTriangle },
  BLOCKED:          { color: '#EF4444', bg: 'rgba(239,68,68,0.1)',  icon: XCircle },
  compatible:                 { color: '#10B981', bg: 'rgba(16,185,129,0.08)' },
  compatible_with_constraints:{ color: '#F59E0B', bg: 'rgba(245,158,11,0.08)' },
  incompatible:               { color: '#EF4444', bg: 'rgba(239,68,68,0.08)' },
  insufficient_information:   { color: '#94A3B8', bg: 'rgba(148,163,184,0.08)' },
}

// ─── Step 1: Model selection ──────────────────────────────────────────────────

function StepModel({ session, onNext, token }) {
  const [models, setModels] = useState([])
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(session?.model_id || '')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    apiGet('/api/v1/models', token)
      .then(d => setModels(d.models || []))
      .catch(e => setModels([]))  // fallback: show nothing, user searches HF
      .finally(() => setLoading(false))
  }, [token])

  const filtered = models.filter(m => {
    if (!search) return true
    const q = search.toLowerCase()
    return (m.name||'').toLowerCase().includes(q) || (m.model_id||'').toLowerCase().includes(q)
  })

  const handleNext = async () => {
    if (!selected) return
    setSubmitting(true)
    setError(null)
    try {
      await onNext({ model_id: selected })
    } catch (e) { setError(e.message) }
    finally { setSubmitting(false) }
  }

  const model = models.find(m => m.model_id === selected)

  return (
    <div>
      <input
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="Search models..."
        style={inputStyle}
      />
      {loading && <div style={hintStyle}>Loading registry...</div>}
      <div style={{ maxHeight: 320, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
        {filtered.map(m => (
          <button key={m.model_id}
            onClick={() => setSelected(m.model_id)}
            style={{
              ...rowStyle,
              borderColor: selected === m.model_id ? '#7C6BF0' : 'rgba(255,255,255,0.08)',
              background: selected === m.model_id ? 'rgba(124,107,240,0.07)' : 'rgba(255,255,255,0.02)',
            }}>
            <div style={{ flex: 1, textAlign: 'left' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#F1F5F9' }}>{m.name}</div>
              <div style={{ fontSize: 11, color: '#64748B' }}>{m.publisher} · {m.param_count} · {m.licence}</div>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {m.commercial_ok === true && <span style={tagStyle('#10B981')}>Commercial OK</span>}
              {m.commercial_ok === false && <span style={tagStyle('#F59E0B')}>Non-Commercial</span>}
              {m.commercial_ok === null && <span style={tagStyle('#94A3B8')}>Licence Unknown</span>}
            </div>
          </button>
        ))}
        {!loading && filtered.length === 0 && (
          <div style={hintStyle}>No models found. Use Goals to submit any HuggingFace model URL.</div>
        )}
      </div>
      {model && (
        <div style={{ marginTop: 12, padding: '10px 14px', background: 'rgba(124,107,240,0.06)',
          border: '1px solid rgba(124,107,240,0.2)', borderRadius: 8, fontSize: 12, color: '#94A3B8' }}>
          <strong style={{ color: '#7C6BF0' }}>{model.name}</strong> — {model.param_count} · GPU min: {model.gpu_min || 'unknown'} · VRAM FP16: {model.vram_fp16_gb ? `${model.vram_fp16_gb} GB` : 'unknown'}
        </div>
      )}
      {error && <div style={errorStyle}>{error}</div>}
      <WizardNav onNext={handleNext} nextDisabled={!selected || submitting} nextLabel={submitting ? 'Saving...' : 'Next: Engine & GPU'} />
    </div>
  )
}

// ─── Step 2: Engine + GPU ─────────────────────────────────────────────────────

function StepEngine({ session, onNext, onBack, token }) {
  const [engine, setEngine] = useState(session?.engine || 'vllm')
  const [quant, setQuant] = useState(session?.quantisation || 'int8')
  const [gpuModel, setGpuModel] = useState(session?.gpu_model || 'a100-80gb')
  const [gpuCount, setGpuCount] = useState(session?.gpu_count || 1)
  const [compat, setCompat] = useState(null)
  const [gpus, setGpus] = useState({})
  const [checking, setChecking] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    apiGet('/api/v1/models/gpus', token).then(d => setGpus(d.gpus || {})).catch(() => {})
  }, [token])

  const checkCompat = useCallback(async () => {
    setChecking(true)
    try {
      const r = await apiPost('/api/v1/models/check-compatibility', {
        model_id: session.model_id, gpu_model: gpuModel, gpu_count: gpuCount,
        quantisation: quant, engine,
      }, token)
      setCompat(r)
    } catch { /* silent */ }
    finally { setChecking(false) }
  }, [session?.model_id, gpuModel, gpuCount, quant, engine, token])

  useEffect(() => { if (session?.model_id) checkCompat() }, [gpuModel, gpuCount, quant, engine])

  const handleNext = async () => {
    if (compat?.status === 'incompatible') { setError('Selected hardware is incompatible with this model.'); return }
    setSubmitting(true); setError(null)
    try { await onNext({ engine, quantisation: quant, gpu_model: gpuModel, gpu_count: gpuCount }) }
    catch (e) { setError(e.message) }
    finally { setSubmitting(false) }
  }

  const compatStyle = STATUS_STYLE[compat?.status] || {}

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
        <SelectField label="Inference Engine" value={engine} onChange={setEngine}
          options={[['vllm','vLLM (recommended)'],['sglang','SGLang (high-throughput)'],['transformers','Transformers (compatible)']]} />
        <SelectField label="Quantisation" value={quant} onChange={setQuant}
          options={[['fp16','FP16 (full precision)'],['int8','INT8 (balanced)'],['int4','INT4 (memory-efficient)'],['awq','AWQ (optimised)'],['gptq','GPTQ (compressed)']]} />
        <SelectField label="GPU Model" value={gpuModel} onChange={setGpuModel}
          options={Object.keys(gpus).map(g => [g, g.toUpperCase()])} />
        <SelectField label="GPU Count" value={String(gpuCount)} onChange={v => setGpuCount(Number(v))}
          options={[['1','1×'],['2','2×'],['4','4×'],['8','8×']]} />
      </div>

      {/* Compatibility result */}
      {checking && <div style={hintStyle}><Loader size={12} style={{ animation: 'spin 1s linear infinite', marginRight: 6 }} />Checking compatibility...</div>}
      {compat && !checking && (
        <div style={{ padding: '12px 14px', background: compatStyle.bg, border: `1px solid ${compatStyle.color}33`,
          borderRadius: 8, marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: compatStyle.color, marginBottom: 6 }}>
            {compat.status?.replace(/_/g, ' ').toUpperCase()}
          </div>
          {compat.reasons?.map((r, i) => <div key={i} style={{ fontSize: 11, color: '#94A3B8', lineHeight: 1.5 }}>{r}</div>)}
          {compat.constraints?.map((c, i) => (
            <div key={i} style={{ fontSize: 11, color: '#F59E0B', marginTop: 4, display: 'flex', gap: 5 }}>
              <AlertTriangle size={10} style={{ flexShrink: 0, marginTop: 2 }} />{c}
            </div>
          ))}
          {compat.estimated_tokens_per_second && (
            <div style={{ fontSize: 11, color: '#7C6BF0', marginTop: 6 }}>
              ~{compat.estimated_tokens_per_second.toLocaleString()} tok/s estimated
              <span style={{ color: '#475569', marginLeft: 4 }}>(rough estimate)</span>
            </div>
          )}
        </div>
      )}

      {error && <div style={errorStyle}>{error}</div>}
      <WizardNav onBack={onBack} onNext={handleNext}
        nextDisabled={submitting || compat?.status === 'incompatible'}
        nextLabel={submitting ? 'Saving...' : 'Next: Provider'} />
    </div>
  )
}

// ─── Step 3: Provider + region ────────────────────────────────────────────────

function StepProvider({ session, onNext, onBack, token }) {
  const [provider, setProvider] = useState(session?.provider || 'runpod')
  const [region, setRegion] = useState(session?.region || 'us-east-1')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const hourlyRate = (session?.gpu_count || 1) * { runpod: 2.49, vastai: 1.89, lambda: 2.75 }[provider]

  const handleNext = async () => {
    setSubmitting(true); setError(null)
    try { await onNext({ provider, region }) }
    catch (e) { setError(e.message) }
    finally { setSubmitting(false) }
  }

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
        <SelectField label="GPU Provider" value={provider} onChange={setProvider}
          options={[['runpod','RunPod'],['vastai','Vast.ai'],['lambda','Lambda Labs']]} />
        <SelectField label="Region" value={region} onChange={setRegion}
          options={[['us-east-1','US East'],['us-west-2','US West'],['eu-west-1','EU West'],['ap-southeast-1','Asia Pacific']]} />
      </div>

      <div style={{ padding: '14px 16px', background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, marginBottom: 12 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#F1F5F9', marginBottom: 10 }}>Cost Estimate</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {[
            ['GPU Config', `${session?.gpu_count}× ${session?.gpu_model}`],
            ['Estimated Rate', `~$${hourlyRate?.toFixed(2)}/hr`],
            ['Provider', provider],
            ['Region', region],
          ].map(([k, v]) => (
            <div key={k}>
              <div style={{ fontSize: 10, color: '#475569', marginBottom: 2 }}>{k}</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#F1F5F9' }}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 10, fontSize: 11, color: '#64748B' }}>
          <Info size={11} style={{ marginRight: 4 }} />
          Actual cost determined at provisioning time from provider live pricing.
          This is an indicative estimate only.
        </div>
      </div>

      {error && <div style={errorStyle}>{error}</div>}
      <WizardNav onBack={onBack} onNext={handleNext}
        nextDisabled={submitting}
        nextLabel={submitting ? 'Saving...' : 'Next: Review Policy'} />
    </div>
  )
}

// ─── Step 4: Policy review ────────────────────────────────────────────────────

function StepReview({ session, onNext, onBack, token }) {
  const [review, setReview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!session?.session_id) return
    apiPost(`/api/v1/wizard/sessions/${session.session_id}/step/review`, {}, token)
      .then(d => setReview(d))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [session?.session_id])

  const policyDecision = review?.governance_decision
  const decisionStyle = STATUS_STYLE[policyDecision?.decision] || {}
  const DecisionIcon = decisionStyle.icon || Info

  const handleNext = async () => {
    if (policyDecision?.decision === 'BLOCKED') { setError('Deployment blocked by governance policy.'); return }
    setSubmitting(true); setError(null)
    try { await onNext({}) }
    catch (e) { setError(e.message) }
    finally { setSubmitting(false) }
  }

  return (
    <div>
      {loading && <div style={hintStyle}>Evaluating governance policies...</div>}
      {review && (
        <>
          {/* Governance decision */}
          <div style={{ padding: '12px 14px', background: decisionStyle.bg,
            border: `1px solid ${decisionStyle.color}33`, borderRadius: 8, marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <DecisionIcon size={15} color={decisionStyle.color} />
              <span style={{ fontSize: 13, fontWeight: 700, color: decisionStyle.color }}>
                {policyDecision?.decision}
              </span>
            </div>
            {policyDecision?.reasons?.map((r, i) => (
              <div key={i} style={{ fontSize: 11, color: '#94A3B8', lineHeight: 1.5, marginBottom: 3 }}>{r}</div>
            ))}
          </div>

          {/* Deployment summary */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
            {[
              ['Model', review.model_id],
              ['Engine', review.engine],
              ['Quantisation', review.quantisation],
              ['GPU', `${review.gpu_count}× ${review.gpu_model}`],
              ['Provider', review.provider],
              ['Region', review.region],
              ['Est. Hourly', `~$${((review.gpu_count||1)*2.49).toFixed(2)}/hr`],
              ['Licence', review.licence || 'Unknown'],
            ].map(([k, v]) => (
              <div key={k} style={{ padding: '8px 10px', background: 'rgba(255,255,255,0.02)',
                border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6 }}>
                <div style={{ fontSize: 10, color: '#475569', marginBottom: 2 }}>{k}</div>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#F1F5F9' }}>{v}</div>
              </div>
            ))}
          </div>

          <div style={{ padding: '10px 12px', background: 'rgba(124,107,240,0.05)',
            border: '1px solid rgba(124,107,240,0.15)', borderRadius: 7, fontSize: 11, color: '#94A3B8' }}>
            <Lock size={11} style={{ marginRight: 6 }} />
            By proceeding, you authorise OrQuanta to provision GPU infrastructure on your behalf.
            Charges begin when GPU allocation starts, not at approval. You can cancel before provisioning completes.
          </div>
        </>
      )}
      {error && <div style={errorStyle}>{error}</div>}
      <WizardNav
        onBack={onBack}
        onNext={handleNext}
        nextDisabled={loading || submitting || policyDecision?.decision === 'BLOCKED'}
        nextLabel={submitting ? 'Approving...' : policyDecision?.decision === 'REQUIRES_REVIEW' ? 'Proceed (Pending Review)' : 'Approve & Deploy'}
        nextVariant={policyDecision?.decision === 'REQUIRES_REVIEW' ? 'warning' : 'primary'}
      />
    </div>
  )
}

// ─── Step 5: Deploy + live status ─────────────────────────────────────────────

function StepDeploy({ session, token }) {
  const [deployment, setDeployment] = useState(null)
  const [error, setError] = useState(null)
  const [showKey, setShowKey] = useState(false)
  const [copied, setCopied] = useState(false)
  const navigate = useNavigate()

  const STATUS_LABELS = {
    mock: 'Demo Mode',
    provisioning: 'Provisioning GPU...',
    starting: 'Starting Container...',
    model_loading: 'Loading Model Weights...',
    health_check: 'Running Health Check...',
    ready: 'Ready',
    failed: 'Failed',
    stopped: 'Stopped',
  }

  useEffect(() => {
    if (!session?.deployment_id) return
    // Poll status every 5s
    const poll = () => {
      apiGet(`/api/v1/deployments/${session.deployment_id}`, token)
        .then(d => { setDeployment(d); if (!['ready','failed','stopped'].includes(d.status)) setTimeout(poll, 5000) })
        .catch(e => setError(e.message))
    }
    poll()
  }, [session?.deployment_id])

  const copy = (text) => {
    navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })
  }

  const isReady = deployment?.status === 'ready'
  const isMock  = !deployment?.is_real
  const statusLabel = STATUS_LABELS[deployment?.status] || deployment?.status || 'Initialising...'

  return (
    <div>
      {/* Status indicator */}
      <div style={{ textAlign: 'center', padding: '20px 0 16px' }}>
        {!deployment && <div style={hintStyle}>Initiating deployment...</div>}
        {deployment && (
          <>
            <div style={{ fontSize: 15, fontWeight: 700, color: isReady ? '#10B981' : '#F1F5F9', marginBottom: 6 }}>
              {statusLabel}
            </div>
            {!['ready','failed','stopped'].includes(deployment.status) && (
              <Loader size={20} style={{ animation: 'spin 1s linear infinite', color: '#7C6BF0' }} />
            )}
            {isReady && <CheckCircle size={24} color="#10B981" />}
            {deployment.status === 'failed' && <XCircle size={24} color="#EF4444" />}
          </>
        )}
      </div>

      {/* Mock banner */}
      {isMock && (
        <div style={{ padding: '10px 12px', background: 'rgba(245,158,11,0.08)',
          border: '1px solid rgba(245,158,11,0.2)', borderRadius: 7, fontSize: 11, color: '#F59E0B', marginBottom: 12 }}>
          <AlertTriangle size={11} style={{ marginRight: 5 }} />
          Demo mode — USE_REAL_PROVIDERS=false. No real GPU was provisioned. Set real provider keys to deploy on live infrastructure.
        </div>
      )}

      {/* Endpoint + API key */}
      {(isReady || isMock) && deployment && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {deployment.inference_endpoint && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#64748B', marginBottom: 5 }}>Inference Endpoint</div>
              <div style={{ display: 'flex', gap: 6 }}>
                <code style={codeStyle}>{deployment.inference_endpoint}/v1</code>
                <button onClick={() => copy(deployment.inference_endpoint + '/v1')} style={iconBtnStyle}>
                  {copied ? <Check size={12} color="#10B981" /> : <Copy size={12} />}
                </button>
              </div>
            </div>
          )}

          <div style={{ padding: '12px 14px', background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#F1F5F9', marginBottom: 8 }}>Quick Start</div>
            <pre style={{ fontSize: 11, color: '#94A3B8', margin: 0, lineHeight: 1.6, overflowX: 'auto' }}>{`from openai import OpenAI

client = OpenAI(
    base_url="${deployment.inference_endpoint || 'https://your-deployment'}/v1",
    api_key="sk-orq-your-key"
)

response = client.chat.completions.create(
    model="${deployment.model_id}",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)`}</pre>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => navigate('/jobs')}
              style={{ flex: 1, ...btnStyle('rgba(255,255,255,0.05)', '#94A3B8') }}>
              View Jobs
            </button>
            <button onClick={() => navigate('/models')}
              style={{ flex: 1, ...btnStyle('linear-gradient(135deg,#7C6BF0,#5B50D6)', '#fff') }}>
              Back to Models
            </button>
          </div>
        </div>
      )}

      {deployment?.failure_reason && (
        <div style={errorStyle}>
          Failure: {deployment.failure_reason}
          <div style={{ marginTop: 6, fontSize: 11 }}>GPU resources have been cleaned up. No charges should be incurred.</div>
        </div>
      )}

      {error && <div style={errorStyle}>{error}</div>}
    </div>
  )
}

// ─── Shared sub-components ────────────────────────────────────────────────────

function WizardNav({ onBack, onNext, nextDisabled, nextLabel = 'Next', nextVariant = 'primary' }) {
  const nextBg = nextVariant === 'warning'
    ? 'linear-gradient(135deg,#F59E0B,#D97706)'
    : 'linear-gradient(135deg,#7C6BF0,#5B50D6)'
  return (
    <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
      {onBack && (
        <button onClick={onBack}
          style={{ flex: 1, ...btnStyle('rgba(255,255,255,0.04)', '#94A3B8'), display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
          <ChevronLeft size={13} /> Back
        </button>
      )}
      {onNext && (
        <button onClick={onNext} disabled={nextDisabled}
          style={{ flex: 2, ...btnStyle(nextBg, '#fff'), opacity: nextDisabled ? 0.5 : 1,
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
          {nextLabel} {!nextDisabled && <ChevronRight size={13} />}
        </button>
      )}
    </div>
  )
}

function SelectField({ label, value, onChange, options }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: '#64748B', marginBottom: 5 }}>{label}</div>
      <select value={value} onChange={e => onChange(e.target.value)}
        style={{ width: '100%', background: '#1E293B', border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 7, color: '#F1F5F9', fontSize: 13, padding: '8px 10px' }}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  )
}

// ─── Shared styles ────────────────────────────────────────────────────────────

const inputStyle = {
  width: '100%', background: '#1E293B', border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 7, color: '#F1F5F9', fontSize: 13, padding: '8px 12px', boxSizing: 'border-box',
}
const rowStyle = {
  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
  border: '1px solid', borderRadius: 8, cursor: 'pointer', background: 'transparent',
  transition: 'all 0.15s',
}
const hintStyle = { fontSize: 12, color: '#64748B', textAlign: 'center', padding: '12px 0' }
const errorStyle = {
  marginTop: 10, padding: '10px 12px', background: 'rgba(239,68,68,0.08)',
  border: '1px solid rgba(239,68,68,0.2)', borderRadius: 7, fontSize: 12, color: '#EF4444',
}
const codeStyle = {
  flex: 1, background: '#0F172A', border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 6, padding: '7px 10px', fontSize: 12, color: '#94A3B8', overflowX: 'auto',
}
const iconBtnStyle = {
  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)',
  borderRadius: 6, padding: '7px 10px', cursor: 'pointer', color: '#94A3B8',
  display: 'flex', alignItems: 'center',
}
const btnStyle = (bg, color) => ({
  fontSize: 13, fontWeight: 600, color, background: bg,
  border: 'none', borderRadius: 8, padding: '10px 16px', cursor: 'pointer',
})
const tagStyle = (color) => ({
  fontSize: 10, fontWeight: 600, color, background: color + '15',
  border: `1px solid ${color}33`, borderRadius: 20, padding: '1px 7px',
})

// ─── Progress stepper ─────────────────────────────────────────────────────────

function StepProgress({ currentStep }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 28 }}>
      {STEPS.map((s, i) => {
        const done = s.id < currentStep
        const active = s.id === currentStep
        const Icon = s.icon
        return (
          <div key={s.id} style={{ display: 'flex', alignItems: 'center', flex: i < STEPS.length - 1 ? 1 : 0 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <div style={{
                width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: done ? '#10B981' : active ? '#7C6BF0' : 'rgba(255,255,255,0.05)',
                border: `2px solid ${done ? '#10B981' : active ? '#7C6BF0' : 'rgba(255,255,255,0.1)'}`,
                transition: 'all 0.3s',
              }}>
                {done ? <Check size={14} color="#fff" /> : <Icon size={13} color={active ? '#fff' : '#475569'} />}
              </div>
              <div style={{ fontSize: 10, fontWeight: active ? 700 : 400,
                color: active ? '#7C6BF0' : done ? '#10B981' : '#475569', whiteSpace: 'nowrap' }}>
                {s.label}
              </div>
            </div>
            {i < STEPS.length - 1 && (
              <div style={{ flex: 1, height: 2, background: done ? '#10B981' : 'rgba(255,255,255,0.08)',
                marginBottom: 14, marginLeft: 4, marginRight: 4, transition: 'background 0.3s' }} />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Main Wizard Page ─────────────────────────────────────────────────────────

export default function DeploymentWizardPage() {
  const { token } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [step, setStep] = useState(1)
  const [session, setSession] = useState(null)
  const [error, setError] = useState(null)
  const [initializing, setInitializing] = useState(true)

  // Create wizard session on mount
  useEffect(() => {
    const modelId = searchParams.get('model')
    apiPost('/api/v1/wizard/sessions', modelId ? { model_id: modelId } : {}, token)
      .then(s => {
        setSession(s)
        if (s.step > 1) setStep(s.step)
        if (modelId && s.model_id) setStep(2)
      })
      .catch(e => {
        // Backend wizard not yet live — use local session
        const id = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)
        setSession({ session_id: id, step: 1, model_id: modelId || '', status: 'in_progress' })
      })
      .finally(() => setInitializing(false))
  }, [token])

  const advanceStep = async (stepKey, payload) => {
    // Try to persist to wizard backend
    if (session?.session_id) {
      try {
        const updated = await apiPost(
          `/api/v1/wizard/sessions/${session.session_id}/step/${stepKey}`,
          payload, token
        )
        setSession(updated)
      } catch {
        // Merge locally if backend not yet live
        setSession(prev => ({ ...prev, ...payload }))
      }
    } else {
      setSession(prev => ({ ...prev, ...payload }))
    }
    setStep(s => s + 1)
  }

  const stepProps = { session, token, onBack: step > 1 ? () => setStep(s => s - 1) : null }

  const STEP_COMPONENTS = {
    1: <StepModel    {...stepProps} onNext={p => advanceStep('model', p)} />,
    2: <StepEngine   {...stepProps} onNext={p => advanceStep('engine', p)} />,
    3: <StepProvider {...stepProps} onNext={p => advanceStep('provider', p)} />,
    4: <StepReview   {...stepProps} onNext={p => advanceStep('deploy', p)} />,
    5: <StepDeploy   {...stepProps} />,
  }

  if (initializing) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300 }}>
      <Loader size={24} style={{ animation: 'spin 1s linear infinite', color: '#7C6BF0' }} />
    </div>
  )

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      style={{ maxWidth: 680, margin: '0 auto', padding: '24px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        <Zap size={20} color="#7C6BF0" />
        <h1 style={{ fontSize: 20, fontWeight: 800, color: '#F1F5F9', margin: 0 }}>Deployment Wizard</h1>
        <span style={{ fontSize: 11, color: '#64748B', marginLeft: 4 }}>Phase 3F</span>
      </div>

      <StepProgress currentStep={step} />

      <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 14, padding: '22px 24px' }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: '#F1F5F9', marginBottom: 16 }}>
          Step {step}: {STEPS[step - 1]?.label}
        </div>
        <AnimatePresence mode="wait">
          <motion.div key={step} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
            {STEP_COMPONENTS[step]}
          </motion.div>
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
