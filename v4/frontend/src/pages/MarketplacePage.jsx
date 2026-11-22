import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../App.jsx'
import {
  Search, Package, Cpu, Wrench, GitBranch, Shield, User, Download,
  CheckCircle, XCircle, Clock, AlertTriangle, ChevronRight, Filter,
  Star, Lock, Globe, ArrowRight, BarChart2, ExternalLink, RefreshCw
} from 'lucide-react'

const API = import.meta.env.VITE_API_BASE_URL || ''

const TABS = [
  { id: 'home',      label: 'Discover',    icon: Globe },
  { id: 'models',    label: 'Models',      icon: Cpu },
  { id: 'agents',    label: 'Agents',      icon: Package },
  { id: 'tools',     label: 'MCP Tools',   icon: Wrench },
  { id: 'workflows', label: 'Workflows',   icon: GitBranch },
  { id: 'installed', label: 'Installed',   icon: Download },
  { id: 'publish',   label: 'Publish',     icon: User },
]

const TRUST_BADGE = {
  SECURITY_REVIEWED: { label: 'Security Reviewed', color: '#10B981', icon: CheckCircle },
  METADATA_VERIFIED: { label: 'Verified',           color: '#3B82F6', icon: Shield },
  PENDING_REVIEW:    { label: 'Pending Review',      color: '#F59E0B', icon: Clock },
  RESTRICTED:        { label: 'Restricted',          color: '#F97316', icon: AlertTriangle },
  REJECTED:          { label: 'Rejected',            color: '#EF4444', icon: XCircle },
  REVOKED:           { label: 'Revoked',             color: '#6B7280', icon: XCircle },
}

function TrustBadge({ status }) {
  const cfg = TRUST_BADGE[status] || TRUST_BADGE['PENDING_REVIEW']
  const Icon = cfg.icon
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: cfg.color + '18', border: `1px solid ${cfg.color}40`,
      color: cfg.color, borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 600,
    }}>
      <Icon size={10} /> {cfg.label}
    </span>
  )
}

function LicenceBadge({ licence }) {
  const risk = {
    'apache-2.0': '#10B981', 'mit': '#10B981', 'openrail': '#10B981',
    'llama2': '#F59E0B', 'llama3': '#F59E0B', 'gemma': '#F59E0B',
    'cc-by-nc-4.0': '#EF4444', 'other': '#6B7280', 'unknown': '#6B7280',
  }
  const c = risk[licence?.toLowerCase()] || '#6B7280'
  return (
    <span style={{
      display: 'inline-block', background: c + '18', border: `1px solid ${c}40`,
      color: c, borderRadius: 12, padding: '1px 8px', fontSize: 10, fontWeight: 600,
    }}>{licence || 'UNKNOWN'}</span>
  )
}

function DemoBadge() {
  return (
    <span style={{
      background: '#7C3AED18', border: '1px solid #7C3AED40',
      color: '#7C3AED', borderRadius: 12, padding: '1px 8px', fontSize: 10, fontWeight: 600,
    }}>DEMO</span>
  )
}

function AssetCard({ asset, onInstall, onDetail }) {
  const a = asset.asset || asset
  const trust = a.security?.trust_status || 'PENDING_REVIEW'
  return (
    <div style={{
      background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: 20,
      cursor: 'pointer', transition: 'all .15s',
    }}
      onClick={() => onDetail && onDetail(a)}
      onMouseEnter={e => { e.currentTarget.style.borderColor = '#7C6BF0'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(124,107,240,.12)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = '#E2E8F0'; e.currentTarget.style.boxShadow = 'none' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, color: '#0F172A' }}>{a.name}</div>
          <div style={{ color: '#64748B', fontSize: 12, marginTop: 2 }}>v{a.version}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          {a.is_demo && <DemoBadge />}
          {a.is_featured && <span style={{ color: '#F59E0B', fontSize: 10 }}><Star size={10} /> Featured</span>}
        </div>
      </div>
      <div style={{ color: '#475569', fontSize: 13, lineHeight: 1.5, marginBottom: 12, minHeight: 40 }}>
        {a.description?.slice(0, 120)}{a.description?.length > 120 ? '...' : ''}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        <TrustBadge status={trust} />
        <LicenceBadge licence={a.licence} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ color: '#94A3B8', fontSize: 11 }}>
          {a.install_count || 0} installs
        </div>
        <button
          onClick={e => { e.stopPropagation(); onInstall && onInstall(a) }}
          style={{
            background: 'linear-gradient(135deg,#7C6BF0,#9B8BF4)', border: 'none',
            borderRadius: 8, color: '#fff', padding: '6px 14px', fontSize: 12,
            fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          <Download size={12} /> Install
        </button>
      </div>
    </div>
  )
}

