import asyncio
import logging
import json
import secrets
import random
import math
from contextlib import asynccontextmanager
from typing import List, Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# --- DATA MODEL ---
DATA_FILE = "orquanta_v5_dna.json"

class PolicyDNA:
    def __init__(self):
        self.version = 1
        self.w_cost = 0.4      # Preference for low cost
        self.w_perf = 0.4      # Preference for high performance
        self.w_risk = 0.2      # Aversion to failure risk
        self.personality = "Balanced"
        self.history = []

    def mutate(self, outcome: dict):
        # Outcome: { "success": bool, "cost_overrun": bool, "latency_spike": bool }
        delta = {}
        old_dna = self.copy()
        
        if not outcome['success']:
            # Failure -> Increase Risk Aversion heavily
            self.w_risk = min(0.9, self.w_risk + 0.1)
            self.w_cost = max(0.1, self.w_cost - 0.05)
            self.w_perf = max(0.1, self.w_perf - 0.05)
            delta['reason'] = "Failure detected. Increasing Risk Aversion."
        
        elif outcome['latency_spike']:
            # Slow -> Increase Performance preference
            self.w_perf = min(0.9, self.w_perf + 0.1)
            self.w_cost = max(0.1, self.w_cost - 0.1)
            delta['reason'] = "Latency violation. Prioritizing Speed."
            
        elif outcome['cost_overrun']:
            # Expensive -> Increase Cost preference
            self.w_cost = min(0.9, self.w_cost + 0.1)
            self.w_perf = max(0.1, self.w_perf - 0.1)
            delta['reason'] = "Budget overrun. Tightening Cost controls."

        # Normalize
        total = self.w_cost + self.w_perf + self.w_risk
        self.w_cost /= total
        self.w_perf /= total
        self.w_risk /= total
        
        self.version += 1
        self.update_personality()
        return old_dna, self, delta

    def update_personality(self):
        if self.w_risk > 0.5: self.personality = "Paranoid/Safe"
        elif self.w_perf > 0.6: self.personality = "Speed Demon"
        elif self.w_cost > 0.6: self.personality = "Penny Pincher"
        else: self.personality = "Adaptive/Balanced"

    def copy(self):
        d = PolicyDNA()
        d.version, d.w_cost, d.w_perf, d.w_risk, d.personality = self.version, self.w_cost, self.w_perf, self.w_risk, self.personality
        return d
    
    def to_dict(self):
        return {"v": self.version, "cost": round(self.w_cost,2), "perf": round(self.w_perf,2), "risk": round(self.w_risk,2), "trait": self.personality}

dna = PolicyDNA()
jobs_db = {}

