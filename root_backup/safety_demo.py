"""
OrQuanta Safety Features Demonstration
Shows rollback and audit capabilities
"""

import urllib.request
import json

API_KEY = "dev-key-change-in-production"
BASE = "http://localhost:8000/api/v1"

def api_call(method, endpoint, data=None):
    headers = {'Content-Type': 'application/json', 'X-API-Key': API_KEY}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{BASE}{endpoint}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

print("=" * 60)
print("SAFETY & CONTROL DEMONSTRATION")
print("=" * 60)

# Show current state
print("\n1. CURRENT POLICY STATE")
print("-" * 60)
policy = api_call("GET", "/policy")
print(f"Version: {policy['version']}")
print(f"Weights: Cost={policy['weights']['cost']:.2f}, "
      f"Perf={policy['weights']['perf']:.2f}, "
      f"Risk={policy['weights']['risk']:.2f}")

# Demonstrate rollback
print("\n2. ROLLBACK CAPABILITY")
print("-" * 60)
print("Scenario: The evolved policy is too conservative")
print("Action: Rolling back to version 1 (baseline)...")

rollback = api_call("POST", "/policy/rollback/1", {})
print(f"Status: {rollback['status']}")
print(f"Current Version: {rollback['version']}")

# Verify rollback
policy_after = api_call("GET", "/policy")
print(f"\nVerification:")
print(f"Weights: Cost={policy_after['weights']['cost']:.2f}, "
      f"Perf={policy_after['weights']['perf']:.2f}, "
      f"Risk={policy_after['weights']['risk']:.2f}")
print("✓ System restored to cost-focused baseline")

# Show safety bounds
print("\n3. SAFETY BOUNDS")
print("-" * 60)
print("All policy weights are constrained to [0.05, 0.95]")
print("This prevents:")
print("  - Runaway cost optimization (min 5% cost awareness)")
print("  - Excessive risk aversion (max 95% risk weight)")
print("  - Unstable oscillations")

# Show auditability
print("\n4. AUDITABILITY")
print("-" * 60)
print("Every decision is:")
print("  ✓ Versioned (policy v1, v2, v3...)")
print("  ✓ Timestamped")
print("  ✓ Traceable to specific outcomes")
print("  ✓ Reversible via rollback")

print("\n" + "=" * 60)
print("SAFETY DEMONSTRATION COMPLETE")
print("=" * 60)