function AssetGrid({ items, onInstall, onDetail, loading, emptyMsg = 'No assets found.' }) {
  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
      <RefreshCw size={24} className="spin" style={{ color: '#7C6BF0', animation: 'spin 1s linear infinite' }} />
    </div>
  )
  if (!items?.length) return (
    <div style={{ textAlign: 'center', color: '#94A3B8', padding: 60 }}>{emptyMsg}</div>
  )
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 16 }}>
      {items.map((item, i) => (
        <AssetCard key={i} asset={item} onInstall={onInstall} onDetail={onDetail} />
      ))}
    </div>
  )
}

function InstallWizard({ asset, onClose, token }) {
  const [step, setStep] = useState('prepare')
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const prepare = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const r = await fetch(`${API}/api/v1/marketplace/install/prepare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ asset_id: asset.asset_id, tenant_id: 'default' }),
        signal: AbortSignal.timeout(15000),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Prepare failed')
      setSession(data)
      setStep('review')
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }, [asset, token])

  const confirm = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const r = await fetch(`${API}/api/v1/marketplace/install/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          session_id: session.session_id,
          accepted_permissions: session.plan?.required_permissions || [],
        }),
        signal: AbortSignal.timeout(15000),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Confirm failed')
      setSession(data)
      setStep('complete')
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }, [session, token])

  useEffect(() => { prepare() }, [prepare])

  const plan = session?.plan

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: '#fff', borderRadius: 16, padding: 32, maxWidth: 540, width: '90%',
        maxHeight: '85vh', overflow: 'auto',
      }}>
        <div style={{ fontWeight: 700, fontSize: 18, color: '#0F172A', marginBottom: 4 }}>
          Install: {asset.name}
        </div>
        <div style={{ color: '#64748B', fontSize: 13, marginBottom: 20 }}>v{asset.version}</div>

        {loading && <div style={{ color: '#7C6BF0', textAlign: 'center', padding: 20 }}>Preparing installation...</div>}
        {error && (
          <div style={{ background: '#FEF2F2', border: '1px solid #FCA5A5', borderRadius: 8, padding: 12, color: '#DC2626', fontSize: 13, marginBottom: 16 }}>
            {error}
          </div>
        )}

        {step === 'review' && plan && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#374151', marginBottom: 8 }}>Installation Plan</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                {[
                  ['Licence', plan.licence],
                  ['Licence Risk', plan.licence_risk],
                  ['Trust Status', plan.trust_status],
                  ['Integrity Verified', plan.integrity_verified ? 'Yes' : 'No (no manifest)'],
                ].map(([k, v]) => (
                  <div key={k} style={{ background: '#F8FAFC', borderRadius: 8, padding: '8px 12px' }}>
                    <div style={{ color: '#94A3B8', fontSize: 10, marginBottom: 2 }}>{k}</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>{v}</div>
                  </div>
                ))}
              </div>
            </div>

            {plan.required_permissions?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: '#374151', marginBottom: 6 }}>
                  Permissions Required
                </div>
                {plan.required_permissions.map(p => (
                  <div key={p} style={{
                    background: '#FFF7ED', border: '1px solid #FED7AA',
                    borderRadius: 6, padding: '4px 10px', fontSize: 12, color: '#C2410C', marginBottom: 4,
                  }}>{p}</div>
                ))}
                <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 4 }}>
                  These permissions will be granted under YOUR identity — not the publisher's.
                </div>
              </div>
            )}

            {plan.warnings?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                {plan.warnings.map((w, i) => (
                  <div key={i} style={{
                    background: '#FFFBEB', border: '1px solid #FDE68A',
                    borderRadius: 6, padding: '6px 10px', fontSize: 12, color: '#92400E', marginBottom: 4,
                    display: 'flex', gap: 6, alignItems: 'flex-start',
                  }}>
                    <AlertTriangle size={12} style={{ marginTop: 1, flexShrink: 0 }} /> {w}
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
              <button onClick={onClose} style={{
                flex: 1, background: '#F1F5F9', border: 'none', borderRadius: 8,
                padding: '10px', cursor: 'pointer', color: '#475569', fontWeight: 600,
              }}>Cancel</button>
              <button
                onClick={confirm}
                disabled={!plan.can_proceed}
                style={{
                  flex: 2, background: plan.can_proceed
                    ? 'linear-gradient(135deg,#7C6BF0,#9B8BF4)'
                    : '#E2E8F0',
                  border: 'none', borderRadius: 8, padding: '10px', cursor: plan.can_proceed ? 'pointer' : 'not-allowed',
                  color: plan.can_proceed ? '#fff' : '#94A3B8', fontWeight: 600,
                }}
              >
                {plan.can_proceed ? 'Approve and Install' : `Blocked: ${plan.policy_decision}`}
              </button>
            </div>
          </div>
        )}

        {step === 'complete' && (
          <div style={{ textAlign: 'center', padding: 20 }}>
            <CheckCircle size={48} color="#10B981" style={{ marginBottom: 12 }} />
            <div style={{ fontWeight: 700, fontSize: 18, color: '#0F172A', marginBottom: 8 }}>
              Installation Complete
            </div>
            <div style={{ color: '#64748B', fontSize: 13 }}>
              {asset.name} has been installed. Monitor it from the Installed tab.
            </div>
            <button
              onClick={onClose}
              style={{
                marginTop: 20, background: 'linear-gradient(135deg,#7C6BF0,#9B8BF4)',
                border: 'none', borderRadius: 8, color: '#fff', padding: '10px 24px',
                fontWeight: 600, cursor: 'pointer',
              }}
            >Done</button>
          </div>
        )}
      </div>
    </div>
  )
}

