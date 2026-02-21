import asyncio
import logging
import json
import secrets
import os
import math
from contextlib import asynccontextmanager
from typing import List, Dict, Optional
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- CONSTANTS ---
POLICY_FILE = "orquanta_policy_v8.json"

# --- INFRASTRUCTURE PHYSICS ---
class HardwareSpec:
    def __init__(self, name, vram_gb, cost, reliability):
        self.name, self.vram_gb, self.cost, self.reliability = name, vram_gb, cost, reliability

HARDWARE = {
    "T4": HardwareSpec("T4", 16, 0.4, 0.95),
    "A10G": HardwareSpec("A10G", 24, 1.2, 0.99),
    "H100": HardwareSpec("H100", 80, 5.0, 0.9999)
}

# --- SOVEREIGN POLICY WITH SAFETY ---
class ProductionPolicy:
    def __init__(self):
        self.version = 1
        self.weights = {"cost": 0.8, "perf": 0.1, "risk": 0.1} # Default: Cost-focused
        self.history = [] # List of snapshots
        self.load()

    def clamp(self, val):
        return max(0.05, min(0.95, val))

    def normalize(self):
        total = sum(self.weights.values())
        for k in self.weights: 
            self.weights[k] = self.clamp(self.weights[k] / total)
        # Re-normalize after clamp
        total = sum(self.weights.values())
        for k in self.weights: self.weights[k] /= total

    def evaluate(self, req_vram: int) -> Dict:
        scores = {}
        for name, hw in HARDWARE.items():
            n_cost = 1.0 - min(1.0, hw.cost / 6.0)
            n_perf = min(1.0, hw.vram_gb / 100.0)
            n_risk = hw.reliability
            
            score = (self.weights["cost"] * n_cost) + \
                    (self.weights["perf"] * n_perf) + \
                    (self.weights["risk"] * n_risk)
            scores[name] = score

        best_hw = max(scores, key=scores.get)
        return {"decision": best_hw, "scores": scores, "policy_v": self.version}

    def mutate(self, cause: str, impact_matrix: Dict[str, float]):
        prev = self.weights.copy()
        
        # Apply Impact
        for k, impact in impact_matrix.items():
            if k in self.weights:
                self.weights[k] += impact
        
        self.normalize() # Enforce Bounds & Sum=1.0
        
        self.version += 1
        snapshot = {
            "v": self.version,
            "ts": datetime.now().isoformat(),
            "cause": cause,
            "weights": self.weights.copy(),
            "delta": {k: self.weights[k] - prev[k] for k in self.weights}
        }
        self.history.append(snapshot)
        self.save()
        return snapshot

    def rollback(self, target_version: int):
        target = next((h for h in self.history if h["v"] == target_version), None)
        if not target and target_version == 1:
             # Reset to baseline
             target = {"weights": {"cost": 0.8, "perf": 0.1, "risk": 0.1}}
        
        if target:
            self.weights = target["weights"].copy()
            self.version = target_version
            self.save()
            return True
        return False

    def decay(self):
        # Slowly drift back to baseline to prevent overfitting
        BASELINE = {"cost": 0.5, "perf": 0.3, "risk": 0.2}
        DECAY_RATE = 0.05
        
        changed = False
        for k in self.weights:
            diff = BASELINE[k] - self.weights[k]
            if abs(diff) > 0.01:
                self.weights[k] += (diff * DECAY_RATE)
                changed = True
        
        if changed:
            self.normalize()
            self.save()

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

policy = ProductionPolicy()
jobs_db = {}

# --- API ---
app = FastAPI(title="OrQuanta v3.7 Production")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class JobReq(BaseModel):
    intent: str
    required_vram: int

async def physics_loop(jid):
    await asyncio.sleep(0.5)
    job = jobs_db[jid]
    hw = HARDWARE[job["decision"]]
    
    if hw.vram_gb < job["req_vram"]:
        job["status"] = "failed"
        job["error"] = "OOM_ERROR"
        # MUTATE: Drastic Risk Increase
        evt = policy.mutate(
            f"OOM Failure on {jid}", 
            {"risk": 0.6, "perf": 0.4, "cost": -0.7} # Aggressive penalty
        )
        job["mutation"] = evt
    else:
        job["status"] = "completed"

@app.post("/api/v1/submit")
async def submit(r: JobReq):
    eval_res = policy.evaluate(r.required_vram)
    jid = f"JOB-{secrets.token_hex(2).upper()}"
    jobs_db[jid] = {
        "id": jid, "status": "pending", "decision": eval_res["decision"],
        "req_vram": r.required_vram, "policy_v": policy.version
    }
    asyncio.create_task(physics_loop(jid))
    return {"id": jid, "decision": eval_res["decision"]}

@app.get("/api/v1/policy")
def get_policy():
    return {"version": policy.version, "weights": policy.weights}

@app.post("/api/v1/policy/rollback/{v}")
def rollback(v: int):
    success = policy.rollback(v)
    if not success: raise HTTPException(404, "Version not found")
    return {"status": "rolled_back", "current_version": policy.version}

@app.post("/api/v1/policy/decay")
def maintenance():
    policy.decay()
    return {"status": "decayed", "weights": policy.weights}

@app.get("/api/v1/jobs/{jid}")
def get_job(jid: str):
    return jobs_db.get(jid, {"error": "not found"})

@app.post("/api/v1/reset")
def reset(payload: Dict = {}):
    global policy, jobs_db
    if os.path.exists(POLICY_FILE): os.remove(POLICY_FILE)
    policy = ProductionPolicy()
    jobs_db = {}
    return {"status": "reset"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
