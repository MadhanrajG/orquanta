import urllib.request
import json
import time
import sys

BASE_URL = "http://localhost:8000/api/v1"

def request(method, endpoint, data=None):
    url = f"{BASE_URL}{endpoint}"
    body = json.dumps(data).encode('utf-8') if data is not None else None
    
    req = urllib.request.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json'},
        method=method
    )
    
    try:
        with urllib.request.urlopen(req) as f:
            if f.status == 204: return None
            return json.loads(f.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"❌ {method} {url} FAILED: {e.code} {e.reason}")
        print(e.read().decode('utf-8'))
        raise e

def run_audit():
    print("🔎 STARTING HEADLESS AUDIT...")
    
    # 1. RESET (Explicit POST)
    print("1. Resetting State...")
    try:
        request("POST", "/reset", {})
    except:
        print("   (Reset failed, assuming clean state)")

    # 2. CHECK INITIAL POLICY
    pol = request("GET", "/policy")
    print(f"   Initial Policy: v{pol['version']} (Cost Weight: {pol['weights']['cost']:.2f})")

    # 3. SUBMIT NAIVE JOB
    print("\n2. Submitting Naive Job (Req: 80GB)...")
    j1 = request("POST", "/submit", {"intent": "Train 70b", "required_vram": 80})
    jid1 = j1["id"]
    decision1 = j1["governance"]["decision"]
    print(f"   Job ID: {jid1}")
    print(f"   Decision: {decision1}")
    
    # 4. WAIT FOR PHYSICS SIMULATION
    print("   Waiting for Sim...")
    time.sleep(2.0)
    
    # 5. CHECK FAILURE & MUTATION
    j1_status = request("GET", f"/jobs/{jid1}")
    print(f"   Status: {j1_status.get('status')} {j1_status.get('error','')}")
    if j1_status.get('status') != "failed": raise Exception("Job 1 should have failed (OOM)!")
    
    print("\n3. Verifying Evolution...")
    pol_new = request("GET", "/policy")
    print(f"   New Policy: v{pol_new['version']}")
    if pol_new["version"] <= pol["version"]: raise Exception("Policy did not evolve!")
    
    delta_risk = pol_new["weights"]["risk"] - pol["weights"]["risk"]
    print(f"   Risk Aversion Delta: +{delta_risk:.2f}")

    # 6. SUBMIT LEARNED JOB
    print("\n4. Submitting Job 2 (Identical Request)...")
    j2 = request("POST", "/submit", {"intent": "Train 70b", "required_vram": 80})
    jid2 = j2["id"]
    decision2 = j2["governance"]["decision"]
    print(f"   Job ID: {jid2}")
    print(f"   Decision: {decision2}")
    
    if decision2 == decision1: raise Exception("Decision did not change! Evolution failed.")
    if decision2 != "H100": raise Exception(f"Expected H100, got {decision2}")

    # 7. CHECK SUCCESS
    time.sleep(2.0)
    j2_status = request("GET", f"/jobs/{jid2}")
    print(f"   Status: {j2_status.get('status')}")
    if j2_status.get('status') != "completed": raise Exception("Job 2 failed!")

    print("\n✅ CERTIFIED: CAUSAL EVOLUTION VERIFIED.")

if __name__ == "__main__":
    run_audit()
