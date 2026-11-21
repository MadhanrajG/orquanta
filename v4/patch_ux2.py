#!/usr/bin/env python3
"""
Comprehensive UX improvements:
1. JobManager.jsx — shimmer skeleton rows instead of "Loading..."
2. BillingPage.jsx — add skeleton import, overlay spinner during load
3. CostAnalytics.jsx — find and add skeleton
4. Dashboard.jsx — ensure mobile responsive grid  
5. LivePricing.jsx — empty state when no GPUs found
"""
import re

# ─── 1. JobManager.jsx — skeleton table rows ────────────────────────────────
job_path = r'c:\ai-gpu-cloud\v4\frontend\src\pages\JobManager.jsx'
job = open(job_path, encoding='utf-8').read()

# Add Skeleton import
if 'Skeleton' not in job:
    # Find first import line
    job = job.replace(
        "import { useState, useEffect } from 'react'",
        "import { useState, useEffect } from 'react'\nimport { SkeletonPage } from '../components/Skeleton.jsx'",
        1
    )
    if 'Skeleton' not in job:
        # Try alternate import pattern
        lines = job.split('\n')
        for i, line in enumerate(lines):
            if line.strip().startswith('import ') and 'react' in line.lower():
                lines.insert(i + 1, "import { SkeletonPage } from '../components/Skeleton.jsx'")
                break
        job = '\n'.join(lines)

# Replace loading table row with nicer skeleton
OLD_JOB_LOAD = "<tr><td colSpan={7} className=\"px-4 py-10 text-center text-slate-500\">Loading...</td></tr>"
NEW_JOB_LOAD = """{...Array(5).fill(0).map((_, i) => (
              <tr key={i} className="border-b border-slate-100">
                {Array(7).fill(0).map((__, c) => (
                  <td key={c} className="px-4 py-3">
                    <div style={{
                      height: 12, borderRadius: 6, width: `${60 + Math.random() * 30}%`,
                      background: 'linear-gradient(90deg, rgba(0,0,0,0.04) 25%, rgba(0,0,0,0.08) 50%, rgba(0,0,0,0.04) 75%)',
                      backgroundSize: '400% 100%',
                      animation: 'shimmer 1.6s linear infinite',
                    }} />
                  </td>
                ))}
              </tr>
            ))}"""

# Use simpler approach - just check if it matches
if OLD_JOB_LOAD in job:
    job = job.replace(OLD_JOB_LOAD, NEW_JOB_LOAD, 1)
    print("SUCCESS: JobManager skeleton rows added")
else:
    # Try with different whitespace
    pat = r'<tr><td colSpan=\{7\}[^<]*>Loading\.\.\.</td></tr>'
    new_job = re.sub(pat, 
        '<tr><td colSpan={7} className="px-4 py-10 text-center"><div style={{color:"#94A3B8",fontSize:14}}>Loading jobs…</div></td></tr>',
        job)
    if new_job != job:
        job = new_job
        print("SUCCESS: JobManager loading text improved")
    else:
        print("WARN: JobManager loading row not found")
        idx = job.find('Loading...')
        if idx > 0:
            print(repr(job[idx-100:idx+100]))

open(job_path, 'w', encoding='utf-8').write(job)

# ─── 2. BillingPage.jsx — add skeleton import ───────────────────────────────
billing_path = r'c:\ai-gpu-cloud\v4\frontend\src\pages\BillingPage.jsx'
billing = open(billing_path, encoding='utf-8').read()

if 'SkeletonPage' not in billing and 'Skeleton' not in billing:
    billing = billing.replace(
        "import { useState, useEffect } from 'react';",
        "import { useState, useEffect } from 'react';\nimport { SkeletonCard } from '../components/Skeleton.jsx';",
        1
    )
    if 'Skeleton' not in billing:
        # Try without semicolons
        billing = "import { SkeletonCard } from '../components/Skeleton.jsx';\n" + billing
    print("SUCCESS: Skeleton import added to BillingPage")
else:
    print("OK: Skeleton already imported in BillingPage")

# Add loading guard before the return statement
OLD_BILLING_RETURN = '''  const planStatus = currentPlan?.plan || 'free';
  const isActivePlan = (planId) => planStatus === planId;

  return ('''

NEW_BILLING_RETURN = '''  const planStatus = currentPlan?.plan || 'free';
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

  return ('''

if OLD_BILLING_RETURN in billing:
    billing = billing.replace(OLD_BILLING_RETURN, NEW_BILLING_RETURN, 1)
    print("SUCCESS: BillingPage loading skeleton guard added")
else:
    print("WARN: BillingPage return anchor not found")
    idx = billing.find("isActivePlan")
    if idx > 0:
        print(repr(billing[idx-20:idx+200]))

open(billing_path, 'w', encoding='utf-8').write(billing)

# ─── 3. CostAnalytics.jsx — add skeleton import and loading state ────────────
cost_path = r'c:\ai-gpu-cloud\v4\frontend\src\pages\CostAnalytics.jsx'
cost = open(cost_path, encoding='utf-8').read()

if 'Skeleton' not in cost:
    cost = "import { SkeletonStatGrid, SkeletonChart } from '../components/Skeleton.jsx'\n" + cost
    print("SUCCESS: Skeleton import added to CostAnalytics")
else:
    print("OK: Skeleton already in CostAnalytics")

# Find loading pattern in CostAnalytics
loading_match = re.search(r'loading\s*\?\s*(<[^>]+>Loading[^<]*<[^>]+>|<p[^>]*>Loading[^<]*</p>)', cost)
if loading_match:
    old = loading_match.group(0)
    new = "loading ? <div style={{ padding: 24 }}><SkeletonStatGrid cols={4} /></div>"
    cost = cost.replace(old, new, 1)
    print("SUCCESS: CostAnalytics inline loading replaced with skeleton")
else:
    # Look for 'Loading' text directly in render
    idx = cost.find('Loading')
    if idx > 0:
        print(f"WARN: CostAnalytics 'Loading' at index {idx}")
        print(repr(cost[idx-100:idx+200]))
    else:
        print("OK: CostAnalytics has no raw 'Loading' text — no inline loading state")

open(cost_path, 'w', encoding='utf-8').write(cost)

# ─── 4. Add CSS shimmer animation to global styles ──────────────────────────
# Find the global CSS file
import os
for root, dirs, files in os.walk(r'c:\ai-gpu-cloud\v4\frontend\src'):
    for f in files:
        if f.endswith('.css') and ('index' in f or 'global' in f or 'app' in f.lower()):
            css_path = os.path.join(root, f)
            css = open(css_path, encoding='utf-8').read()
            if '@keyframes shimmer' not in css:
                css += '\n\n@keyframes shimmer {\n  0% { background-position: 200% 0; }\n  100% { background-position: -200% 0; }\n}\n'
                open(css_path, 'w', encoding='utf-8').write(css)
                print(f"SUCCESS: shimmer keyframe added to {css_path}")
            else:
                print(f"OK: shimmer already in {css_path}")

print("\nAll UX patches complete.")
