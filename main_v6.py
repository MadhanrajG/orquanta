import asyncio
import logging
import json
import secrets
import random
import time
from contextlib import asynccontextmanager
from typing import List, Dict, Optional, Any
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# --- INFRASTRUCTURE PHYSICS ---
class HardwareSpec:
    def __init__(self, name, vram_gb, cost_per_hr, reliability):
        self.name = name
        self.vram_gb = vram_gb
        self.cost = cost_per_hr
        self.reliability = reliability # 0.0-1.0

HARDWARE = {
    "T4": HardwareSpec("T4", 16, 0.4, 0.95),
    "A10G": HardwareSpec("A10G", 24, 1.2, 0.99),
    "A100": HardwareSpec("A100", 40, 3.5, 0.999),
    "H100": HardwareSpec("H100", 80, 5.0, 0.9999)
}

# --- POLICY ENGINE ---
class CausalPolicy:
    def __init__(self):
        self.version = 1
        self.weights = {"cost": 0.8, "perf": 0.1, "risk": 0.1} # Initial: Cheap & Risky
        self.history = []
        self.regret_accumulated = 0.0

    def evaluate(self, intent_vRAM: int) -> str:
        # Select best hardware based on current weights
        best_hw = None
        best_score = -float('inf')
        
        for name, hw in HARDWARE.items():
            # Normalized metrics (0-1)
            norm_cost = 1.0 - min(1.0, hw.cost / 5.0) # Lower cost = Higher score
            norm_perf = min(1.0, hw.vram_gb / 80.0)   # More VRAM = Higher score
            norm_risk = hw.reliability                # Higher reliability = Higher score
            
            # Weighted Score
            score = (self.weights["cost"] * norm_cost) + \
                    (self.weights["perf"] * norm_perf) + \
                    (self.weights["risk"] * norm_risk)
            
            if score > best_score:
                best_score = score
                best_hw = name
                
        return best_hw

    def learn(self, cause: str, penalty: float):
        self.regret_accumulated += penalty
        
        # Log mutation point
        prev_weights = self.weights.copy()
        
        if "OOM" in cause or "Failure" in cause:
            # Shift towards Risk/Perf, away from Cost
            self.weights["risk"] = min(0.9, self.weights["risk"] + 0.3)
            self.weights["perf"] = min(0.9, self.weights["perf"] + 0.1)
            self.weights["cost"] = max(0.05, self.weights["cost"] - 0.4)
            
        elif "Budget" in cause:
            self.weights["cost"] = min(0.9, self.weights["cost"] + 0.2)
            self.weights["perf"] = max(0.1, self.weights["perf"] - 0.1)

        # Normalize
        total = sum(self.weights.values())
        for k in self.weights: self.weights[k] /= total
        
        self.version += 1
        self.history.append({
            "v": self.version,
            "ts": datetime.now().strftime("%H:%M:%S"),
            "cause": cause,
            "delta": {k: self.weights[k]-prev_weights[k] for k in self.weights},
            "new_weights": self.weights.copy()
        })
        return self.history[-1]

policy = CausalPolicy()

# --- BACKEND LOGIC ---
jobs_db = {}
event_log = []

class Intent(BaseModel):
    text: str
    required_vram: int = 24 # Simplified intent extraction

class Nexus:
    def __init__(self): self.socks = []
    async def broadcast(self, t, p):
        for s in self.socks: 
            try: await s.send_json({"type":t, "payload":p})
            except: pass
nexus = Nexus()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.websocket("/ws/core")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    nexus.socks.append(ws)
    # Sync State
    await ws.send_json({"type":"SYNC_POLICY", "payload": {"v":policy.version, "w":policy.weights, "h":policy.history}})
    await ws.send_json({"type":"SYNC_JOBS", "payload": list(jobs_db.values())})
    try:
        while True: await ws.receive_text()
    except: nexus.socks.remove(ws)

@app.post("/api/v1/submit")
async def submit_job(i: Intent):
    # 1. GOVERNANCE
    chosen_hw = policy.evaluate(i.required_vram)
    
    # 2. DISPATCH
    jid = f"JOB-{secrets.token_hex(2).upper()}"
    job = {
        "id": jid, 
        "intent": i.text, 
        "req_vram": i.required_vram, 
        "hw": chosen_hw, 
        "hw_vram": HARDWARE[chosen_hw].vram_gb,
        "status": "provisioning",
        "policy_v": policy.version
    }
    jobs_db[jid] = job
    
    await nexus.broadcast("SYNC_JOBS", list(jobs_db.values()))
    await nexus.broadcast("LOG", f"v{policy.version} Governance: Selected {chosen_hw} for '{i.text}' (W_COST={policy.weights['cost']:.2f})")
    
    # 3. ASYNC INFRASTRUCTURE SIMULATION
    asyncio.create_task(run_infra_sim(jid))
    
    return {"id": jid, "decision": chosen_hw}

async def run_infra_sim(jid):
    await asyncio.sleep(2) # Provisioning delay
    job = jobs_db[jid]
    
    # PHYSICS CHECK
    if job["hw_vram"] < job["req_vram"]:
        # DETERMINISTIC FAILURE: OOM
        job["status"] = "failed"
        job["error"] = "OOM_ERROR: Device VRAM insufficient"
        await nexus.broadcast("SYNC_JOBS", list(jobs_db.values()))
        await nexus.broadcast("LOG", f"CRITICAL INFRA FLT: {job['id']} failed. VRAM {job['hw_vram']}GB < {job['req_vram']}GB.")
        
        # CAUSAL FEEDBACK LOOP
        evolution = policy.learn(f"OOM Failure on Job {jid}", 1.0)
        await nexus.broadcast("EVOLUTION", evolution)
        await nexus.broadcast("SYNC_POLICY", {"v":policy.version, "w":policy.weights, "h":policy.history})
        await nexus.broadcast("LOG", f"⚠️ POLICY MUTATED to v{policy.version}. Risk Aversion increased.")
        
    else:
        # SUCCESS
        job["status"] = "running"
        await nexus.broadcast("SYNC_JOBS", list(jobs_db.values()))
        await asyncio.sleep(3)
        job["status"] = "completed"
        await nexus.broadcast("SYNC_JOBS", list(jobs_db.values()))

