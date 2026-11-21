import { SkeletonStatGrid, SkeletonCard } from '../components/Skeleton.jsx'
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';

const PLANS = [
  {
    id: 'starter',
    name: 'Starter',
    price: 99,
    description: 'Perfect for indie researchers and small teams',
    features: [
      'Up to $5K/mo GPU spend automated',
      '2 concurrent AI agents',
      'RunPod + Lambda Labs providers',
      'Email alerts',
      'Basic cost analytics',
      '14-day free trial',
    ],
    color: '#6366f1',
    popular: false,
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 499,
    description: 'For ML teams running production workloads',
    features: [
      'Up to $30K/mo GPU spend automated',
      '10 concurrent AI agents',
      'All 5 cloud providers',
      'Slack + PagerDuty alerts',
      'Advanced cost analytics',
      'Priority support (24hr SLA)',
      '14-day free trial',
    ],
    color: '#8b5cf6',
    popular: true,
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: null,
    description: 'Custom solutions for large organizations',
    features: [
      'Unlimited GPU spend management',
      'Unlimited agents',
      'All providers + CoreWeave',
      'SAML SSO',
      '99.9% uptime SLA',
      'Dedicated Slack channel',
      'Custom integrations',
    ],
    color: '#a855f7',
    popular: false,
  },
];

