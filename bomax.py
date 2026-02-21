"""
OrQuanta v3.2 - Self-Evolving AI Organism
Features: Closed-Loop Learning, Proactive Reasoning, Real-Time Evolution.
"""

import asyncio
import logging
import json
import os
import secrets
import random
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OrQuanta-Cortex")

DATA_FILE = "orquanta_data.json"

# ============================================================================
# THE HIPPOCAMPUS (Long-Term Memory)
# ============================================================================

users_db = {}
jobs_db = {}

# Knowledge Graph: Workload Signature -> Performance Metadata
knowledge_base = {
    # Initial seeds
    "llm_training": {"avg_duration": 7200, "success_rate": 0.95, "samples": 10},
    "inference": {"avg_duration": 3600, "success_rate": 0.99, "samples": 50},
    "unknown": {"avg_duration": 1800, "success_rate": 0.50, "samples": 1}
}

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try: await connection.send_json(message)
            except: pass

manager = ConnectionManager()

def load_data():
    global users_db, jobs_db, knowledge_base
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                users_db = data.get("users", {})
                jobs_db = data.get("jobs", {})
                knowledge_base.update(data.get("knowledge", {}))
                logger.info(f"🧠 Cortex Loaded. {len(knowledge_base)} synaptic pathways active.")
        except Exception: pass

def save_data():
    try:
        def default(o): return o.isoformat() if isinstance(o, datetime) else o
        with open(DATA_FILE, "w") as f:
            json.dump({"users": users_db, "jobs": jobs_db, "knowledge": knowledge_base}, f, default=default)
    except Exception: pass

# ============================================================================
# THE LEARNING ENGINE
# ============================================================================

async def learn_from_outcome(workload_type: str, duration: int, success: bool):
    """Bayesian update of the knowledge base based on experience"""
    node = knowledge_base.get(workload_type, {"avg_duration": 0, "success_rate": 0.5, "samples": 0})
    
    # Weight new knowledge (simple moving average for demo)
    n = node["samples"]
    new_n = n + 1
    
    # Update Duration
    node["avg_duration"] = ((node["avg_duration"] * n) + duration) / new_n
    
    # Update Success Rate (Alpha smoothing)
    learning_rate = 0.1
    outcome_val = 1.0 if success else 0.0
    node["success_rate"] = (node["success_rate"] * (1 - learning_rate)) + (outcome_val * learning_rate)
    
    node["samples"] = new_n
    knowledge_base[workload_type] = node
    
    # Broadcast Evolution Event
    msg = f"✨ Brain Evolved [{workload_type}]: Confidence now {(node['success_rate']*100):.1f}% over {new_n} samples."
    await manager.broadcast({"type": "LOG", "payload": msg})
    logger.info(msg)
    save_data()

# ============================================================================
# MODELS
# ============================================================================

class AIRecommendationRequest(BaseModel):
    workload_description: str

class AIRecommendation(BaseModel):
    recommended_gpu: str
    gpu_count: int
    reasoning: str
    confidence_score: float

class GPURequest(BaseModel):
    gpu_type: str
    gpu_count: int

# ============================================================================
# AUTONOMOUS LOOP
# ============================================================================

async def autonomous_loop():
    logger.info("⚡ Neural Loop Active")
    while True:
        try:
            active_jobs = [j for j in jobs_db.values() if j["status"] in ["pending", "running"]]
            
            for job in active_jobs:
                # START
                if job["status"] == "pending":
                    if random.random() > 0.1:
                        job["status"] = "running"
                        job["started_at"] = datetime.now()
                        msg = f"🚀 Job {job['job_id'][:8]} Started on {job['gpu_count']}x {job['gpu_type']}"
                        job["logs"].append(msg)
                        await manager.broadcast({"type": "LOG", "payload": msg})

                # RUN
                elif job["status"] == "running":
                    job.setdefault("progress", 0)
                    job["progress"] += random.randint(2, 5) # Faster sim
                    
                    # Self-Healing Simulation
                    if random.random() < 0.02:
                        msg = "🛡️ Healer: Corrected micro-latency on Node-7."
                        job["logs"].append(msg)
                        await manager.broadcast({"type": "LOG", "payload": msg})

                    # FINISH
                    if job["progress"] >= 100:
                        job["status"] = "completed"
                        msg = f"✅ Job {job['job_id'][:8]} Completed."
                        job["logs"].append(msg)
                        await manager.broadcast({"type": "LOG", "payload": msg})
                        
                        # TRIGGER LEARNING
                        tag = "llm_training" if "H100" in job["gpu_type"] else "inference"
                        await learn_from_outcome(tag, random.randint(100, 500), True)

            # Telemetry Pulse
            avg_conf = sum(k['success_rate'] for k in knowledge_base.values()) / len(knowledge_base)
            telemetry = {
                "active_jobs": len(active_jobs),
                "gpu_utilization": int(len(active_jobs) * 12.5),
                "revenue_rate": len(active_jobs) * 4.50,
                "knowledge_nodes": len(knowledge_base),
                "brain_health": f"{(avg_conf*100):.1f}%",
                "jobs": [{
                    "job_id": j["job_id"], "status": j["status"], 
                    "gpu_type": j["gpu_type"], "gpu_count": j["gpu_count"],
                    "progress": j.get("progress", 0),
                    "last_log": j["logs"][-1] if j["logs"] else "..."
                } for j in active_jobs]
            }
            await manager.broadcast({"type": "HEARTBEAT", "payload": telemetry})

            await asyncio.sleep(1.5)
        except Exception as e:
            logger.error(e)
            await asyncio.sleep(1.5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_data()
    asyncio.create_task(autonomous_loop())
    yield
    save_data()

app = FastAPI(title="OrQuanta v3.2", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
async def ui(): return FileResponse("templates/index.html")

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/v1/ai/recommend", response_model=AIRecommendation)
async def brain_reason(req: AIRecommendationRequest):
    desc = req.workload_description.lower()
    
    # Proactive Reasoning Logic
    if "70b" in desc or "llama" in desc or "train" in desc:
        rec, count = "H100", 8
        tag = "llm_training"
        reason = "Detected LLM Training Intent. H100 provides 9x throughput vs A100."
    elif "inference" in desc:
        rec, count = "A100", 1
        tag = "inference"
        reason = "Deep Learning Inference optimized for A100."
    else:
        rec, count = "T4", 1
        tag = "unknown"
        reason = "General purpose workload."

    # Consult Memory
    memory = knowledge_base.get(tag, knowledge_base["unknown"])
    confidence = memory["success_rate"]
    
    return {
        "recommended_gpu": rec, "gpu_count": count,
        "reasoning": f"{reason} (Historical Confidence: {(confidence*100):.0f}%)",
        "confidence_score": confidence
    }

@app.post("/api/v1/jobs")
async def launch(req: GPURequest):
    jid = f"job-{secrets.token_hex(4)}"
    jobs_db[jid] = {
        "job_id": jid, "status": "pending", 
        "gpu_type": req.gpu_type, "gpu_count": req.gpu_count, 
        "logs": [], "created_at": datetime.now().isoformat()
    }
    await manager.broadcast({"type": "LOG", "payload": f"📥 Deployment Accepted: {jid}"})
    return jobs_db[jid]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