function SearchBar({ value, onChange, placeholder }) {
  return (
    <div style={{ position: 'relative', maxWidth: 480 }}>
      <Search size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94A3B8' }} />
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder || 'Search...'}
        style={{
          width: '100%', padding: '10px 12px 10px 36px',
          border: '1px solid #E2E8F0', borderRadius: 10, fontSize: 14,
          color: '#0F172A', background: '#fff', outline: 'none',
        }}
      />
    </div>
  )
}

export default function MarketplacePage() {
  const { token } = useAuth()
  const [tab, setTab] = useState('home')
  const [query, setQuery] = useState('')
  const [overview, setOverview] = useState(null)
  const [assets, setAssets] = useState([])
  const [loading, setLoading] = useState(false)
  const [installations, setInstallations] = useState([])
  const [installing, setInstalling] = useState(null)   // asset being installed
  const [detail, setDetail] = useState(null)           // asset detail overlay

  const authHdr = { Authorization: `Bearer ${token}` }

  const fetchOverview = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch(`${API}/api/v1/marketplace/overview`, { headers: authHdr, signal: AbortSignal.timeout(10000) })
      if (r.ok) setOverview(await r.json())
    } catch {}
  }, [token])

  const fetchAssets = useCallback(async (assetType, q = '') => {
    if (!token) return
    setLoading(true)
    try {
      const endpoint = {
        models: '/api/v1/marketplace/models',
        agents: '/api/v1/marketplace/agents',
        tools: '/api/v1/marketplace/tools',
        workflows: '/api/v1/marketplace/workflows',
      }[assetType] || '/api/v1/marketplace/assets'
      const r = await fetch(`${API}${endpoint}?q=${encodeURIComponent(q)}&limit=48`, {
        headers: authHdr, signal: AbortSignal.timeout(10000),
      })
      if (r.ok) {
        const data = await r.json()
        setAssets(data.models || data.agents || data.tools || data.workflows || data.assets || [])
      }
    } catch {} finally { setLoading(false) }
  }, [token])

  const fetchInstallations = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch(`${API}/api/v1/marketplace/installations`, { headers: authHdr, signal: AbortSignal.timeout(10000) })
      if (r.ok) {
        const data = await r.json()
        setInstallations(data.installations || [])
      }
    } catch {}
  }, [token])

  useEffect(() => { fetchOverview() }, [fetchOverview])

  useEffect(() => {
    if (tab === 'home') { setAssets([]); return }
    if (tab === 'installed') { fetchInstallations(); return }
    fetchAssets(tab, query)
  }, [tab, fetchAssets, fetchInstallations, query])

  const handleInstall = (asset) => setInstalling(asset)

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: '#0F172A', margin: 0 }}>
          AI Marketplace
        </h1>
        <p style={{ color: '#64748B', fontSize: 14, marginTop: 4 }}>
          Discover, install and publish AI models, agents, MCP tools and workflows.
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid #E2E8F0', marginBottom: 24, flexWrap: 'wrap' }}>
        {TABS.map(t => {
          const Icon = t.icon
          return (
            <button
              key={t.id}
              onClick={() => { setTab(t.id); setQuery('') }}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 16px', border: 'none', borderRadius: '8px 8px 0 0',
                background: tab === t.id ? '#7C6BF0' : 'transparent',
                color: tab === t.id ? '#fff' : '#64748B',
                cursor: 'pointer', fontWeight: tab === t.id ? 700 : 500, fontSize: 13,
                borderBottom: tab === t.id ? '2px solid #7C6BF0' : '2px solid transparent',
              }}
            >
              <Icon size={14} /> {t.label}
            </button>
          )
        })}
      </div>

      {/* Home / Discover */}
      {tab === 'home' && (
        <div>
          {overview && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 32 }}>
              {[
                { label: 'Models', count: overview.models, icon: Cpu, tab: 'models' },
                { label: 'Agents', count: overview.agents, icon: Package, tab: 'agents' },
                { label: 'MCP Tools', count: overview.tools, icon: Wrench, tab: 'tools' },
                { label: 'Workflows', count: overview.workflows, icon: GitBranch, tab: 'workflows' },
              ].map(c => {
                const Icon = c.icon
                return (
                  <div
                    key={c.label}
                    onClick={() => setTab(c.tab)}
                    style={{
                      background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12,
                      padding: 20, cursor: 'pointer', textAlign: 'center',
                    }}
                  >
                    <Icon size={28} color="#7C6BF0" style={{ marginBottom: 8 }} />
                    <div style={{ fontSize: 24, fontWeight: 700, color: '#0F172A' }}>{c.count}</div>
                    <div style={{ color: '#64748B', fontSize: 13 }}>{c.label}</div>
                  </div>
                )
              })}
            </div>
          )}

          <div style={{ marginBottom: 16, fontWeight: 600, fontSize: 16, color: '#0F172A' }}>
            Featured Assets
          </div>
          {overview?.demo_data_note && (
            <div style={{
              background: '#FFFBEB', border: '1px solid #FDE68A',
              borderRadius: 8, padding: '8px 14px', fontSize: 12, color: '#92400E', marginBottom: 16,
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <AlertTriangle size={13} /> {overview.demo_data_note}
            </div>
          )}
          <AssetGrid
            items={overview?.featured || []}
            onInstall={handleInstall}
            onDetail={setDetail}
            loading={!overview}
            emptyMsg="No featured assets."
          />
        </div>
      )}

      {/* Asset Tabs */}
      {['models', 'agents', 'tools', 'workflows'].includes(tab) && (
        <div>
          <div style={{ marginBottom: 20 }}>
            <SearchBar
              value={query}
              onChange={q => { setQuery(q); fetchAssets(tab, q) }}
              placeholder={`Search ${tab}...`}
            />
          </div>
          <AssetGrid items={assets} onInstall={handleInstall} onDetail={setDetail} loading={loading} />
        </div>
      )}

      {/* Installed */}
      {tab === 'installed' && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 15, color: '#0F172A', marginBottom: 16 }}>
            Installed Assets
          </div>
          {installations.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#94A3B8', padding: 60 }}>
              No assets installed yet. Browse the marketplace to get started.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {installations.map(r => (
                <div key={r.installation_id} style={{
                  background: '#fff', border: '1px solid #E2E8F0', borderRadius: 10,
                  padding: '14px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                  <div>
                    <div style={{ fontWeight: 600, color: '#0F172A' }}>{r.asset_id}</div>
                    <div style={{ color: '#64748B', fontSize: 12 }}>v{r.asset_version} · Installed by {r.installed_by}</div>
                  </div>
                  <span style={{
                    padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                    background: r.status === 'ACTIVE' ? '#D1FAE5' : '#F3F4F6',
                    color: r.status === 'ACTIVE' ? '#065F46' : '#6B7280',
                  }}>{r.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Publish */}
      {tab === 'publish' && (
        <div style={{ maxWidth: 600 }}>
          <div style={{ fontWeight: 700, fontSize: 18, color: '#0F172A', marginBottom: 8 }}>
            Publisher Portal
          </div>
          <div style={{ color: '#64748B', fontSize: 14, marginBottom: 24, lineHeight: 1.6 }}>
            Publish AI models, agents, MCP tools and workflows to the OrQuanta Marketplace.
            All assets go through a trust and security review before publication.
          </div>
          {[
            { label: 'Register as Publisher', href: '/docs/marketplace/publish', icon: User },
            { label: 'Submit a Model', href: '/docs/marketplace/models', icon: Cpu },
            { label: 'Submit an Agent', href: '/docs/marketplace/agents', icon: Package },
            { label: 'Register an MCP Tool', href: '/docs/marketplace/tools', icon: Wrench },
            { label: 'Submit a Workflow', href: '/docs/marketplace/workflows', icon: GitBranch },
          ].map(item => {
            const Icon = item.icon
            return (
              <div key={item.label} style={{
                background: '#fff', border: '1px solid #E2E8F0', borderRadius: 10,
                padding: '16px 20px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <Icon size={18} color="#7C6BF0" />
                  <span style={{ fontWeight: 600, color: '#0F172A' }}>{item.label}</span>
                </div>
                <ChevronRight size={16} color="#94A3B8" />
              </div>
            )
          })}
          <div style={{
            background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 8,
            padding: '12px 16px', fontSize: 12, color: '#92400E', marginTop: 16,
          }}>
            Monetisation accounting is available but real payouts require additional
            verification, fraud prevention, tax and legal review.
          </div>
        </div>
      )}

      {/* Install wizard overlay */}
      {installing && (
        <InstallWizard
          asset={installing}
          token={token}
          onClose={() => { setInstalling(null); if (tab === 'installed') fetchInstallations() }}
        />
      )}
    </div>
  )
}
