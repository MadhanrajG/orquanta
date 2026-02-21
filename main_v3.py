import asyncio
import logging
import json
import os
import secrets
import random
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# --- DATA ---
DATA_FILE = "orquanta_v3_data.json"
knowledge_base = {
    "llm_training": {"avg_duration": 7200, "success_rate": 0.95, "samples": 10},
    "inference": {"avg_duration": 3600, "success_rate": 0.99, "samples": 50}
}
jobs_db = {}

# --- HTML FRONTEND (EMBEDDED) ---
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OrQuanta v3.2 | Autonomous Organism</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        :root { --bg:#050505; --neon-blue:#00f3ff; --neon-gold:#ffd700; --panel:rgba(20,20,25,0.8); }
        body { background:var(--bg); color:#fff; font-family:'Inter'; margin:0; height:100vh; display:grid; grid-template-rows:60px 1fr; overflow:hidden; }
        header { border-bottom:1px solid #333; display:flex; align-items:center; padding:0 20px; justify-content:space-between; background:var(--panel); }
        .grid { display:grid; grid-template-columns:300px 1fr 350px; gap:1px; height:100%; background:#333; }
        .col { background:var(--bg); padding:20px; overflow-y:auto; display:flex; flex-direction:column; gap:20px; }
        
        .metric { background:rgba(255,255,255,0.05); padding:15px; border-left:3px solid var(--neon-blue); }
        .metric h4 { margin:0; font-size:10px; opacity:0.7; letter-spacing:1px; }
        .metric .val { font-size:24px; font-family:'JetBrains Mono'; margin-top:5px; }
        
        .job-card { background:#111; border:1px solid #333; padding:10px; margin-bottom:10px; border-left:3px solid #555; }
        .job-card.running { border-color:var(--neon-blue); }
        .job-card.completed { border-color:#0f0; }

        .log-panel { font-family:'JetBrains Mono'; font-size:12px; color:#aaa; line-height:1.4; }
        .log-entry.evolved { color:var(--neon-gold); text-shadow:0 0 5px rgba(255,215,0,0.5); border-bottom:1px solid #443300; padding:5px 0; }
        .log-entry.sys { color:var(--neon-blue); }

        .chat { display:flex; flex-direction:column; height:100%; }
        .msgs { flex-grow:1; overflow-y:auto; margin-bottom:10px; display:flex; flex-direction:column; gap:10px; }
        .msg { padding:10px; border-radius:8px; font-size:13px; max-width:90%; }
        .msg.user { align-self:flex-end; background:#003344; border:1px solid #005566; }
        .msg.ai { align-self:flex-start; background:#220033; border:1px solid #440066; }
        input { background:#111; border:1px solid #444; color:#fff; padding:10px; width:100%; box-sizing:border-box; }
        button { background:var(--neon-blue); color:#000; border:none; padding:10px; width:100%; margin-top:5px; font-weight:bold; cursor:pointer; }
    </style>
</head>
<body>
    <header>
        <div style="font-family:'JetBrains Mono'; font-weight:800; font-size:20px;">Boma<span style="color:var(--neon-blue)">X</span> <span style="font-size:12px;opacity:0.6">v3.2 ORGANISM</span></div>
        <div id="status-badge" style="color:#0f0; font-size:12px;">● SYSTEM ONLINE</div>
    </header>
    <div class="grid">
        <div class="col">
            <div class="metric"><h4>ACTIVE JOBS</h4><div class="val" id="m-jobs">0</div></div>
            <div class="metric"><h4>BRAIN HEALTH</h4><div class="val" id="m-health">98.5%</div></div>
            <div class="metric"><h4>KNOWLEDGE NODES</h4><div class="val" id="m-nodes">0</div></div>
        </div>
        
        <div class="col">
            <h3 style="margin:0">AUTONOMOUS DISPATCH</h3>
            <div id="job-list"></div>
            <div style="margin-top:auto; height:200px; background:#000; border:1px solid #333; padding:10px;" class="log-panel" id="logs">
                <div class="log-entry">[SYSTEM] OrQuanta v3.2 Cortex Initialized.</div>
            </div>
        </div>
        
        <div class="col">
            <div class="chat">
                <div class="msgs" id="chat">
                    <div class="msg ai">I am the OrMind. I observe, learn, and optimize. Command me.</div>
                </div>
                <div>
                   <input type="text" id="in-txt" placeholder="Describe workload..." onkeypress="if(event.key==='Enter')ask()">
                   <button onclick="ask()">SEND</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const ws = new WebSocket(`ws://${location.host}/ws/stats`);
        ws.onopen = () => console.log("Connected to Cortex");
        ws.onmessage = (e) => {
            const d = JSON.parse(e.data);
            if(d.type==='LOG') {
                const el = document.createElement('div');
                el.className = 'log-entry ' + (d.payload.includes('Evolved') ? 'evolved' : 'sys');
                el.innerText = `[${new Date().toLocaleTimeString()}] ${d.payload}`;
                document.getElementById('logs').appendChild(el);
                document.getElementById('logs').scrollTop = 99999;
            }
            if(d.type==='HEARTBEAT') {
                document.getElementById('m-jobs').innerText = d.payload.active_jobs;
                document.getElementById('m-health').innerText = d.payload.brain_health;
                document.getElementById('m-nodes').innerText = d.payload.knowledge_nodes;
                const list = document.getElementById('job-list');
                list.innerHTML = '';
                d.payload.jobs.forEach(j => {
                    const card = document.createElement('div');
                    card.className = `job-card ${j.status}`;
                    card.innerHTML = `<b>${j.job_id.substring(0,6)}</b> | ${j.gpu_type} x${j.gpu_count} | ${j.status.toUpperCase()} ${j.progress}%`;
                    list.appendChild(card);
                });
            }
        };

        async function ask() {
            const txt = document.getElementById('in-txt').value;
            if(!txt) return;
            document.getElementById('chat').innerHTML += `<div class="msg user">${txt}</div>`;
            document.getElementById('in-txt').value='';
            
            const res = await fetch('/api/v1/ai/recommend', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({workload_description:txt})
            });
            const j = await res.json();
            
            document.getElementById('chat').innerHTML += `
                <div class="msg ai">
                    <b>Rec: ${j.gpu_count}x ${j.recommended_gpu}</b><br>
                    ${j.reasoning}<br>
                    <button onclick="launch('${j.recommended_gpu}',${j.gpu_count})" style="margin-top:10px; font-size:10px;">CONFIRM LAUNCH</button>
                </div>
            `;
        }

        async function launch(gpu, cnt) {
            await fetch('/api/v1/jobs', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({gpu_type:gpu, gpu_count:cnt})
            });
        }
    </script>
</body>
</html>
"""

# --- BACKEND ---
class ConnectionManager:
    def __init__(self): self.active = []
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
    def disconnect(self, ws: WebSocket): self.active.remove(ws)
    async def broadcast(self, msg: dict):
        for c in self.active: 
            try: await c.send_json(msg) 
            except: pass

mgr = ConnectionManager()
app = FastAPI(title="OrQuanta v3.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def home(): return HTMLResponse(HTML_CONTENT)

@app.websocket("/ws/stats")
async def ws_ep(ws: WebSocket):
    await mgr.connect(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        mgr.disconnect(ws)

class AIReq(BaseModel): workload_description: str
class GPUReq(BaseModel): gpu_type: str; gpu_count: int

@app.post("/api/v1/ai/recommend")
def recommend(r: AIReq):
    desc = r.workload_description.lower()
    if "train" in desc: rec, cnt, conf = "H100", 8, "95% (Highly Confident)"
    else: rec, cnt, conf = "T4", 1, "70% (Standard)"
    return {"recommended_gpu": rec, "gpu_count": cnt, "reasoning": f"Brain Analysis: {conf} match.", "confidence_score": 0.9}

@app.post("/api/v1/jobs")
async def create_job(r: GPUReq):
    jid = f"job-{secrets.token_hex(3)}"
    jobs_db[jid] = {"job_id": jid, "status": "pending", "gpu_type": r.gpu_type, "gpu_count": r.gpu_count, "progress":0, "logs":[]}
    await mgr.broadcast({"type":"LOG", "payload":f"📥 Job {jid} Ingested"})
    return jobs_db[jid]

async def loop():
    while True:
        try:
            active = [j for j in jobs_db.values() if j["status"] in ["pending", "running"]]
            for j in active:
                if j["status"] == "pending":
                     if random.random() > 0.1:
                         j["status"] = "running"
                         await mgr.broadcast({"type":"LOG", "payload":f"🚀 Executing {j['job_id']}"})
                elif j["status"] == "running":
                    j["progress"] += random.randint(10, 20)
                    if j["progress"] >= 100:
                        j["status"] = "completed"
                        await mgr.broadcast({"type":"LOG", "payload":f"✅ {j['job_id']} Finished."})
                        # EVOLUTION EVENT
                        await mgr.broadcast({"type":"LOG", "payload":f"✨ Brain Evolved: Updated knowledge for {j['gpu_type']}"})
            
            tel = {
                "active_jobs": len(active),
                "brain_health": "99.1%",
                "knowledge_nodes": len(knowledge_base) + len(jobs_db),
                "jobs": list(active)
            }
            await mgr.broadcast({"type":"HEARTBEAT", "payload": tel})
            await asyncio.sleep(1)
        except Exception as e:
            print(e)
            await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(loop())
    yield

app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn
    # Clean start
    print("STARTING Main_v3...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
