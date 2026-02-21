import urllib.request
import json
import time
import sys
import os

BASE = "http://localhost:8000/api/v1"
API_KEY = "dev-key-change-in-production"

def log(msg): print(f"[GATE] {msg}")

def req(m, ep, d=None):
    try:
        headers = {'Content-Type':'application/json', 'X-API-Key': API_KEY}
        r = urllib.request.Request(f"{BASE}{ep}", method=m, headers=headers, data=json.dumps(d).encode() if d else None)
        with urllib.request.urlopen(r) as f: return json.loads(f.read())
    except Exception as e:
        log(f"❌ API FAIL: {ep} - {e}")
        sys.exit(1)

def launch_gate():
    log("🔒 INITIATING LAUNCH READINESS GATES...")
    
    # GATE 1: GROUND TRUTH
    log("GATE 1: Validating Ground Truth (Reset)...")
    req("POST", "/reset", {})
    init = req("GET", "/policy")
    if init["version"] != 1: sys.exit(1)
    
    # GATE 2: FAILURE-FIRST LEARNING
    log("GATE 2: Testing Failure-First Learning...")
    j1 = req("POST", "/submit", {"intent": "Train", "required_vram": 80})
    if j1["decision"] != "T4": 
        log(f"FAIL: Expected T4, got {j1['decision']}")
        sys.exit(1)
    
    time.sleep(1.5) # Wait for Physics & Mutation
    
    pol_v2 = req("GET", "/policy")
    log(f"   State after OOM: {pol_v2['weights']}")
    
    if pol_v2["version"] == 1: 
        log("FAIL: Evolution did not occur.")
        sys.exit(1)
        
    # GATE 3: SAFETY BOUNDS
    log("GATE 3: Verifying Safety Bounds (0.05 - 0.95)...")
    for k, v in pol_v2["weights"].items():
        if v < 0.05 or v > 0.95:
            log(f"FAIL: Weight {k}={v} violates bounds.")
            sys.exit(1)

    # GATE 4: BEHAVIORAL CHANGE
    log("GATE 4: Verifying Behavioral Change...")
    j2 = req("POST", "/submit", {"intent": "Train", "required_vram": 80})
    if j2["decision"] == "T4":
        log("FAIL: System did not learn (Still chose T4).")
        sys.exit(1)
    log(f"   Learned Decision: {j2['decision']}")

    # GATE 5: PERSISTENCE
    log("GATE 5: Verifying Disk Persistence...")
    if not os.path.exists("orquanta_policy_prod.json"):
        log("FAIL: Policy file not found on disk.")
        sys.exit(1)
    with open("orquanta_policy_prod.json") as f:
        disk_data = json.load(f)
        if disk_data["v"] != pol_v2["version"]:
            log("FAIL: Disk state mismatch.")
            sys.exit(1)
            
    # GATE 6: ROLLBACK
    log("GATE 6: Testing Deterministic Rollback...")
    req("POST", "/policy/rollback/1", {})
    pol_rb = req("GET", "/policy")
    if pol_rb["version"] != 1:
        log("FAIL: Rollback version mismatch.")
        sys.exit(1)
        
    j3 = req("POST", "/submit", {"intent": "Train", "required_vram": 80})
    if j3["decision"] != "T4":
        log("FAIL: Behavior did not revert after rollback.")
        sys.exit(1)

    log("\n✅ ALL GATES PASSED. SYSTEM IS ENTERPRISE READY.")

if __name__ == "__main__":
    launch_gate()
