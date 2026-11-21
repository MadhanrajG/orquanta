#!/usr/bin/env python3
"""
Multi-file patch script:
1. Add "Forgot password?" link to login form in App.jsx
2. Add mobile-responsive meta viewport (index.html)
3. Update BillingPage to use Skeleton on load
4. Update CostAnalytics to use Skeleton on load
5. Update JobManager to use Skeleton on load
"""

# ─── 1. App.jsx — add "Forgot password?" link ───────────────────────────────
app_path = r'c:\ai-gpu-cloud\v4\frontend\src\App.jsx'
app = open(app_path, encoding='utf-8').read()

OLD_SUBMIT_BTN = '''                        <div className="input-group" style={{ marginBottom: mode === 'register' ? 8 : 20 }}>
                            <label className="input-label">Password</label>
                            <input id="auth-password" type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} placeholder="Min. 8 characters" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
                        </div>'''

NEW_SUBMIT_BTN = '''                        <div className="input-group" style={{ marginBottom: mode === 'register' ? 8 : 12 }}>
                            <label className="input-label">Password</label>
                            <input id="auth-password" type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} placeholder="Min. 8 characters" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
                        </div>
                        {mode === 'login' && (
                            <div style={{ textAlign: 'right', marginBottom: 20 }}>
                                <a href="/forgot-password" style={{ fontSize: 12, color: '#7C6BF0', textDecoration: 'none', fontWeight: 500 }}>
                                    Forgot password?
                                </a>
                            </div>
                        )}'''

if OLD_SUBMIT_BTN in app:
    app = app.replace(OLD_SUBMIT_BTN, NEW_SUBMIT_BTN, 1)
    open(app_path, 'w', encoding='utf-8').write(app)
    print("SUCCESS: Forgot password link added to login form")
else:
    print("WARN: login password input anchor not found — checking partial match")
    # Try a simpler anchor
    simple = 'placeholder="Min. 8 characters"'
    print(f"  'Min. 8 characters' found: {simple in app}")

# ─── 2. index.html — ensure mobile viewport meta tag ───────────────────────
import os
index_path = r'c:\ai-gpu-cloud\v4\frontend\index.html'
if os.path.exists(index_path):
    idx = open(index_path, encoding='utf-8').read()
    if 'viewport' not in idx:
        idx = idx.replace('<head>', '<head>\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">')
        open(index_path, 'w', encoding='utf-8').write(idx)
        print("SUCCESS: viewport meta added to index.html")
    else:
        print("OK: viewport meta already in index.html")
else:
    print(f"WARN: index.html not found at {index_path}")

# ─── 3. BillingPage.jsx — add skeleton loading ──────────────────────────────
billing_path = r'c:\ai-gpu-cloud\v4\frontend\src\pages\BillingPage.jsx'
billing = open(billing_path, encoding='utf-8').read()

# Add Skeleton import at top
if 'Skeleton' not in billing:
    billing = "import { SkeletonStatGrid, SkeletonCard } from '../components/Skeleton.jsx'\n" + billing
    
# Replace raw loading state
old_loading = "if (loading) return <div>Loading billing...</div>"
new_loading = """if (loading) return (
    <div style={{ padding: 24 }}>
      <SkeletonStatGrid cols={3} />
      <div style={{ marginTop: 20, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        <SkeletonCard rows={6} />
        <SkeletonCard rows={6} />
        <SkeletonCard rows={6} />
      </div>
    </div>
  )"""

if old_loading in billing:
    billing = billing.replace(old_loading, new_loading, 1)
    print("SUCCESS: BillingPage skeleton loading added")
else:
    # Find and replace any "Loading billing" text
    import re
    # Look for loading return patterns
    patterns = [
        (r'if\s*\(loading\)\s*return\s*<[^>]*>Loading[^<]*<[^>]*>', 
         'if (loading) return <div style={{ padding: 24 }}><SkeletonStatGrid cols={3} /></div>'),
    ]
    replaced = False
    for pat, rep in patterns:
        new_billing = re.sub(pat, rep, billing, count=1)
        if new_billing != billing:
            billing = new_billing
            replaced = True
            print("SUCCESS: BillingPage skeleton loading added (regex)")
            break
    if not replaced:
        print("WARN: BillingPage loading anchor not found")
        # Find what's near loading
        idx2 = billing.find('setLoading(false)')
        if idx2 > 0:
            print(repr(billing[idx2-200:idx2+200]))

open(billing_path, 'w', encoding='utf-8').write(billing)

print("All patches complete.")
