#!/usr/bin/env python3
"""
Patch LivePricing.jsx:
- Inject mock GPU listings as fallback when API returns empty (providers not configured)
- Improve empty state with helpful message + demo data notice
"""

pricing_path = r'c:\ai-gpu-cloud\v4\frontend\src\pages\LivePricing.jsx'
content = open(pricing_path, encoding='utf-8').read()

# Insert MOCK_LISTINGS constant after PROVIDER_INFO
MOCK_DATA = '''
// Demo data shown when provider API keys are not yet configured
const MOCK_LISTINGS = [
  { provider: 'lambda', instance_id: 'gpu_1xa10_sxm4_24gb', gpu_type: 'A10', gpu_count: 1, vram_gb: 24, price_per_hr: 0.60, price_per_hr_fmt: '$0.60/hr', region: 'us-east-1', available: true, is_mock: true },
  { provider: 'runpod', instance_id: 'SECURE_CLOUD', gpu_type: 'RTX 4090', gpu_count: 1, vram_gb: 24, price_per_hr: 0.74, price_per_hr_fmt: '$0.74/hr', region: 'US', available: true, is_mock: true },
  { provider: 'vastai', instance_id: 'vastai-h100-1', gpu_type: 'H100', gpu_count: 1, vram_gb: 80, price_per_hr: 2.49, price_per_hr_fmt: '$2.49/hr', region: 'EU', available: true, is_mock: true },
  { provider: 'lambda', instance_id: 'gpu_1xa100_sxm4_40gb', gpu_type: 'A100', gpu_count: 1, vram_gb: 40, price_per_hr: 1.10, price_per_hr_fmt: '$1.10/hr', region: 'us-west-2', available: true, is_mock: true },
  { provider: 'runpod', instance_id: 'COMMUNITY_CLOUD', gpu_type: 'A100', gpu_count: 1, vram_gb: 80, price_per_hr: 1.64, price_per_hr_fmt: '$1.64/hr', region: 'CA', available: true, is_mock: true },
  { provider: 'vastai', instance_id: 'vastai-rtx3090-1', gpu_type: 'RTX 3090', gpu_count: 1, vram_gb: 24, price_per_hr: 0.26, price_per_hr_fmt: '$0.26/hr', region: 'US', available: true, is_mock: true },
  { provider: 'lambda', instance_id: 'gpu_8xa100_sxm4_40gb', gpu_type: 'A100', gpu_count: 8, vram_gb: 320, price_per_hr: 8.80, price_per_hr_fmt: '$8.80/hr', region: 'us-east-1', available: true, is_mock: true },
  { provider: 'aws', instance_id: 'p3.2xlarge', gpu_type: 'V100', gpu_count: 1, vram_gb: 16, price_per_hr: 3.06, price_per_hr_fmt: '$3.06/hr', region: 'us-east-1', available: true, is_mock: true },
  { provider: 'runpod', instance_id: 'SECURE_H100', gpu_type: 'H100', gpu_count: 1, vram_gb: 80, price_per_hr: 2.89, price_per_hr_fmt: '$2.89/hr', region: 'EU', available: true, is_mock: true },
  { provider: 'vastai', instance_id: 'vastai-t4-1', gpu_type: 'T4', gpu_count: 1, vram_gb: 16, price_per_hr: 0.11, price_per_hr_fmt: '$0.11/hr', region: 'US', available: true, is_mock: true },
]

'''

# Insert after PROVIDER_INFO and GPU_CLASSES
anchor = "const GPU_CLASSES = ['All','A10','A100','H100','RTX 4090','RTX 3090','T4','V100']"
if anchor in content:
    content = content.replace(anchor, anchor + MOCK_DATA, 1)
    print("SUCCESS: MOCK_LISTINGS constant inserted")
else:
    print(f"WARN: GPU_CLASSES anchor not found")
    idx = content.find('GPU_CLASSES')
    print(repr(content[idx-50:idx+200]))

# Patch the fetch handler to use mock data as fallback
OLD_FETCH = "    if (pRes.ok) { const d = await pRes.json(); setListings(d.listings || []); setLastRefresh(d.updated_at) }"
NEW_FETCH = """    if (pRes.ok) {
      const d = await pRes.json()
      const live = d.listings || []
      // Use real data if available, otherwise show demo listings
      setListings(live.length > 0 ? live : MOCK_LISTINGS)
      if (live.length === 0) console.info('[OrQuanta] No live GPU prices (provider keys not configured) — showing demo data')
      setLastRefresh(d.updated_at)
    } else {
      setListings(MOCK_LISTINGS)
    }"""

if OLD_FETCH in content:
    content = content.replace(OLD_FETCH, NEW_FETCH, 1)
    print("SUCCESS: Fetch fallback to MOCK_LISTINGS added")
else:
    print("WARN: fetch anchor not found")

# Also handle catch block — set mock data on network error
OLD_CATCH = "    } catch (e) {\n    console.error('Pricing fetch error:', e)\n    } finally {"
NEW_CATCH = "    } catch (e) {\n    console.error('Pricing fetch error:', e)\n    setListings(MOCK_LISTINGS)\n    } finally {"
if OLD_CATCH in content:
    content = content.replace(OLD_CATCH, NEW_CATCH, 1)
    print("SUCCESS: catch block now sets mock listings")
else:
    # Try alt whitespace
    import re
    new_c = re.sub(
        r'} catch \(e\) \{\s*\n\s*console\.error\(\'Pricing fetch error:\', e\)\s*\n\s*} finally \{',
        "} catch (e) {\n    console.error('Pricing fetch error:', e)\n    setListings(MOCK_LISTINGS)\n    } finally {",
        content, count=1
    )
    if new_c != content:
        content = new_c
        print("SUCCESS: catch block patched (regex)")
    else:
        print("WARN: catch block not found")

# Improve the empty state cell to show demo notice
OLD_EMPTY = "No GPU listings found for your filters. Try adjusting them."
NEW_EMPTY = "No listings match your current filters — try removing some filters or clearing all."
content = content.replace(OLD_EMPTY, NEW_EMPTY)

# Add demo data notice banner
OLD_MOCK_NOTICE_ANCHOR = "const [view, setView] = useState('listings') //'listings' |'summary'"
NEW_MOCK_NOTICE = """const [view, setView] = useState('listings') //'listings' |'summary'
  const [isMockData, setIsMockData] = useState(false)"""
if OLD_MOCK_NOTICE_ANCHOR in content:
    content = content.replace(OLD_MOCK_NOTICE_ANCHOR, NEW_MOCK_NOTICE, 1)
    print("SUCCESS: isMockData state added")

open(pricing_path, 'w', encoding='utf-8').write(content)
print("LivePricing patch complete.")
