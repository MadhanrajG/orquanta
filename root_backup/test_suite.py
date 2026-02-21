"""
OrQuanta Pre-Launch Test Suite
Comprehensive headless validation of all use cases and safety requirements.
"""

import urllib.request
import json
import time
import sys
import os

BASE = "http://localhost:8000/api/v1"
POLICY_FILE = "orquanta_policy_prod.json"

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def add(self, test_id, name, passed, details=""):
        self.results.append({"id": test_id, "name": name, "passed": passed, "details": details})
        if passed:
            self.passed += 1
            print(f"  ✅ {test_id}: {name}")
        else:
            self.failed += 1
            print(f"  ❌ {test_id}: {name} — {details}")

results = TestResult()

def req(method, endpoint, data=None, expect_error=False):
    try:
        body = json.dumps(data).encode() if data else None
        r = urllib.request.Request(f"{BASE}{endpoint}", method=method, 
                                   headers={'Content-Type': 'application/json'}, data=body)
        with urllib.request.urlopen(r) as f:
            return json.loads(f.read()), f.status
    except urllib.error.HTTPError as e:
        if expect_error:
            return {"error": str(e.code)}, e.code
        raise

def reset():
    req("POST", "/reset", {})

# ============================================================
# FUNCTIONAL TESTS
# ============================================================

def test_functional():
    print("\n📋 FUNCTIONAL TESTS")
    
    reset()
    
    # F1: Submit job returns decision
    try:
        resp, status = req("POST", "/submit", {"intent": "Test", "required_vram": 16})
        passed = status == 200 and "decision" in resp
        results.add("F1", "Submit returns decision", passed, resp.get("decision", "missing"))
    except Exception as e:
        results.add("F1", "Submit returns decision", False, str(e))
    
    time.sleep(1)
    
    # F2: Policy version increments after OOM
    reset()
    pol_before, _ = req("GET", "/policy")
    req("POST", "/submit", {"intent": "Big", "required_vram": 80})  # Forces OOM on T4
    time.sleep(1)
    pol_after, _ = req("GET", "/policy")
    passed = pol_after["version"] > pol_before["version"]
    results.add("F2", "Version increments after OOM", passed, 
                f"v{pol_before['version']} → v{pol_after['version']}")
    
    # F3: Identical intent produces different decision after learning
    reset()
    j1, _ = req("POST", "/submit", {"intent": "Train", "required_vram": 80})
    time.sleep(1)
    j2, _ = req("POST", "/submit", {"intent": "Train", "required_vram": 80})
    passed = j1["decision"] != j2["decision"]
    results.add("F3", "Decision changes after learning", passed,
                f"{j1['decision']} → {j2['decision']}")
    
    # F4: Rollback restores weights
    reset()
    pol_v1, _ = req("GET", "/policy")
    req("POST", "/submit", {"intent": "OOM", "required_vram": 80})
    time.sleep(1)
    req("POST", "/policy/rollback/1", {})
    pol_rb, _ = req("GET", "/policy")
    passed = abs(pol_rb["weights"]["cost"] - pol_v1["weights"]["cost"]) < 0.01
    results.add("F4", "Rollback restores weights", passed,
                f"cost={pol_rb['weights']['cost']:.2f}")

# ============================================================
# FAILURE TESTS
# ============================================================

def test_failure():
    print("\n⚠️ FAILURE TESTS")
    
    reset()
    
    # FL1: OOM triggers mutation
    pol_before, _ = req("GET", "/policy")
    resp, _ = req("POST", "/submit", {"intent": "Fail", "required_vram": 200})
    time.sleep(1)
    pol_after, _ = req("GET", "/policy")
    passed = pol_after["version"] > pol_before["version"]
    results.add("FL1", "OOM triggers mutation", passed)
    
    # FL2: Invalid input rejected
    try:
        _, status = req("POST", "/submit", {"wrong_field": "bad"}, expect_error=True)
        passed = status == 422
        results.add("FL2", "Invalid input rejected", passed, f"status={status}")
    except:
        results.add("FL2", "Invalid input rejected", False, "No error raised")
    
    # FL3: Rollback to nonexistent version
    try:
        _, status = req("POST", "/policy/rollback/999", {}, expect_error=True)
        passed = status == 404
        results.add("FL3", "Invalid rollback rejected", passed, f"status={status}")
    except:
        results.add("FL3", "Invalid rollback rejected", False)
    
    # FL4: Multiple rapid failures don't crash
    reset()
    success = True
    for i in range(10):
        try:
            req("POST", "/submit", {"intent": f"Stress{i}", "required_vram": 100})
        except:
            success = False
            break
    time.sleep(2)
    pol, _ = req("GET", "/policy")
    passed = success and pol["version"] > 1
    results.add("FL4", "Rapid failures handled", passed, f"v{pol['version']}")

