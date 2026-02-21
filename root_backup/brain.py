"""
OrQuanta v3.2 - Self-Evolving AI Organism (Renamed to brain.py for cache bust)
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Brain")

DATA_FILE = "orquanta_data.json"
knowledge_base = {
    "llm_training": {"avg_duration": 7200, "success_rate": 0.95, "samples": 10},
    "inference": {"avg_duration": 3600, "success_rate": 0.99, "samples": 50},
    "unknown": {"avg_duration": 1800, "success_rate": 0.50, "samples": 1}
}
users_db = {}
jobs_db = {}

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
                d = json.load(f)
                users_db = d.get("users", {})
                jobs_db = d.get("jobs", {})
                knowledge_base.update(d.get("knowledge", {}))
        except: pass

def save_data():
    try:
        def default(o): return o.isoformat() if isinstance(o, datetime) else o
        with open(DATA_FILE, "w") as f:
            json.dump({"users": users_db, "jobs": jobs_db, "knowledge": knowledge_base}, f, default=default)
    except: pass

async def learn_from_outcome(tag, duration, success):
    node = knowledge_base.get(tag, {"avg_duration": 0, "success_rate": 0.5, "samples": 0})
    n = node["samples"] + 1
    node["avg_duration"] = ((node["avg_duration"] * node["samples"]) + duration) / n
    lr = 0.1
    node["success_rate"] = (node["success_rate"] * (1 - lr)) + ((1.0 if success else 0.0) * lr)
    node["samples"] = n
    knowledge_base[tag] = node
    msg = f"✨ Brain Evolved [{tag}]: Confidence {(node['success_rate']*100):.1f}% (n={n})"
    await manager.broadcast({"type": "LOG", "payload": msg})
    save_data()

class GPURequest(BaseModel):
    gpu_type: str
    gpu_count: int

class AIRecommendationRequest(BaseModel):
    workload_description: str

async def autonomous_loop():
    while True:
        try:
            active = [j for j in jobs_db.values() if j["status"] in ["pending", "running"]]
            for job in active:
                if job["status"] == "pending":
                    if random.random() > 0.1:
                        job["status"] = "running"
                        job["started_at"] = datetime.now()
                        msg = f"🚀 Job {job['job_id'][:4]} Started"
                        job["logs"].append(msg)
                        await manager.broadcast({"type": "LOG", "payload": msg})
                elif job["status"] == "running":
                    job.setdefault("progress", 0)
                    job["progress"] += random.randint(5, 10)
                    if job["progress"] >= 100:
                        job["status"] = "completed"
                        mean_conf = int(sum(k['success_rate'] for k in knowledge_base.values())/len(knowledge_base)*100)
                        msg = f"✅ Job {job['job_id'][:4]} Complete. Brain Health: {mean_conf}%" 
                        job["logs"].append(msg)
                        await manager.broadcast({"type": "LOG", "payload": msg})
                        tag = "llm_training" if "H100" in job["gpu_type"] else "inference"
                        await learn_from_outcome(tag, random.randint(100,200), True)
            
            if active: save_data()
            
            tel = {
                "active_jobs": len(active),
                "gpu_utilization": len(active)*10,
                "revenue_rate": len(active)*4.0,
                "knowledge_nodes": len(knowledge_base),
                "jobs": [{"job_id": j["job_id"], "status": j["status"], "gpu_type": j["gpu_type"], "gpu_count": j["gpu_count"], "progress": j.get("progress",0), "last_log": j["logs"][-1] if j["logs"] else ""} for j in active]
            }
            await manager.broadcast({"type": "HEARTBEAT", "payload": tel})
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(e)
            await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_data()
    asyncio.create_task(autonomous_loop())
    yield
    save_data()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def ui(): return FileResponse("templates/index.html")

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/v1/ai/recommend")
def recommend(req: AIRecommendationRequest):
    desc = req.workload_description.lower()
    if "train" in desc: rec, cnt, tag = "H100", 8, "llm_training"
    else: rec, cnt, tag = "A100", 1, "inference"
    conf = knowledge_base.get(tag, {}).get("success_rate", 0.5)
    return {"recommended_gpu": rec, "gpu_count": cnt, "reasoning": f"Evolved Intent Analysis (Conf: {conf*100:.0f}%)", "confidence_score": conf}

@app.post("/api/v1/jobs")
async def launch(req: GPURequest):
    jid = f"job-{secrets.token_hex(2)}"
    jobs_db[jid] = {"job_id": jid, "status": "pending", "gpu_type": req.gpu_type, "gpu_count": req.gpu_count, "logs": [], "created_at": datetime.now().isoformat()}
    await manager.broadcast({"type": "LOG", "payload": f"📥 Accepted: {jid}"})
    return jobs_db[jid]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
