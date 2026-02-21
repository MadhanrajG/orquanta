import asyncio
import logging
import json
import secrets
import os
import math
import threading
from typing import List, Dict, Optional
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("orquanta")

# --- CONSTANTS ---
POLICY_FILE = "orquanta_policy_prod.json"
MIN_WEIGHT = 0.05
MAX_WEIGHT = 0.95
API_KEY = os.getenv("ORQUANTA_API_KEY", "dev-key-change-in-production")

# --- INFRASTRUCTURE PHYSICS ---
class HardwareSpec:
    def __init__(self, name, vram_gb, cost, reliability):
        self.name, self.vram_gb, self.cost, self.reliability = name, vram_gb, cost, reliability

HARDWARE = {
    "T4": HardwareSpec("T4", 16, 0.4, 0.95),
    "A10G": HardwareSpec("A10G", 24, 1.2, 0.99),
    "H100": HardwareSpec("H100", 80, 5.0, 0.9999)
}

# --- SOVEREIGN POLICY ENGINE ---
class SovereignPolicy:
    def __init__(self):
        self.version = 1
        self.weights = {"cost": 0.8, "perf": 0.1, "risk": 0.1}
        self.history = []
        self.lock = threading.Lock()  # Thread-safe mutations
        self.load()

    def enforce_bounds(self):
        """Guarantee all weights are in [MIN_WEIGHT, MAX_WEIGHT] and sum to 1.0"""
        keys = list(self.weights.keys())
        
        # Step 1: Clamp all values to valid range
        for k in keys:
            self.weights[k] = max(MIN_WEIGHT, min(MAX_WEIGHT, self.weights[k]))
        
        # Step 2: Calculate how much we need to adjust to sum to 1.0
        total = sum(self.weights.values())
        if abs(total - 1.0) < 0.001:
            return  # Already valid
        
        # Step 3: Distribute the difference proportionally among unclamped weights
        diff = 1.0 - total
        
        # Find weights that have room to adjust
        adjustable = []
        for k in keys:
            if diff > 0 and self.weights[k] < MAX_WEIGHT:
                adjustable.append(k)
            elif diff < 0 and self.weights[k] > MIN_WEIGHT:
                adjustable.append(k)
        
        if adjustable:
            adjustment = diff / len(adjustable)
            for k in adjustable:
                self.weights[k] += adjustment
                self.weights[k] = max(MIN_WEIGHT, min(MAX_WEIGHT, self.weights[k]))
        
        # Final normalization pass
        total = sum(self.weights.values())
        for k in keys:
            self.weights[k] /= total


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
        with self.lock:  # Thread-safe mutation
            prev = self.weights.copy()
            
            # Apply Impact
            for k, impact in impact_matrix.items():
                if k in self.weights:
                    self.weights[k] += impact
            
            self.enforce_bounds()
            
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
            logger.info(f"Policy mutated to v{self.version}: {cause}")
            return snapshot

    def rollback(self, target_version: int):
        target = next((h for h in self.history if h["v"] == target_version), None)
        # Baseline fallback
        if not target and target_version == 1:
            target = {"weights": {"cost": 0.8, "perf": 0.1, "risk": 0.1}}

        if target:
            self.weights = target["weights"].copy()
            self.version = target_version
            self.save()
            return True
        return False

    def decay(self):
        BASELINE = {"cost": 0.5, "perf": 0.3, "risk": 0.2}
        DECAY_RATE = 0.05
        changed = False
        for k in self.weights:
            diff = BASELINE[k] - self.weights[k]
            if abs(diff) > 0.01:
                self.weights[k] += (diff * DECAY_RATE)
                changed = True
        
        if changed:
            self.enforce_bounds()
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
                logger.info(f"Policy loaded from disk: v{self.version}")
            except Exception as e:
                logger.warning(f"Policy load failed, using defaults: {e}")

policy = SovereignPolicy()
jobs_db = {}

# --- API ---
app = FastAPI(title="OrQuanta Production Kernel")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

from pydantic import Field

class JobReq(BaseModel):
    intent: str = Field(..., min_length=1, max_length=1000)
    required_vram: int = Field(..., ge=1, le=10000)  # 1-10000 GB

# --- AUTHENTICATION ---
def verify_api_key(x_api_key: str = Header(None)):
    """Simple API key authentication. Exclude /health endpoint."""
    if x_api_key != API_KEY:
        logger.warning(f"Unauthorized access attempt with key: {x_api_key or 'None'}")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

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
            {"risk": 0.8, "perf": 0.4, "cost": -0.8} # Aggressive penalty
        )
        job["mutation"] = evt
    else:
        job["status"] = "completed"

@app.post("/api/v1/submit")
async def submit(r: JobReq, _: str = Header(None, alias="X-API-Key", include_in_schema=False)):
    verify_api_key(_)
    eval_res = policy.evaluate(r.required_vram)
    jid = f"JOB-{secrets.token_hex(2).upper()}"
    jobs_db[jid] = {
        "id": jid, "status": "pending", "decision": eval_res["decision"],
        "req_vram": r.required_vram, "policy_v": policy.version
    }
    asyncio.create_task(physics_loop(jid))
    return {"id": jid, "decision": eval_res["decision"]}


@app.get("/health")
def health(): return {"status": "ok", "version": policy.version}

@app.get("/api/v1/policy")
def get_policy(_: str = Header(None, alias="X-API-Key")):
    verify_api_key(_)
    return {"version": policy.version, "weights": policy.weights}

@app.post("/api/v1/policy/rollback/{v}")
def rollback(v: int, _: str = Header(None, alias="X-API-Key")):
    verify_api_key(_)
    if policy.rollback(v): return {"status": "rolled_back", "version": policy.version}
    raise HTTPException(404, "Target version not found")

@app.post("/api/v1/reset")
def reset(payload: Dict = {}, _: str = Header(None, alias="X-API-Key")):
    verify_api_key(_)
    global policy, jobs_db
    if os.path.exists(POLICY_FILE): os.remove(POLICY_FILE)
    policy = SovereignPolicy()
    jobs_db.clear()
    return {"status": "reset"}

if __name__ == "__main__":
    import uvicorn
    print("CORE: Production Kernel Active.")
    uvicorn.run(app, host="0.0.0.0", port=8000)
