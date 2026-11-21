#!/usr/bin/env python3
"""
Final UX polish:
1. JobManager — responsive grid + table overflow-x
2. LivePricing — demo data banner
3. HelpPage — forgot password FAQ entry
"""

# ─── 1. JobManager.jsx ───────────────────────────────────────────────────────
job_path = r'c:\ai-gpu-cloud\v4\frontend\src\pages\JobManager.jsx'
job = open(job_path, encoding='utf-8').read()

# Stat cards: 4-col grid → responsive
job = job.replace(
    'className="grid grid-cols-4 gap-3"',
    'className="grid grid-cols-2 md:grid-cols-4 gap-3"'
)

# 2-col grid → responsive
job = job.replace(
    'className="grid grid-cols-2 gap-3"',
    'className="grid grid-cols-1 sm:grid-cols-2 gap-3"'
)

# Add overflow-x-auto to table wrapper
OLD_TABLE_WRAPPER = '<div className="glass-card overflow-hidden">'
NEW_TABLE_WRAPPER = '<div className="glass-card overflow-hidden"><div className="overflow-x-auto -mx-0">'
if OLD_TABLE_WRAPPER in job:
    job = job.replace(OLD_TABLE_WRAPPER, NEW_TABLE_WRAPPER, 1)
    # Close the extra div before the closing glass-card div
    job = job.replace('</table>\n </div>', '</table>\n </div></div>', 1)
    print('SUCCESS: JobManager table overflow-x added')
else:
    print('WARN: JobManager table wrapper not found')

open(job_path, 'w', encoding='utf-8').write(job)
print('JobManager responsive:', 'grid-cols-2 md:grid-cols-4' in job)

# ─── 2. LivePricing.jsx — demo data notice ───────────────────────────────────
pricing_path = r'c:\ai-gpu-cloud\v4\frontend\src\pages\LivePricing.jsx'
pricing = open(pricing_path, encoding='utf-8').read()

DEMO_ANCHOR = " <p className=\"text-slate-500 text-sm mt-1\">"

DEMO_BANNER = """ {listings.length > 0 && listings[0] && listings[0].is_mock && (
    <div style={{
      marginTop: 8, padding: '5px 12px', borderRadius: 8,
      display: 'inline-flex', alignItems: 'center', gap: 8,
      background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)',
    }}>
      <span style={{ fontSize: 11, color: '#F59E0B', fontWeight: 700 }}>DEMO</span>
      <span style={{ fontSize: 11, color: '#94A3B8' }}>
        Sample prices shown. Add provider API keys to load live data.
      </span>
    </div>
  )}
 <p className="text-slate-500 text-sm mt-1">"""

if DEMO_ANCHOR in pricing:
    pricing = pricing.replace(DEMO_ANCHOR, DEMO_BANNER, 1)
    print('SUCCESS: LivePricing demo banner added')
else:
    print('WARN: LivePricing demo banner anchor not found')
    idx = pricing.find('text-slate-500 text-sm')
    if idx > 0:
        print(repr(pricing[idx-50:idx+100]))

open(pricing_path, 'w', encoding='utf-8').write(pricing)

# ─── 3. HelpPage.jsx — forgot password FAQ ───────────────────────────────────
help_path = r'c:\ai-gpu-cloud\v4\frontend\src\pages\HelpPage.jsx'
help_p = open(help_path, encoding='utf-8').read()

FAQ_ANCHOR = 'const FAQ_ITEMS'
if FAQ_ANCHOR in help_p:
    idx = help_p.find('[', help_p.find(FAQ_ANCHOR))
    new_entry = """[
  {
    question: 'How do I reset my password?',
    answer: "Click 'Forgot password?' on the Sign In page, enter your email address, and check your inbox for a reset link. The link expires in 1 hour. If you don't receive it, check your spam folder or contact support@orquanta.com.",
  },"""
    help_p = help_p[:idx] + new_entry + help_p[idx+1:]
    open(help_path, 'w', encoding='utf-8').write(help_p)
    print('SUCCESS: HelpPage forgot-password FAQ entry added')
else:
    print('WARN: FAQ_ITEMS not found in HelpPage')

print('All polish patches complete.')