export default function BillingPage() {
  const [currentPlan, setCurrentPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState('');
  const [message, setMessage] = useState('');
  const [billingHistory, setBillingHistory] = useState([]);
  const [stripeReady, setStripeReady] = useState(false);

  const getToken = () => localStorage.getItem('orquanta_token') || '';

  useEffect(() => {
    // Check URL params for success/cancel
    const params = new URLSearchParams(window.location.search);
    if (params.get('success') === 'true') {
      setMessage('✅ Subscription activated! Welcome to OrQuanta.');
    } else if (params.get('cancelled') === 'true') {
      setMessage('ℹ️ Checkout cancelled. Your free trial is still active.');
    }

    fetchSubscription();
    // Check if Stripe is configured on the backend
    fetch('/api/v1/billing/plans', { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.stripe_enabled) setStripeReady(true) })
      .catch(() => {});

    // Fetch real billing/usage history from API
    fetch('/api/v1/jobs?status=completed&limit=10', {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(r => r.ok ? r.json() : { jobs: [] })
      .then(data => {
        const rows = (data.jobs || []).map(j => ({
          date: j.completed_at ? new Date(j.completed_at).toLocaleDateString() : '—',
          description: `Job ${(j.job_id || '').slice(0, 10)}… ${j.intent ? '— ' + j.intent.slice(0, 40) : ''}`,
          amount: j.cost_usd ?? 0,
          provider: j.provider || 'GPU Cloud',
        }));
        setBillingHistory(rows);
      })
      .catch(() => setBillingHistory([]));
  }, []);

  async function fetchSubscription() {
    setLoading(true);
    try {
      const r = await fetch('/api/v1/billing/subscription', {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (r.ok) {
        const data = await r.json();
        setCurrentPlan(data);
      }
    } catch (err) {
      console.error('Failed to fetch subscription:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubscribe(planId) {
    if (planId === 'enterprise') {
      window.location.href = 'mailto:sales@orquanta.com?subject=Enterprise%20Inquiry';
      return;
    }

    setCheckoutLoading(planId);
    try {
      const r = await fetch('/api/v1/billing/checkout', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${getToken()}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          plan: planId,
          success_url: window.location.origin + '/app/billing?success=true',
          cancel_url: window.location.origin + '/app/billing?cancelled=true',
        }),
      });
      const data = await r.json();
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      } else if (data.demo_mode || data.message) {
        // Demo mode "" Stripe not configured yet, simulate trial activation
        setMessage(` 14-day free trial activated for the ${planId.charAt(0).toUpperCase() + planId.slice(1)} plan! You'll be charged after the trial ends. Add STRIPE_SECRET_KEY to enable real billing.`);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } else if (r.status === 404 || r.status === 422) {
        setMessage(` Trial started! Connect Stripe in settings to enable billing. Plan: ${planId}`);
      } else {
        setMessage('Checkout unavailable. Please try again or contact support@orquanta.com');
      }
    } catch (err) {
      setMessage('Checkout failed. Please try again.');
    } finally {
      setCheckoutLoading('');
    }
  }

  async function handleManageSubscription() {
    try {
      const r = await fetch('/api/v1/billing/portal', {
        method: 'POST',
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      const data = await r.json();
      if (data.portal_url) {
        window.location.href = data.portal_url;
      }
    } catch (err) {
      setMessage('Could not open billing portal.');
    }
  }

  const planStatus = currentPlan?.plan || 'free';
  const isActivePlan = (planId) => planStatus === planId;

  if (loading) return (
    <div style={{ padding: '2rem', maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <div style={{ height: 40, width: '50%', margin: '0 auto 16px', borderRadius: 8,
          background: 'linear-gradient(90deg,rgba(99,102,241,0.08) 25%,rgba(99,102,241,0.15) 50%,rgba(99,102,241,0.08) 75%)',
          backgroundSize: '400% 100%', animation: 'shimmer 1.6s linear infinite' }} />
        <div style={{ height: 16, width: '40%', margin: '0 auto', borderRadius: 6,
          background: 'linear-gradient(90deg,rgba(0,0,0,0.04) 25%,rgba(0,0,0,0.08) 50%,rgba(0,0,0,0.04) 75%)',
          backgroundSize: '400% 100%', animation: 'shimmer 1.6s linear infinite' }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 24 }}>
        <SkeletonCard rows={6} />
        <SkeletonCard rows={6} />
        <SkeletonCard rows={6} />
      </div>
    </div>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
      style={{ padding: '2rem', maxWidth: '1100px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <h1 style={{
          fontSize: '2.5rem',
          fontWeight: 800,
          background: 'linear-gradient(135deg, #6366f1, #a855f7)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          marginBottom: '0.75rem',
        }}>
          GPU Cloud at AI Prices
        </h1>
        <p style={{ color: '#94a3b8', fontSize: '1.1rem', maxWidth: '520px', margin: '0 auto' }}>
          Our AI agents find you the cheapest GPU in under 60 seconds, then run your job autonomously.
          Pay only for what you use.
        </p>
      </div>

      {/* Stripe not configured banner */}
      {!stripeReady && (
        <div style={{
          background: 'rgba(245, 158, 11, 0.1)',
          border: '1px solid rgba(245, 158, 11, 0.35)',
          borderRadius: '12px',
          padding: '1rem 1.5rem',
          marginBottom: '2rem',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
          fontSize: '0.9rem',
        }}>
          <span style={{ fontSize: '1.2rem', flexShrink: 0 }}> </span>
          <div>
            <span style={{ color: '#fbbf24', fontWeight: 700 }}>Payment gateway not yet connected. </span>
            <span style={{ color: '#94a3b8' }}>
              Plans are visible and trials can be started. To enable real billing, add{' '}
              <code style={{ background: 'rgba(255,255,255,0.06)', padding: '1px 6px', borderRadius: 4, fontSize: '0.85rem', color: '#e2e8f0' }}>STRIPE_SECRET_KEY</code>{' '}
              to your environment variables.
            </span>
          </div>
        </div>
      )}

      {/* Alert banner */}
      {message && (
        <div style={{
          background: 'rgba(99, 102, 241, 0.15)',
          border: '1px solid rgba(99, 102, 241, 0.4)',
          borderRadius: '12px',
          padding: '1rem 1.5rem',
          marginBottom: '2rem',
          color: '#a5b4fc',
          fontSize: '0.95rem',
        }}>
          {message}
        </div>
      )}

      {/* Current Plan status */}
      {!loading && currentPlan && planStatus !== 'free' && (
        <div style={{
          background: 'rgba(16, 185, 129, 0.1)',
          border: '1px solid rgba(16, 185, 129, 0.3)',
          borderRadius: '12px',
          padding: '1.25rem 1.5rem',
          marginBottom: '2rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <div>
            <span style={{ color: '#10b981', fontWeight: 700, textTransform: 'capitalize' }}>
              {planStatus} Plan
            </span>
            <span style={{ color: '#94a3b8', marginLeft: '1rem', fontSize: '0.875rem' }}>
              Status: {currentPlan.status}
              {currentPlan.trial_end && ` - Trial ends: ${new Date(currentPlan.trial_end).toLocaleDateString()}`}
            </span>
          </div>
          <button
            onClick={handleManageSubscription}
            style={{
              background: 'rgba(16, 185, 129, 0.2)',
              border: '1px solid rgba(16, 185, 129, 0.5)',
              borderRadius: '8px',
              color: '#10b981',
              padding: '0.5rem 1.25rem',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.875rem',
            }}
          >
            Manage Subscription
          </button>
        </div>
      )}

      {/* Pricing Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem', marginBottom: '3rem' }}>
        {PLANS.map((plan) => (
          <div
            key={plan.id}
            style={{
              background: plan.popular
                ? 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(139,92,246,0.15))'
                : 'rgba(15, 23, 42, 0.8)',
              border: plan.popular
                ? '2px solid rgba(139, 92, 246, 0.6)'
                : '1px solid rgba(255,255,255,0.06)',
              borderRadius: '16px',
              padding: '2rem',
              position: 'relative',
              transition: 'transform 0.2s',
            }}
          >
            {plan.popular && (
              <div style={{
                position: 'absolute',
                top: '-12px',
                left: '50%',
                transform: 'translateX(-50%)',
                background: 'linear-gradient(90deg, #6366f1, #a855f7)',
                borderRadius: '20px',
                padding: '4px 16px',
                fontSize: '0.75rem',
                fontWeight: 700,
                color: 'var(--text-primary)',
                whiteSpace: 'nowrap',
              }}>
                Most Popular
              </div>
            )}

            {isActivePlan(plan.id) && (
              <div style={{
                position: 'absolute',
                top: '-12px',
                right: '1.5rem',
                background: 'rgba(16, 185, 129, 0.9)',
                borderRadius: '20px',
                padding: '4px 12px',
                fontSize: '0.7rem',
                fontWeight: 700,
                color: 'var(--text-primary)',
              }}>
                " Current Plan
              </div>
            )}

            <h3 style={{ color: '#f1f5f9', fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.5rem' }}>
              {plan.name}
            </h3>
            <p style={{ color: '#64748b', fontSize: '0.875rem', marginBottom: '1.25rem' }}>
              {plan.description}
            </p>

            <div style={{ marginBottom: '1.5rem' }}>
              {plan.price !== null ? (
                <>
                  <span style={{ fontSize: '2.75rem', fontWeight: 800, color: '#f1f5f9' }}>
                    ${plan.price}
                  </span>
                  <span style={{ color: '#64748b', fontSize: '0.9rem' }}>/month</span>
                  <div style={{ color: '#6366f1', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                    14-day free trial - No credit card required
                  </div>
                </>
              ) : (
                <span style={{ fontSize: '1.75rem', fontWeight: 800, color: '#f1f5f9' }}>
                  Custom Pricing
                </span>
              )}
            </div>

            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 1.75rem 0' }}>
              {plan.features.map((f) => (
                <li key={f} style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '0.625rem',
                  marginBottom: '0.625rem',
                  color: '#cbd5e1',
                  fontSize: '0.875rem',
                }}>
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ flexShrink: 0, marginTop: 2 }}>
                    <circle cx="7" cy="7" r="6" stroke="#10b981" strokeWidth="1.5"/>
                    <path d="M4.5 7l1.75 1.75L9.5 5.5" stroke="#10b981" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  {f}
                </li>
              ))}
            </ul>

            <button
              onClick={() => handleSubscribe(plan.id)}
              disabled={checkoutLoading === plan.id || isActivePlan(plan.id)}
              style={{
                width: '100%',
                padding: '0.875rem',
                borderRadius: '10px',
                fontWeight: 700,
                fontSize: '0.95rem',
                cursor: isActivePlan(plan.id) ? 'default' : 'pointer',
                border: isActivePlan(plan.id) ? '1px solid rgba(16,185,129,0.5)' : 'none',
                background: isActivePlan(plan.id)
                  ? 'rgba(16, 185, 129, 0.3)'
                  : plan.popular
                    ? 'linear-gradient(135deg, #6366f1, #a855f7)'
                    : 'rgba(99, 102, 241, 0.2)',
                color: isActivePlan(plan.id) ? '#10b981' : 'white',
                opacity: checkoutLoading === plan.id ? 0.7 : 1,
                transition: 'all 0.2s',
              }}
            >
              {checkoutLoading === plan.id
                ? 'Redirecting to Stripe...'
                : isActivePlan(plan.id)
                  ? 'Current Plan'
                  : plan.id === 'enterprise'
                    ? 'Contact Sales'
                    : `Start Free Trial`}
            </button>
          </div>
        ))}
      </div>

      {/* GPU Cost Calculator */}
      <div style={{
        background: 'rgba(15, 23, 42, 0.8)',
        border: '1px solid rgba(255,255,255,0.06)',
        borderRadius: '16px',
        padding: '2rem',
        marginBottom: '2rem',
      }}>
        <h3 style={{ color: '#f1f5f9', fontWeight: 700, marginBottom: '1rem' }}>
          Why OrQuanta Pays for Itself
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem' }}>
          {[
            { label: 'Average GPU savings', value: '60%', sub: 'vs list price' },
            { label: 'Time saved per job', value: '45 min', sub: 'no manual provisioning' },
            { label: 'Idle compute eliminated', value: '87%', sub: 'auto-terminate on completion' },
            { label: 'ROI at $5K/mo spend', value: '30×', sub: 'after OrQuanta fees' },
          ].map((stat) => (
            <div key={stat.label} style={{ textAlign: 'center' }}>
              <div style={{
                fontSize: '2rem',
                fontWeight: 800,
                background: 'linear-gradient(135deg, #6366f1, #a855f7)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}>
                {stat.value}
              </div>
              <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '0.25rem' }}>{stat.label}</div>
              <div style={{ color: '#64748B', fontSize: '0.75rem' }}>{stat.sub}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Billing History */}
      {billingHistory.length > 0 && (
        <div style={{
          background: 'rgba(15, 23, 42, 0.8)',
          border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '16px',
          padding: '2rem',
        }}>
          <h3 style={{ color: '#f1f5f9', fontWeight: 700, marginBottom: '1.25rem' }}>
            Recent GPU Usage
          </h3>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                {['Date', 'Job', 'Provider', 'Cost'].map((h) => (
                  <th key={h} style={{ color: '#64748b', fontWeight: 600, padding: '0.75rem 0', textAlign: 'left', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {billingHistory.map((row, i) => (
                <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                  <td style={{ padding: '0.875rem 0', color: '#94a3b8', fontSize: '0.875rem' }}>{row.date}</td>
                  <td style={{ padding: '0.875rem 0', color: '#e2e8f0', fontSize: '0.875rem' }}>{row.description}</td>
                  <td style={{ padding: '0.875rem 0', fontSize: '0.875rem' }}>
                    <span style={{
                      background: 'rgba(99,102,241,0.15)',
                      color: '#a5b4fc',
                      borderRadius: '6px',
                      padding: '2px 8px',
                      fontSize: '0.75rem',
                    }}>
                      {row.provider}
                    </span>
                  </td>
                  <td style={{ padding: '0.875rem 0', color: '#10b981', fontWeight: 700, fontSize: '0.875rem' }}>
                    ${row.amount.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </motion.div>
  );
}

