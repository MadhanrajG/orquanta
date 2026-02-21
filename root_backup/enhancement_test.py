import requests
import time
import sys

BASE_URL = "http://localhost:8000/api/v1"

def print_step(msg):
    print(f"\n🔹 {msg}")

def fail(msg):
    print(f"❌ {msg}")
    sys.exit(1)

# 1. Register
print_step("Registering User...")
reg_data = {
    "email": "ai_expert@orquanta.com",
    "password": "securepassword123",
    "full_name": "AI Expert",
    "company": "DeepMind"
}
try:
    resp = requests.post(f"{BASE_URL}/auth/register", json=reg_data)
    if resp.status_code != 200:
        # Maybe user exists from check prev run, try login
        print("User exists, logging in...")
        lresp = requests.post(f"{BASE_URL}/auth/login", json={"email": reg_data["email"], "password": reg_data["password"]})
        api_key = lresp.json()["api_key"]
    else:
        api_key = resp.json()["api_key"]
except Exception as e:
    fail(f"Auth failed: {e}")

print(f"✅ Authenticated. Key: {api_key[:10]}...")
headers = {"Authorization": f"Bearer {api_key}"}

# 2. AI Recommendation
print_step("Asking AI Advisor for recommendation...")
workload = {
    "workload_description": "Fine-tuning Llama 3 70B model on medical dataset",
    "priority": "performance"
}
rec_resp = requests.post(f"{BASE_URL}/ai/recommend", json=workload)
rec_data = rec_resp.json()
print(f"🧠 Advisor Verification:\n   Input: {workload['workload_description']}\n   Recommendation: {rec_data['gpu_count']}x {rec_data['recommended_gpu']}")
print(f"   Reasoning: {rec_data['reasoning']}")

if rec_data['recommended_gpu'] not in ["A100", "H100"]:
    fail("AI Advisor gave poor recommendation for LLM training")

# 3. Create Job based on recommendation
print_step("Launching Job based on AI Recommendation...")
job_req = {
    "gpu_type": rec_data['recommended_gpu'],
    "gpu_count": 4, # Just testing creation
    "docker_image": "pytorch/pytorch:2.0-cuda11.7-cudnn8-runtime"
}
job_resp = requests.post(f"{BASE_URL}/jobs", json=job_req, headers=headers)
job_id = job_resp.json()["job_id"]
print(f"✅ Job Launched: {job_id}")

# 4. Watch for Simulation Logs
print_step("Waiting for Simulation Engine to process job...")
for i in range(10):
    time.sleep(2)
    logs_resp = requests.get(f"{BASE_URL}/jobs/{job_id}/logs", headers=headers)
    logs = logs_resp.json()["logs"]
    print(f"   [{i*2}s] Logs: {len(logs)} entries")
    
    # Check if we have more than just initialization logs
    if len(logs) > 1:
        print(f"   New Log Entry: {logs[-1]}")
        print("✅ Simulation Engine is Active!")
        break
else:
    fail("Simulation engine fail to generate logs within 20s")

print("\n🎉 ENHANCEMENT VALIDATION SUCCESSFUL!")