# --- UI ---
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OrQuanta v3.5 | Causal Sovereign</title>
    <style>
        body { background:#0a0a0a; color:#eee; font-family:monospace; margin:0; display:grid; grid-template-columns:1fr 1fr; height:100vh; }
        .panel { padding:20px; border-right:1px solid #333; display:flex; flex-direction:column; }
        .card { background:#111; border:1px solid #333; padding:10px; margin-bottom:10px; border-left:3px solid #555; }
        .card.failed { border-color:#f04; }
        .card.completed { border-color:#0f8; }
        .metric-bar { height:20px; background:#222; margin-bottom:5px; position:relative; }
        .metric-fill { height:100%; transition:width 0.5s; }
        .log-entry { font-size:12px; margin-bottom:4px; opacity:0.8; border-bottom:1px solid #222; padding-bottom:2px; }
        .highlight { color:#f0f; font-weight:bold; }
        h2 { margin-top:0; border-bottom:2px solid #333; padding-bottom:10px; }
    </style>
</head>
<body>
    <div class="panel">
        <h2>SOVEREIGN POLICY <span id="p-ver" style="color:#0ff">v1</span></h2>
        
        <div>COST AVERSION</div>
        <div class="metric-bar"><div id="w-cost" class="metric-fill" style="width:0%; background:#0f8"></div></div>
        
        <div>PERF PREFERENCE</div>
        <div class="metric-bar"><div id="w-perf" class="metric-fill" style="width:0%; background:#08f"></div></div>
        
        <div>RISK AVERSION</div>
        <div class="metric-bar"><div id="w-risk" class="metric-fill" style="width:0%; background:#f04"></div></div>
        
        <h3>EVOLUTION HISTORY</h3>
        <div id="history" style="flex-grow:1; overflow-y:auto; font-size:11px;"></div>
    </div>
    
    <div class="panel">
        <h2>INFRASTRUCTURE OPS</h2>
        <div style="margin-bottom:20px;">
            <input id="intent" type="text" value="Train Llama 70b" style="padding:10px; width:60%; background:#222; color:#fff; border:1px solid #444;">
            <select id="vram" style="padding:10px; background:#222; color:#fff; border:1px solid #444;">
                <option value="80">High Mem (80GB+)</option>
                <option value="12">Low Mem (12GB)</option>
            </select>
            <button onclick="submit()" style="padding:10px; background:#0ff; border:none; font-weight:bold; cursor:pointer;">SUBMIT JOB</button>
        </div>
        
        <div id="jobs"></div>
        
        <h3>SYSTEM LOGS</h3>
        <div id="logs" style="flex-grow:1; background:#000; padding:10px; overflow-y:auto;"></div>
    </div>

    <script>
        const ws = new WebSocket(`ws://${location.host}/ws/core`);
        ws.onmessage = (e) => {
            const d = JSON.parse(e.data);
            if(d.type === 'SYNC_POLICY') renderPolicy(d.payload);
            if(d.type === 'SYNC_JOBS') renderJobs(d.payload);
            if(d.type === 'LOG') log(d.payload);
            if(d.type === 'EVOLUTION') log(`Mutation: ${d.payload.cause} -> Risk +${(d.payload.delta.risk||0).toFixed(2)}`);
        };

        function renderPolicy(p) {
            document.getElementById('p-ver').innerText = 'v' + p.v;
            document.getElementById('w-cost').style.width = (p.w.cost * 100) + '%';
            document.getElementById('w-perf').style.width = (p.w.perf * 100) + '%';
            document.getElementById('w-risk').style.width = (p.w.risk * 100) + '%';
            
            const h = document.getElementById('history');
            h.innerHTML = '';
            p.h.reverse().forEach(ev => {
                const el = document.createElement('div');
                el.innerHTML = `<span style="color:#888">[${ev.ts}]</span> <b>v${ev.v}</b>: ${ev.cause}`;
                el.style.marginBottom = '5px';
                h.appendChild(el);
            });
        }

        function renderJobs(jobs) {
            const c = document.getElementById('jobs');
            c.innerHTML = '';
            jobs.reverse().forEach(j => {
                const el = document.createElement('div');
                el.className = `card ${j.status}`;
                el.innerHTML = `
                    <b>${j.id}</b> (${j.status})<br>
                    Intent: ${j.intent}<br>
                    Req: ${j.req_vram}GB | Got: ${j.hw} (${j.hw_vram}GB)<br>
                    <span style="font-size:10px; color:#888">Governed by Policy v${j.policy_v}</span>
                `;
                c.appendChild(el);
            });
        }
        
        function log(msg) {
            const l = document.getElementById('logs');
            const el = document.createElement('div');
            el.className = 'log-entry';
            if(msg.includes('MUTATED')) el.className += ' highlight';
            el.innerText = `> ${msg}`;
            l.prepend(el);
        }

        async function submit() {
            const txt = document.getElementById('intent').value;
            const vram = parseInt(document.getElementById('vram').value);
            await fetch('/api/v1/submit', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({text:txt, required_vram:vram})
            });
        }
    </script>
</body>
</html>
"""

@app.get("/")
def ui(): return HTMLResponse(HTML_CONTENT)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