# ============================================================
# SAFETY TESTS
# ============================================================

def test_safety():
    print("\n🛡️ SAFETY TESTS")
    
    reset()
    
    # Force extreme mutation
    for _ in range(5):
        req("POST", "/submit", {"intent": "Extreme", "required_vram": 200})
        time.sleep(0.5)
    
    pol, _ = req("GET", "/policy")
    
    # S1: No weight exceeds 0.95
    max_weight = max(pol["weights"].values())
    passed = max_weight <= 0.95
    results.add("S1", "Max weight ≤ 0.95", passed, f"max={max_weight:.3f}")
    
    # S2: No weight below 0.05
    min_weight = min(pol["weights"].values())
    passed = min_weight >= 0.05
    results.add("S2", "Min weight ≥ 0.05", passed, f"min={min_weight:.3f}")
    
    # S3: Weights sum to 1.0
    total = sum(pol["weights"].values())
    passed = abs(total - 1.0) < 0.01
    results.add("S3", "Weights sum to 1.0", passed, f"sum={total:.3f}")
    
    # S4: Rollback preserves bounds
    req("POST", "/policy/rollback/1", {})
    pol_rb, _ = req("GET", "/policy")
    min_rb = min(pol_rb["weights"].values())
    max_rb = max(pol_rb["weights"].values())
    passed = min_rb >= 0.05 and max_rb <= 0.95
    results.add("S4", "Rollback preserves bounds", passed)

# ============================================================
# PERSISTENCE TESTS
# ============================================================

def test_persistence():
    print("\n💾 PERSISTENCE TESTS")
    
    reset()
    
    # Trigger mutation
    req("POST", "/submit", {"intent": "Persist", "required_vram": 80})
    time.sleep(1)
    
    pol, _ = req("GET", "/policy")
    
    # P1: Check file exists (we can't restart server, but verify file)
    passed = os.path.exists(POLICY_FILE)
    results.add("P1", "Policy file exists", passed)
    
    # P2: File content matches API
    if passed:
        with open(POLICY_FILE) as f:
            disk_data = json.load(f)
        passed = disk_data["v"] == pol["version"]
        results.add("P2", "File matches API state", passed, 
                    f"disk=v{disk_data['v']}, api=v{pol['version']}")
    else:
        results.add("P2", "File matches API state", False, "No file")
    
    # P3: History recorded
    passed = len(disk_data.get("h", [])) > 0
    results.add("P3", "History recorded", passed, f"entries={len(disk_data.get('h', []))}")

# ============================================================
# AUDITABILITY TESTS
# ============================================================

def test_auditability():
    print("\n📝 AUDITABILITY TESTS")
    
    reset()
    req("POST", "/submit", {"intent": "Audit", "required_vram": 80})
    time.sleep(1)
    
    with open(POLICY_FILE) as f:
        disk_data = json.load(f)
    
    history = disk_data.get("h", [])
    
    if not history:
        results.add("A1", "Mutation cause recorded", False, "No history")
        results.add("A2", "Delta recorded", False, "No history")
        results.add("A3", "Timestamp recorded", False, "No history")
        return
    
    latest = history[-1]
    
    # A1: Cause recorded
    passed = "cause" in latest and len(latest["cause"]) > 0
    results.add("A1", "Mutation cause recorded", passed, latest.get("cause", "")[:50])
    
    # A2: Delta recorded
    passed = "delta" in latest and isinstance(latest["delta"], dict)
    results.add("A2", "Delta recorded", passed)
    
    # A3: Timestamp recorded
    passed = "ts" in latest and "T" in latest["ts"]  # ISO format has T
    results.add("A3", "Timestamp recorded", passed, latest.get("ts", "")[:19])

# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("  OrQuanta Pre-Launch Test Suite")
    print("=" * 60)
    
    test_functional()
    test_failure()
    test_safety()
    test_persistence()
    test_auditability()
    
    print("\n" + "=" * 60)
    print(f"  RESULTS: {results.passed} passed, {results.failed} failed")
    print("=" * 60)
    
    if results.failed == 0:
        print("\n✅ ALL TESTS PASSED — READY FOR LAUNCH")
        return 0
    else:
        print("\n❌ TESTS FAILED — NOT READY")
        return 1

if __name__ == "__main__":
    sys.exit(main())
