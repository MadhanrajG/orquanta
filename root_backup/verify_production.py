import urllib.request
import json
import time

BASE = "http://localhost:8000/api/v1"

def req(m, ep, d=None):
    try:
        r = urllib.request.Request(f"{BASE}{ep}", method=m, headers={'Content-Type':'application/json'}, data=json.dumps(d).encode() if d else None)
        with urllib.request.urlopen(r) as f: return json.loads(f.read())
    except Exception as e:
        print(f"❌ {m} {ep} Failed: {e}")
        raise e

def audit():
    print("🛡️ STARTING PRODUCTION AUDIT...")
    
    # 1. RESET
    req("POST", "/reset", {})
    init = req("GET", "/policy")
    print(f"1. Init Policy v{init['version']}: {init['weights']}")

    # 2. TRIGGER EVOLUTION
    print("\n2. Triggering Evolution (OOM)...")
    j1 = req("POST", "/submit", {"intent": "Train", "required_vram": 80})
    print(f"   Job 1 Decision: {j1['decision']} (Expected T4)")
    time.sleep(1) # Physics
    
    pol_v2 = req("GET", "/policy")
    print(f"   Policy v{pol_v2['version']}: {pol_v2['weights']}")
    
    # 3. VERIFY EVOLUTION & BOUNDS
    if pol_v2["version"] == 1: raise Exception("Failed to Evolve")
    if pol_v2["weights"]["risk"] < 0.5: raise Exception("Risk aversion too low after OOM")
    if pol_v2["weights"]["cost"] < 0.05: raise Exception("Safety Bound Violated! Cost < 0.05")
    print("✅ Evolution & Safety Bounds Verified.")

    # 4. ROLLBACK
    print("\n3. Testing Rollback to v1...")
    req("POST", "/policy/rollback/1", {})
    pol_rb = req("GET", "/policy")
    print(f"   Rolled Back Policy: v{pol_rb['version']} Weights: {pol_rb['weights']}")
    
    # Check if weights match v1 (approx)
    if abs(pol_rb["weights"]["cost"] - init["weights"]["cost"]) > 0.01:
        raise Exception("Rollback failed! Weights do not match v1.")
    print("✅ Rollback Verified.")

    # 5. VERIFY BEHAVIOR REVERTED
    print("\n4. Verifying Behavior Reversion...")
    j3 = req("POST", "/submit", {"intent": "Train", "required_vram": 80})
    print(f"   Job 3 Decision: {j3['decision']}")
    if j3["decision"] != "T4": raise Exception("Rollback did not restore naive behavior!")
    
    print("\n✅ CERTIFIED: PRODUCTION HARDENING COMPLETE.")

if __name__ == "__main__":
    audit()
