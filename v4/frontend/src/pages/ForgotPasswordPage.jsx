/* ─────────────────────────────────────────────────────────────────
   ForgotPasswordPage.jsx  –  request + confirm password reset
   Two modes driven by ?token= URL param
   ───────────────────────────────────────────────────────────────── */
import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Mail, Lock, ArrowLeft, CheckCircle, AlertTriangle, Loader2, Eye, EyeOff } from 'lucide-react'

const API = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || ''

export default function ForgotPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token')

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #0F172A 0%, #1E1A3C 50%, #0F172A 100%)',
      padding: '24px',
    }}>
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        style={{
          width: '100%', maxWidth: 440,
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 20, padding: 40,
          backdropFilter: 'blur(20px)',
        }}
      >
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            width: 56, height: 56, borderRadius: 16, margin: '0 auto 16px',
            background: 'linear-gradient(135deg, #7B2FFF, #0091FF)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 24,
          }}>⚡</div>
          <h1 style={{ color: '#F8FAFC', fontSize: '1.4rem', fontWeight: 700, margin: 0 }}>OrQuanta</h1>
          <p style={{ color: '#7B2FFF', fontSize: 12, fontWeight: 600, margin: '4px 0 0', letterSpacing: '0.08em' }}>
            GPU Cloud Intelligence
          </p>
        </div>

        {token ? <ResetForm token={token} /> : <RequestForm />}

        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <Link to="/login" style={{ color: '#7B2FFF', fontSize: 13, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <ArrowLeft size={13} /> Back to Sign In
          </Link>
        </div>
      </motion.div>
    </div>
  )
}

/* ── Request reset form (step 1) ─────────────────────────────── */
function RequestForm() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState('idle') // idle | loading | success | error
  const [msg, setMsg] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    if (!email.includes('@')) { setMsg('Enter a valid email.'); setStatus('error'); return }
    setStatus('loading'); setMsg('')

    try {
      const res = await fetch(`${API}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok) {
        setStatus('success')
        setMsg(data.message || 'Reset link sent — check your email.')
      } else {
        setStatus('error')
        setMsg(data.detail || 'Something went wrong. Try again.')
      }
    } catch {
      setStatus('error')
      setMsg('Network error. Please check your connection.')
    }
  }

  if (status === 'success') {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ textAlign: 'center' }}>
        <CheckCircle size={48} style={{ color: '#10B981', margin: '0 auto 16px', display: 'block' }} />
        <h2 style={{ color: '#F8FAFC', fontSize: '1.1rem', fontWeight: 700, marginBottom: 8 }}>Check your inbox</h2>
        <p style={{ color: '#94A3B8', fontSize: 14, lineHeight: 1.6, marginBottom: 24 }}>{msg}</p>
        <p style={{ color: '#64748B', fontSize: 12 }}>
          Didn't receive it? Check spam or{' '}
          <button onClick={() => setStatus('idle')} style={{ color: '#7B2FFF', background: 'none', border: 'none', cursor: 'pointer', fontSize: 12 }}>
            try again
          </button>
        </p>
      </motion.div>
    )
  }

  return (
    <>
      <h2 style={{ color: '#F8FAFC', fontSize: '1.15rem', fontWeight: 700, marginBottom: 8, textAlign: 'center' }}>
        Reset your password
      </h2>
      <p style={{ color: '#94A3B8', fontSize: 13, textAlign: 'center', marginBottom: 28, lineHeight: 1.6 }}>
        Enter your email and we'll send a reset link.
      </p>

      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ position: 'relative' }}>
          <Mail size={16} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: '#64748B' }} />
          <input
            type="email" value={email} onChange={e => setEmail(e.target.value)}
            placeholder="you@example.com" required
            style={inputStyle}
          />
        </div>

        {msg && status === 'error' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#FF6B6B', fontSize: 13 }}>
            <AlertTriangle size={14} /> {msg}
          </div>
        )}

        <button type="submit" disabled={status === 'loading'} style={btnStyle}>
          {status === 'loading'
            ? <><Loader2 size={16} style={{ animation: 'spin 0.8s linear infinite' }} /> Sending…</>
            : 'Send Reset Link'}
        </button>
      </form>
    </>
  )
}

/* ── Reset password form (step 2 — arrived via email link) ─── */
function ResetForm({ token }) {
  const [pw, setPw] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [status, setStatus] = useState('idle')
  const [msg, setMsg] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    if (pw.length < 8) { setMsg('Password must be at least 8 characters.'); setStatus('error'); return }
    if (pw !== confirm) { setMsg('Passwords do not match.'); setStatus('error'); return }
    setStatus('loading'); setMsg('')

    try {
      const res = await fetch(`${API}/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: pw }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok) {
        setStatus('success')
        setMsg(data.message || 'Password updated successfully!')
      } else {
        setStatus('error')
        setMsg(data.detail || 'Reset link may have expired. Request a new one.')
      }
    } catch {
      setStatus('error')
      setMsg('Network error. Please try again.')
    }
  }

  if (status === 'success') {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ textAlign: 'center' }}>
        <CheckCircle size={48} style={{ color: '#10B981', margin: '0 auto 16px', display: 'block' }} />
        <h2 style={{ color: '#F8FAFC', fontSize: '1.1rem', fontWeight: 700, marginBottom: 8 }}>Password updated!</h2>
        <p style={{ color: '#94A3B8', fontSize: 14, marginBottom: 24 }}>{msg}</p>
        <Link to="/login" style={{ ...btnStyle, display: 'inline-flex', textDecoration: 'none', justifyContent: 'center' }}>
          Sign In Now
        </Link>
      </motion.div>
    )
  }

  return (
    <>
      <h2 style={{ color: '#F8FAFC', fontSize: '1.15rem', fontWeight: 700, marginBottom: 8, textAlign: 'center' }}>
        Set new password
      </h2>
      <p style={{ color: '#94A3B8', fontSize: 13, textAlign: 'center', marginBottom: 28, lineHeight: 1.6 }}>
        Choose a strong password of at least 8 characters.
      </p>

      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ position: 'relative' }}>
          <Lock size={16} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: '#64748B' }} />
          <input
            type={showPw ? 'text' : 'password'} value={pw}
            onChange={e => setPw(e.target.value)}
            placeholder="New password (min 8 chars)" required minLength={8}
            style={{ ...inputStyle, paddingRight: 44 }}
          />
          <button type="button" onClick={() => setShowPw(v => !v)} style={{
            position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)',
            background: 'none', border: 'none', cursor: 'pointer', color: '#64748B', padding: 0,
          }}>
            {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>

        <div style={{ position: 'relative' }}>
          <Lock size={16} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: '#64748B' }} />
          <input
            type={showPw ? 'text' : 'password'} value={confirm}
            onChange={e => setConfirm(e.target.value)}
            placeholder="Confirm new password" required
            style={inputStyle}
          />
        </div>

        {/* Password strength indicator */}
        {pw.length > 0 && <PasswordStrength password={pw} />}

        {msg && status === 'error' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#FF6B6B', fontSize: 13 }}>
            <AlertTriangle size={14} /> {msg}
          </div>
        )}

        <button type="submit" disabled={status === 'loading'} style={btnStyle}>
          {status === 'loading'
            ? <><Loader2 size={16} style={{ animation: 'spin 0.8s linear infinite' }} /> Updating…</>
            : 'Update Password'}
        </button>
      </form>
    </>
  )
}

