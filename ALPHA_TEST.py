"""
OrQuanta v1 Internal Alpha - Adversarial Fault Discovery
Real-world simulation under stress
"""

import urllib.request
import urllib.error
import json
import time
import concurrent.futures
import sys

BASE = "http://localhost:8000"
KEY = "dev-key-change-in-production"

def req(method, path, data=None, auth=True, expect_error=False):
    headers = {'Content-Type': 'application/json'}
    if auth:
        headers['X-API-Key'] = KEY
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(f"{BASE}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as f:
            return json.loads(f.read().decode()), f.status
    except urllib.error.HTTPError as e:
        return {"error": e.code}, e.code
    except Exception as e:
        return {"error": str(e)}, 500

results = {"passed": 0, "failed": 0, "warnings": 0, "details": []}

def test(name, condition, warning=False):
    if condition:
        results["passed"] += 1
        print(f"  ✅ {name}")
    elif warning:
        results["warnings"] += 1
        print(f"  ⚠️ {name}")
        results["details"].append(f"WARN: {name}")
    else:
        results["failed"] += 1
        print(f"  ❌ {name}")
        results["details"].append(f"FAIL: {name}")

# ===========================================
# SECURITY TESTS
# ===========================================
print("\n🔒 SECURITY TESTS")

# No auth
resp, code = req("GET", "/api/v1/policy", auth=False)
test("Reject request without auth", code == 401)

# Empty auth header
headers = {'Content-Type': 'application/json', 'X-API-Key': ''}
r = urllib.request.Request(f"{BASE}/api/v1/policy", headers=headers)
try:
    urllib.request.urlopen(r)
    test("Reject empty API key", False)
except urllib.error.HTTPError as e:
    test("Reject empty API key", e.code == 401)

# Health endpoint (should be open)
resp, code = req("GET", "/health", auth=False)
test("Health endpoint accessible without auth", code == 200)

# ===========================================
# LEARNING TESTS
# ===========================================
print("\n🧠 LEARNING TESTS")

# Reset to baseline
req("POST", "/api/v1/reset", {})
time.sleep(0.5)

# Initial state
pol1, _ = req("GET", "/api/v1/policy")
test("Initial policy is v1", pol1.get("version") == 1)

# Submit job that will OOM
job1, _ = req("POST", "/api/v1/submit", {"intent": "Train 70b", "required_vram": 80})
test("Job submission returns decision", "decision" in job1)

time.sleep(1.5)  # Wait for physics

# Check evolution
pol2, _ = req("GET", "/api/v1/policy")
test("Policy evolved after OOM", pol2.get("version", 0) > 1)

# Submit identical intent
job2, _ = req("POST", "/api/v1/submit", {"intent": "Train 70b", "required_vram": 80})
test("Decision changes after learning", job1.get("decision") != job2.get("decision"), warning=True)

# ===========================================
# SAFETY BOUNDS TESTS
# ===========================================
print("\n🛡️ SAFETY BOUNDS TESTS")

# Force extreme mutations
for i in range(10):
    req("POST", "/api/v1/submit", {"intent": f"Stress{i}", "required_vram": 200})
time.sleep(2)

pol_stress, _ = req("GET", "/api/v1/policy")
weights = pol_stress.get("weights", {})

test("Cost weight ≥ 0.05", weights.get("cost", 0) >= 0.05)
test("Cost weight ≤ 0.95", weights.get("cost", 1) <= 0.95)
test("Perf weight ≥ 0.05", weights.get("perf", 0) >= 0.05)
test("Perf weight ≤ 0.95", weights.get("perf", 1) <= 0.95)
test("Risk weight ≥ 0.05", weights.get("risk", 0) >= 0.05)
test("Risk weight ≤ 0.95", weights.get("risk", 1) <= 0.95)

total = sum(weights.values()) if weights else 0
test("Weights sum to 1.0", abs(total - 1.0) < 0.01)

# ===========================================
# ROLLBACK TESTS
# ===========================================
print("\n🔄 ROLLBACK TESTS")

# Rollback to v1
resp, code = req("POST", "/api/v1/policy/rollback/1", {})
test("Rollback returns success", code == 200)

pol_rb, _ = req("GET", "/api/v1/policy")
test("Rollback restores v1", pol_rb.get("version") == 1)
test("Rollback restores baseline cost", abs(pol_rb.get("weights", {}).get("cost", 0) - 0.8) < 0.01)

# Invalid rollback
resp, code = req("POST", "/api/v1/policy/rollback/9999", {})
test("Invalid rollback returns 404", code == 404)

# ===========================================
# CONCURRENT STRESS TESTS
# ===========================================
print("\n⚡ CONCURRENCY TESTS")

req("POST", "/api/v1/reset", {})
time.sleep(0.5)

pol_before, _ = req("GET", "/api/v1/policy")
v_before = pol_before.get("version", 0)

def submit_oom():
    return req("POST", "/api/v1/submit", {"intent": "concurrent", "required_vram": 200})

with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
    futures = [executor.submit(submit_oom) for _ in range(15)]
    concurrent.futures.wait(futures)

time.sleep(2)

pol_after, _ = req("GET", "/api/v1/policy")
v_after = pol_after.get("version", 0)

test("Concurrent OOMs increment version", v_after > v_before)
test("No lost mutations (15 OOMs)", v_after - v_before >= 10, warning=True)  # Some may not OOM

# ===========================================
# PERSISTENCE TESTS
# ===========================================
print("\n💾 PERSISTENCE TESTS")

import os
test("Policy file exists", os.path.exists("orquanta_policy_prod.json"))

if os.path.exists("orquanta_policy_prod.json"):
    with open("orquanta_policy_prod.json") as f:
        disk = json.load(f)
    test("Disk version matches API", disk.get("v") == pol_after.get("version"))

# ===========================================
# INPUT EDGE CASES
# ===========================================
print("\n🔬 INPUT EDGE CASES")

# Negative VRAM (should ideally reject, but document if accepted)
resp, code = req("POST", "/api/v1/submit", {"intent": "test", "required_vram": -1})
test("Negative VRAM handled (accepted/rejected)", code in [200, 400, 422], warning=(code == 200))

# Zero VRAM
resp, code = req("POST", "/api/v1/submit", {"intent": "test", "required_vram": 0})
test("Zero VRAM handled", code in [200, 400, 422], warning=(code == 200))

# Very large intent (10KB)
resp, code = req("POST", "/api/v1/submit", {"intent": "x" * 10000, "required_vram": 16})
test("Large intent handled", code in [200, 413, 422], warning=(code == 200))

# ===========================================
# SUMMARY
# ===========================================
print("\n" + "=" * 50)
print(f"RESULTS: {results['passed']} passed, {results['failed']} failed, {results['warnings']} warnings")
print("=" * 50)

if results["failed"] > 0:
    print("\n❌ LAUNCH BLOCKED - Critical failures detected:")
    for d in results["details"]:
        if d.startswith("FAIL"):
            print(f"   {d}")
    sys.exit(1)
elif results["warnings"] > 0:
    print("\n⚠️ LAUNCH APPROVED (with known limitations):")
    for d in results["details"]:
        print(f"   {d}")
    sys.exit(0)
else:
    print("\n✅ LAUNCH APPROVED - All tests passed")
    sys.exit(0)
