import asyncio
import logging
import json
import secrets
import os
from contextlib import asynccontextmanager
from typing import List, Dict, Optional
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# --- CONSTANTS ---
POLICY_FILE = "orquanta_policy.json"

# --- INFRASTRUCTURE PHYSICS ---
class HardwareSpec:
    def __init__(self, name, vram_gb, cost, reliability):
        self.name, self.vram_gb, self.cost, self.reliability = name, vram_gb, cost, reliability

HARDWARE = {
    "T4": HardwareSpec("T4", 16, 0.4, 0.95),
    "A10G": HardwareSpec("A10G", 24, 1.2, 0.99),
    "H100": HardwareSpec("H100", 80, 5.0, 0.9999)
}

# --- SOVEREIGN POLICY ---
class SovereignPolicy:
    def __init__(self):
        self.version = 1
        self.weights = {"cost": 0.9, "perf": 0.05, "risk": 0.05} # Naive: Very Cheap
        self.history = []
        self.load()

    def evaluate(self, req_vram: int) -> Dict:
        scores = {}
        for name, hw in HARDWARE.items():
            # Normalized components (0.0 - 1.0)
            n_cost = 1.0 - min(1.0, hw.cost / 6.0) # Lower cost is better
            n_perf = min(1.0, hw.vram_gb / 80.0)
            n_risk = hw.reliability
            
            score = (self.weights["cost"] * n_cost) + \
                    (self.weights["perf"] * n_perf) + \
                    (self.weights["risk"] * n_risk)
            scores[name] = score

        best_hw = max(scores, key=scores.get)
        return {"decision": best_hw, "scores": scores, "policy_v": self.version}

    def mutate(self, cause: str):
        prev = self.weights.copy()
        
        # REACTIVE MUTATION LOGIC
        if "OOM" in cause:
            # Drastic shift: OOM means 'Cheaping out' is fatal.
            self.weights["risk"] = min(0.95, self.weights["risk"] + 0.5)
            self.weights["perf"] = min(0.95, self.weights["perf"] + 0.5)
            self.weights["cost"] = 0.05 # Nuke cost preference
        
        # Re-normalize
        total = sum(self.weights.values())
        for k in self.weights: self.weights[k] /= total
        
        self.version += 1
        event = {
            "v": self.version,
            "ts": datetime.now().isoformat(),
            "cause": cause,
            "delta": {k: self.weights[k] - prev[k] for k in self.weights},
            "new_weights": self.weights.copy()
        }
        self.history.append(event)
        self.save()
        return event

    def save(self):
        with open(POLICY_FILE, "w") as f:
            json.dump({"v": self.version, "w": self.weights, "h": self.history}, f, indent=2)

    def load(self):
        if os.path.exists(POLICY_FILE):
            try:
                with open(POLICY_FILE, "r") as f:
                    d = json.load(f)
                    self.version = d["v"]
                    self.weights = d["w"]
                    self.history = d["h"]
            except: pass

policy = SovereignPolicy()
jobs_db = {}

# --- API ---
app = FastAPI(title="OrQuanta v3.6 Hardened")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class JobReq(BaseModel):
    intent: str
    required_vram: int

async def run_physics_sim(jid):
    await asyncio.sleep(1.0) # Processing time
    job = jobs_db[jid]
    
    # PHYSICS CHECK
    hw = HARDWARE[job["decision"]]
    if hw.vram_gb < job["req_vram"]:
        # DETERMINISTIC FAILURE
        job["status"] = "failed"
        job["error"] = "OOM_ERROR"
        
        # TRIGGER MUTATION
        evt = policy.mutate(f"OOM on {jid} (Req: {job['req_vram']}GB, Has: {hw.vram_gb}GB)")
        job["mutation_event"] = evt
    else:
        job["status"] = "completed"

@app.post("/api/v1/submit")
async def submit(r: JobReq):
    # 1. GOVERNANCE
    eval_result = policy.evaluate(r.required_vram)
    
    # 2. DISPATCH
    jid = f"JOB-{secrets.token_hex(2).upper()}"
    jobs_db[jid] = {
        "id": jid,
        "req_vram": r.required_vram,
        "decision": eval_result["decision"],
        "policy_snapshot": policy.weights.copy(),
        "status": "pending"
    }
    
    # 3. BACKGROUND PHYSICS
    asyncio.create_task(run_physics_sim(jid))
    
    return {"id": jid, "governance": eval_result}

@app.get("/api/v1/policy")
def get_policy():
    return {"version": policy.version, "weights": policy.weights, "history": policy.history}

@app.get("/api/v1/jobs/{jid}")
def get_job(jid: str):
    return jobs_db.get(jid, {"error": "not found"})

@app.post("/api/v1/reset")
def reset(payload: Dict = {}):
    global policy
    if os.path.exists(POLICY_FILE): os.remove(POLICY_FILE)
    policy = SovereignPolicy()
    jobs_db.clear()
    return {"status": "tabula_rasa"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