# --- FRONTEND ---
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OrQuanta v3.4 | Sovereign Evolution</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        :root { --bg:#050505; --panel:#0f0f0f; --accent:#00ffcc; --mutant:#ff00ea; --dim:#444; }
        body { background:var(--bg); color:#eee; font-family:'Inter'; margin:0; height:100vh; display:grid; grid-template-rows:60px 1fr; overflow:hidden; }
        
        header { display:flex; align-items:center; justify-content:space-between; padding:0 20px; border-bottom:1px solid #222; background:rgba(0,0,0,0.8); }
        .brand { font-family:'JetBrains Mono'; font-weight:800; font-size:18px; }
        
        .main { display:grid; grid-template-columns: 350px 1fr 350px; height:100%; }
        .col { border-right:1px solid #222; display:flex; flex-direction:column; background:var(--panel); }
        
        /* DNA PANEL */
        .dna-vis { padding:20px; }
        .dna-row { display:flex; justify-content:space-between; margin-bottom:10px; font-family:'JetBrains Mono'; font-size:12px; }
        .bar-bg { flex-grow:1; background:#333; height:8px; margin:5px 10px; border-radius:4px; overflow:hidden; }
        .bar-fill { height:100%; transition:width 1s ease-in-out; }
        .mutation-log { flex-grow:1; overflow-y:auto; font-size:11px; font-family:'JetBrains Mono'; padding:20px; border-top:1px solid #222; }
        .mutation { margin-bottom:10px; padding-bottom:10px; border-bottom:1px solid #222; opacity:0; animation:fadein 0.5s forwards; }
        .mutation .ver { color:#666; }
        .mutation .change { color:var(--mutant); font-weight:bold; }

        /* CENTER */
        .center-stage { padding:20px; background:radial-gradient(circle at 50% 50%, #1a1a1a 0%, #000 100%); display:flex; flex-direction:column; gap:20px; overflow-y:auto; }
        .job-card { background:rgba(255,255,255,0.05); border:1px solid #333; padding:15px; border-radius:8px; position:relative; }
        .job-card h3 { margin:0 0 5px 0; font-family:'JetBrains Mono'; color:var(--accent); }
        .job-card .status { font-size:10px; text-transform:uppercase; letter-spacing:1px; margin-bottom:10px; }
        
        /* CONTROLS */
        .controls { padding:20px; display:flex; flex-direction:column; gap:15px; }
        input { background:#222; border:1px solid #444; color:#fff; padding:10px; border-radius:4px; width:100%; box-sizing:border-box; }
        button { background:var(--accent); color:#000; font-weight:700; border:none; padding:12px; border-radius:4px; cursor:pointer; text-transform:uppercase; }
        .logs { flex-grow:1; background:#000; border:1px solid #222; padding:10px; overflow-y:auto; font-family:'JetBrains Mono'; font-size:11px; color:#aaa; }
        
        @keyframes fadein { to { opacity:1; } }
    </style>
</head>
<body>
    <header>
        <div class="brand">OrQuanta <span style="color:var(--mutant)">v3.4</span> // SOVEREIGN</div>
        <div style="font-size:11px; font-family:'JetBrains Mono'">POLICY VERSION: <span style="color:var(--accent)" id="pol-ver">v1</span></div>
    </header>
    <div class="main">
        <!-- DNA PANEL -->
        <div class="col">
            <div class="dna-vis">
                <h3 style="color:#888; font-size:12px; margin-top:0;">POLICY DNA</h3>
                <div class="dna-row"><span>COST</span> <div class="bar-bg"><div class="bar-fill" style="background:#00ffaa; width:40%" id="b-cost"></div></div> <span id="v-cost">0.40</span></div>
                <div class="dna-row"><span>PERF</span> <div class="bar-bg"><div class="bar-fill" style="background:#00aaff; width:40%" id="b-perf"></div></div> <span id="v-perf">0.40</span></div>
                <div class="dna-row"><span>RISK</span> <div class="bar-bg"><div class="bar-fill" style="background:#ff0066; width:20%" id="b-risk"></div></div> <span id="v-risk">0.20</span></div>
                <div style="margin-top:20px; text-align:center; padding:10px; background:#222; border-radius:4px;">
                    <div style="font-size:10px; color:#666;">CURRENT PERSONALITY</div>
                    <div style="font-size:14px; font-weight:bold; color:#fff;" id="trait">Balanced</div>
                </div>
            </div>
            <div class="mutation-log" id="mutations">
                <div class="mutation">
                    <div class="ver">v1.0 Genesis</div>
                    <div>System initialized with balanced baseline.</div>
                </div>
            </div>
        </div>

        <!-- CENTER -->
        <div class="center-stage" id="jobs">
            <!-- Jobs go here -->
        </div>

        <!-- RIGHT -->
        <div class="col controls">
            <div class="logs" id="sys-log">
                <div>[SYSTEM] Sovereign Kernel Active. Monitoring Outcomes.</div>
            </div>
            <div>
                <input type="text" id="intent" placeholder="Describe intent..." value="Train Llama 70b">
                <button onclick="submit()" style="margin-top:10px;">Execute Intent</button>
                <button onclick="forceFail()" style="margin-top:10px; background:#ff0044; color:#fff;">Simulate Failure (Trigger Evolution)</button>
            </div>
        </div>
    </div>

    <script>
        const ws = new WebSocket(`ws://${location.host}/ws/sov`);
        
        ws.onmessage = (e) => {
            const d = JSON.parse(e.data);
            
            if(d.type === 'DNA') {
                updateDNA(d.payload);
            }
            if(d.type === 'MUTATION') {
                logMutation(d.payload);
            }
            if(d.type === 'SYNC') {
                renderJobs(d.payload);
            }
            if(d.type === 'LOG') {
                const l = document.getElementById('sys-log');
                const el = document.createElement('div');
                el.innerText = `> ${d.payload}`;
                el.style.marginBottom = '4px';
                if(d.payload.includes('REJECTED')) el.style.color = '#ffaa00';
                l.appendChild(el);
                l.scrollTop = l.scrollHeight;
            }
        };

        function updateDNA(dna) {
            document.getElementById('pol-ver').innerText = 'v' + dna.v;
            
            document.getElementById('b-cost').style.width = (dna.cost * 100) + '%';
            document.getElementById('v-cost').innerText = dna.cost.toFixed(2);
            
            document.getElementById('b-perf').style.width = (dna.perf * 100) + '%';
            document.getElementById('v-perf').innerText = dna.perf.toFixed(2);
            
            document.getElementById('b-risk').style.width = (dna.risk * 100) + '%';
            document.getElementById('v-risk').innerText = dna.risk.toFixed(2);
            
            document.getElementById('trait').innerText = dna.trait;
        }

        function logMutation(m) {
            const c = document.getElementById('mutations');
            const el = document.createElement('div');
            el.className = 'mutation';
            el.innerHTML = `
                <div class="ver">v${m.old.v} → v${m.new.v}</div>
                <div class="change">${m.delta.reason}</div>
            `;
            c.prepend(el);
        }

        function renderJobs(jobs) {
            const c = document.getElementById('jobs');
            c.innerHTML = '';
            jobs.forEach(j => {
                const el = document.createElement('div');
                el.className = 'job-card';
                el.innerHTML = `
                    <h3>${j.id}</h3>
                    <div class="status" style="color:${j.status==='failed'?'#ff0044':(j.status==='completed'?'#00ffcc':'#fff')}">${j.status}</div>
                    <div style="font-size:12px;">${j.hardware}</div>
                    <div style="font-size:11px; color:#666; margin-top:5px;">Policy Score: ${j.score.toFixed(2)}</div>
                `;
                c.appendChild(el);
            });
        }

        async function submit() {
            const t = document.getElementById('intent').value;
            await fetch('/api/v1/intent', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text:t}) });
        }
        
        async function forceFail() {
            await fetch('/api/v1/chaos', { method:'POST' });
        }
    </script>
</body>
</html>
"""

# --- BACKEND ---
class Nexus:
    def __init__(self): self.socks = []
    async def broadcast(self, t, p):
        for s in self.socks: 
            try: await s.send_json({"type":t, "payload":p})
            except: pass
nexus = Nexus()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.websocket("/ws/sov")
async def ws_ep(ws: WebSocket):
    await ws.accept()
    nexus.socks.append(ws)
    await ws.send_json({"type":"DNA", "payload": dna.to_dict()})
    try:
        while True: await ws.receive_text()
    except: nexus.socks.remove(ws)

class IntentReq(BaseModel): text: str

@app.get("/")
def ui(): return HTMLResponse(HTML_CONTENT)

@app.post("/api/v1/intent")
async def intent(r: IntentReq):
    # DECISION ENGINE BASED ON DNA
    opts = [
        {"hw": "8x H100", "cost": 0.1, "perf": 0.9, "risk": 0.1}, # Expensive, Fast, Safe
        {"hw": "8x A100", "cost": 0.4, "perf": 0.6, "risk": 0.3}, # Mid
        {"hw": "8x T4",   "cost": 0.9, "perf": 0.2, "risk": 0.8}  # Cheap, Slow, Risky
    ]
    
    # Calculate Scores
    best_score = -1
    selected = None
    
    for opt in opts:
        # Score = (w_cost * cost_score) + (w_perf * perf_score) + (w_risk * (1-risk_score))
        score = (dna.w_cost * opt['cost']) + (dna.w_perf * opt['perf']) + (dna.w_risk * (1 - opt['risk']))
        if score > best_score:
            best_score = score
            selected = opt
    
    # Commit
    jid = f"SOV-{secrets.token_hex(2).upper()}"
    jobs_db[jid] = {"id": jid, "status": "running", "hardware": selected['hw'], "score": best_score}
    await nexus.broadcast("SYNC", list(jobs_db.values()))
    await nexus.broadcast("LOG", f"Deployed {selected['hw']} (Score: {best_score:.2f}) based on {dna.personality} policy.")
    return {"id": jid}

@app.post("/api/v1/chaos")
async def chaos():
    # Force failure on running job to trigger evolution
    run = [j for j in jobs_db.values() if j['status'] == 'running']
    if run:
        j = run[0]
        j['status'] = 'failed'
        await nexus.broadcast("SYNC", list(jobs_db.values()))
        await nexus.broadcast("LOG", f"CRITICAL FAILURE on {j['id']}. Calculating Regret...")
        
        # MUTATE DNA
        old_snap = dna.to_dict()
        _, _, delta = dna.mutate({"success": False, "cost_overrun": False, "latency_spike": False})
        new_snap = dna.to_dict()
        
        await nexus.broadcast("DNA", new_snap)
        await nexus.broadcast("MUTATION", {"old": old_snap, "new": new_snap, "delta": delta})
        await nexus.broadcast("LOG", f"POLICY EVOLVED: {delta['reason']}")
        return {"status": "evolved"}
    return {"status": "no_active_jobs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
