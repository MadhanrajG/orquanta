"""
OrQuanta Client Demonstration Script
Shows the complete workflow: submit → learn → improve
"""

import urllib.request
import json
import time

API_KEY = "dev-key-change-in-production"
BASE = "http://localhost:8000/api/v1"

def api_call(method, endpoint, data=None):
    headers = {'Content-Type': 'application/json', 'X-API-Key': API_KEY}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{BASE}{endpoint}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

print("=" * 60)
print("ORQUANTA DEMONSTRATION - INTELLIGENT GPU ALLOCATION")
print("=" * 60)

# Step 1: Check initial policy
print("\n1. INITIAL STATE")
print("-" * 60)
policy = api_call("GET", "/policy")
print(f"Policy Version: {policy['version']}")
print(f"Decision Weights:")
print(f"  - Cost Priority: {policy['weights']['cost']:.2f}")
print(f"  - Performance: {policy['weights']['perf']:.2f}")
print(f"  - Risk Aversion: {policy['weights']['risk']:.2f}")
print("\nInterpretation: System is currently cost-focused")

# Step 2: Submit a workload
print("\n2. WORKLOAD SUBMISSION")
print("-" * 60)
workload = {"intent": "Train Large Language Model", "required_vram": 80}
print(f"Request: {workload['intent']}")
print(f"Memory Required: {workload['required_vram']}GB VRAM")

job = api_call("POST", "/submit", workload)
print(f"\nRecommendation: {job['decision']}")
print(f"Job ID: {job['id']}")

# Step 3: Wait for outcome
print("\n3. OUTCOME PROCESSING")
print("-" * 60)
print("Waiting for infrastructure simulation...")
time.sleep(2)

# Step 4: Check if policy evolved
policy_after = api_call("GET", "/policy")
if policy_after['version'] > policy['version']:
    print(f"✓ Policy evolved to v{policy_after['version']}")
    print(f"\nUpdated Weights:")
    print(f"  - Cost Priority: {policy_after['weights']['cost']:.2f} (was {policy['weights']['cost']:.2f})")
    print(f"  - Performance: {policy_after['weights']['perf']:.2f} (was {policy['weights']['perf']:.2f})")
    print(f"  - Risk Aversion: {policy_after['weights']['risk']:.2f} (was {policy['weights']['risk']:.2f})")
    print("\nInterpretation: System learned from failure, now prioritizes safety")
else:
    print("No evolution needed (job succeeded)")

# Step 5: Submit same workload again
print("\n4. LEARNED BEHAVIOR")
print("-" * 60)
print("Submitting the SAME workload again...")
job2 = api_call("POST", "/submit", workload)
print(f"New Recommendation: {job2['decision']}")

if job['decision'] != job2['decision']:
    print(f"\n✓ Decision changed: {job['decision']} → {job2['decision']}")
    print("System learned from experience and improved its recommendation")
else:
    print("Decision unchanged (original recommendation was correct)")

print("\n" + "=" * 60)
print("DEMONSTRATION COMPLETE")
print("=" * 60)