function PasswordStrength({ password }) {
  const checks = [
    { label: '8+ chars', pass: password.length >= 8 },
    { label: 'Uppercase', pass: /[A-Z]/.test(password) },
    { label: 'Number', pass: /\d/.test(password) },
    { label: 'Symbol', pass: /[^A-Za-z0-9]/.test(password) },
  ]
  const score = checks.filter(c => c.pass).length
  const color = score <= 1 ? '#FF6B6B' : score === 2 ? '#F59E0B' : score === 3 ? '#0091FF' : '#10B981'

  return (
    <div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
        {[1, 2, 3, 4].map(i => (
          <div key={i} style={{
            flex: 1, height: 3, borderRadius: 2,
            background: i <= score ? color : 'rgba(255,255,255,0.08)',
            transition: 'background 0.2s',
          }} />
        ))}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {checks.map(c => (
          <span key={c.label} style={{ fontSize: 11, color: c.pass ? '#10B981' : '#64748B' }}>
            {c.pass ? '✓' : '○'} {c.label}
          </span>
        ))}
      </div>
    </div>
  )
}

/* ── Shared styles ─────────────────────────────────────────── */
const inputStyle = {
  width: '100%', boxSizing: 'border-box',
  paddingLeft: 42, paddingRight: 14, paddingTop: 12, paddingBottom: 12,
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 10, color: '#F8FAFC', fontSize: 14,
  outline: 'none',
  transition: 'border-color 0.2s',
}

const btnStyle = {
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  padding: '12px 24px', borderRadius: 10, border: 'none', cursor: 'pointer',
  background: 'linear-gradient(135deg, #7B2FFF, #0091FF)',
  color: '#fff', fontWeight: 700, fontSize: 14, letterSpacing: '0.02em',
  transition: 'opacity 0.2s',
}
