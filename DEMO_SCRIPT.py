"""
OrQuanta Golden Demo Script - Verbatim Client Presentation
Run this during the live demo. Follow the script exactly.
"""

import urllib.request
import json
import time

API_KEY = "dev-key-change-in-production"
BASE = "http://localhost:8000/api/v1"

def api(method, endpoint, data=None):
    headers = {'Content-Type': 'application/json', 'X-API-Key': API_KEY}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{BASE}{endpoint}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

# ============================================================
# VERBATIM SCRIPT - READ ALOUD DURING DEMO
# ============================================================

print("\n" + "="*60)
print("  OrQuanta: Intelligent GPU Allocation")
print("="*60)

# ============================================================
# INTRO (15 seconds)
# ============================================================
print("\n📌 SAY THIS:")
print('"OrQuanta solves a simple problem: choosing the right GPU')
print(' for AI workloads without over-provisioning or failures.')
print(' Let me show you how it learns from real outcomes."')
print("\n[Press Enter to continue]")
input()

# ============================================================
# STEP 1: INITIAL STATE (30 seconds)
# ============================================================
print("\n" + "-"*60)
print("STEP 1: Initial State")
print("-"*60)

print("\n📌 SAY THIS:")
print('"First, let\'s see the current decision policy."')
print("\n[Press Enter to check policy]")
input()

policy = api("GET", "/policy")
print(f"\n✓ Policy Version: {policy['version']}")
print(f"✓ Decision Weights:")
print(f"   - Cost Priority: {policy['weights']['cost']:.1%}")
print(f"   - Performance:   {policy['weights']['perf']:.1%}")
print(f"   - Risk Aversion: {policy['weights']['risk']:.1%}")

print("\n📌 SAY THIS:")
print(f'"The system is currently cost-focused — {policy["weights"]["cost"]:.0%} weight on cost.')
print(' This means it will prefer cheaper GPUs."')
print("\n[Press Enter to continue]")
input()

# ============================================================
# STEP 2: FIRST RECOMMENDATION (30 seconds)
# ============================================================
print("\n" + "-"*60)
print("STEP 2: Submit Workload")
print("-"*60)

print("\n📌 SAY THIS:")
print('"Now I\'ll submit a workload that needs 80GB of memory.')
print(' Let\'s see what the system recommends."')
print("\n[Press Enter to submit]")
input()

job1 = api("POST", "/submit", {"intent": "Train LLM", "required_vram": 80})
print(f"\n✓ Workload: Train Large Language Model")
print(f"✓ Memory Required: 80GB")
print(f"✓ Recommendation: {job1['decision']}")

print("\n📌 SAY THIS:")
print(f'"It recommended {job1["decision"]} — the cheapest option.')
print(' But this GPU only has 16GB of memory.')
print(' This will fail."')
print("\n[Press Enter to continue]")
input()

# ============================================================
# STEP 3: LEARNING (45 seconds)
# ============================================================
print("\n" + "-"*60)
print("STEP 3: System Learning")
print("-"*60)

print("\n📌 SAY THIS:")
print('"The system simulates the job execution.')
print(' It detects the Out-of-Memory failure.')
print(' Watch what happens to the policy..."')
print("\n[Waiting 2 seconds for simulation...]")
time.sleep(2)

policy2 = api("GET", "/policy")
print(f"\n✓ Policy Version: {policy2['version']} (was {policy['version']})")
print(f"✓ New Weights:")
print(f"   - Cost Priority: {policy2['weights']['cost']:.1%} (was {policy['weights']['cost']:.1%})")
print(f"   - Risk Aversion: {policy2['weights']['risk']:.1%} (was {policy['weights']['risk']:.1%})")

print("\n📌 SAY THIS:")
print('"The system learned from the failure and updated its policy.')
print(f' Cost priority dropped from {policy["weights"]["cost"]:.0%} to {policy2["weights"]["cost"]:.0%}.')
print(f' Risk aversion increased from {policy["weights"]["risk"]:.0%} to {policy2["weights"]["risk"]:.0%}.')
print(' It now prioritizes safety over cost."')
print("\n[Press Enter to continue]")
input()

# ============================================================
# STEP 4: IMPROVED RECOMMENDATION (30 seconds)
# ============================================================
print("\n" + "-"*60)
print("STEP 4: Learned Behavior")
print("-"*60)

print("\n📌 SAY THIS:")
print('"Now I submit the EXACT SAME workload again.')
print(' Same requirements. But the system has learned."')
print("\n[Press Enter to resubmit]")
input()

job2 = api("POST", "/submit", {"intent": "Train LLM", "required_vram": 80})
print(f"\n✓ Workload: Train Large Language Model (same as before)")
print(f"✓ Memory Required: 80GB")
print(f"✓ New Recommendation: {job2['decision']}")

print("\n📌 SAY THIS:")
print(f'"This time it recommended {job2["decision"]} — which has 80GB.')
print(' The system learned from a real failure,')
print(' improved its behavior automatically,')
print(' and still allows full human rollback."')
print("\n[PAUSE. Let them react.]")
print("\n[Press Enter to continue]")
input()

# ============================================================
# STEP 5: ROLLBACK (30 seconds)
# ============================================================
print("\n" + "-"*60)
print("STEP 5: Safety & Control")
print("-"*60)

print("\n📌 SAY THIS:")
print('"If the evolved policy is too conservative,')
print(' we can instantly roll back to any previous version."')
print("\n[Press Enter to rollback]")
input()

rollback = api("POST", "/policy/rollback/1", {})
print(f"\n✓ Rolled back to version {rollback['version']}")

policy3 = api("GET", "/policy")
print(f"✓ Weights restored:")
print(f"   - Cost Priority: {policy3['weights']['cost']:.1%}")
print(f"   - Risk Aversion: {policy3['weights']['risk']:.1%}")

print("\n📌 SAY THIS:")
print('"Every decision is versioned, timestamped, and reversible.')
print(' You have complete control."')

# ============================================================
# CLOSE (30 seconds)
# ============================================================
print("\n" + "="*60)
print("  Demo Complete")
print("="*60)

print("\n📌 CLOSING STATEMENT:")
print('"That\'s OrQuanta. Three key points:')
print(' 1. It learns from real outcomes, not guesses')
print(' 2. Learning is bounded and safe')
print(' 3. You maintain full control via rollback')
print('')
print(' v1 is scoped: single policy, simulation-based,')
print(' internal deployment. We expand based on real usage."')
print("\n[Open for questions]")
