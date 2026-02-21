import asyncio
import logging
import json
import secrets
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# --- DATA MODEL ---
DATA_FILE = "orquanta_v4_cortex.json"

class MemoryEngram:
    def __init__(self, tag):
        self.tag = tag
        self.samples = 0
        self.success_rate = 0.5
        self.avg_cost = 0.0
        self.preferred_hardware = "T4" # Default
        self.evolution_log = []

cortex_memory: Dict[str, MemoryEngram] = {}
jobs_db = {}
decision_log = []

# --- FRONTEND ---
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OrQuanta v3.3 | Self-Governing Intelligence</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        :root { --bg:#020202; --panel:#0a0a0a; --accent:#00ff9d; --warn:#ffaa00; --err:#ff0044; --dim:#444; }
        body { background:var(--bg); color:#eee; font-family:'Inter'; margin:0; height:100vh; overflow:hidden; display:grid; grid-template-rows:50px 1fr; }
        
        /* HEADER */
        header { display:flex; align-items:center; justify-content:space-between; padding:0 20px; border-bottom:1px solid #222; background:rgba(0,0,0,0.5); backdrop-filter:blur(5px); }
        .brand { font-family:'JetBrains Mono'; font-weight:800; font-size:18px; letter-spacing:-1px; }
        
        /* LAYOUT */
        .workspace { display:grid; grid-template-columns: 320px 1fr 350px; height:100%; }
        .col { border-right:1px solid #222; display:flex; flex-direction:column; background:var(--panel); }
        
        /* CORTEX STREAM (Left) */
        .thought-stream { padding:20px; overflow-y:auto; font-family:'JetBrains Mono'; font-size:11px; }
        .thought { margin-bottom:15px; border-left:2px solid var(--dim); padding-left:10px; opacity:0.7; transition:all 0.3s; }
        .thought.active { opacity:1; border-color:var(--accent); }
        .thought .ts { color:#666; margin-bottom:4px; }
        .thought .content { color:#ccc; }
        .thought .meta { color:var(--accent); margin-top:4px; font-weight:bold; }

        /* MAIN VIEW (Center) */
        .vis-area { padding:20px; overflow-y:auto; background:radial-gradient(circle at 50% 30%, #111 0%, #000 100%); }
        .job-cluster { display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:15px; }
        .card { background:rgba(255,255,255,0.03); border:1px solid #333; padding:15px; border-radius:6px; position:relative; overflow:hidden; }
        .card::before { content:''; position:absolute; top:0; left:0; width:100%; height:2px; background:var(--accent); opacity:0.5; }
        .card h3 { margin:0 0 10px 0; font-size:14px; font-family:'JetBrains Mono'; }
        .card .stat { font-size:12px; color:#888; display:flex; justify-content:space-between; margin-bottom:4px; }
        .card .bar { height:3px; background:#333; margin-top:10px; border-radius:3px; overflow:hidden; }
        .card .fill { height:100%; background:var(--accent); width:0%; transition:width 0.5s; }

        /* INTERACTION (Right) */
        .interaction { padding:20px; display:flex; flex-direction:column; gap:20px; }
        .chat-box { flex-grow:1; background:#000; border:1px solid #222; border-radius:8px; padding:15px; overflow-y:auto; font-size:13px; }
        .msg { margin-bottom:10px; padding:8px 12px; border-radius:6px; max-width:90%; }
        .msg.sys { background:#112211; color:var(--accent); align-self:flex-start; border:1px solid #004422; }
        .msg.user { background:#222; color:#fff; align-self:flex-end; margin-left:auto; text-align:right; border:1px solid #444; }
        
        .controls { display:grid; gap:10px; }
        input { background:#111; border:1px solid #333; color:#fff; padding:12px; border-radius:4px; width:100%; box-sizing:border-box; font-family:'Inter'; outline:none; }
        input:focus { border-color:var(--accent); }
        button { background:var(--accent); color:#000; font-weight:700; border:none; padding:12px; border-radius:4px; cursor:pointer; text-transform:uppercase; letter-spacing:1px; transition:0.2s; }
        button:hover { box-shadow:0 0 15px rgba(0,255,157,0.4); }

        /* DECISION CARD */
        .decision-popup { background:#111; border:1px solid #444; padding:15px; margin-top:10px; border-radius:6px; font-size:12px; }
        .decision-popup h4 { margin:0 0 5px 0; color:var(--accent); }
        .decision-popup ul { margin:5px 0 0 20px; padding:0; color:#888; }
    </style>
</head>
<body>
    <header>
        <div class="brand">OrQuanta <span style="color:var(--accent)">v3.3</span> // GOVERNOR</div>
        <div style="font-size:12px; color:#666;">CORTEX STATUS: <span style="color:var(--accent)">AUTONOMOUS</span></div>
    </header>
    <div class="workspace">
        <!-- LEFT: THOUGHT STREAM -->
        <div class="col">
            <div style="padding:15px; border-bottom:1px solid #222; font-size:12px; font-weight:700; color:#666;">INTERNAL MONOLOGUE</div>
            <div class="thought-stream" id="stream">
                <!-- Injected via WS -->
            </div>
        </div>

        <!-- CENTER: VISUALIZATION -->
        <div class="vis-area">
            <h2 style="margin-top:0; font-size:16px; opacity:0.8;">ACTIVE CLUSTER TOPOLOGY</h2>
            <div class="job-cluster" id="jobs"></div>
        </div>

        <!-- RIGHT: INTERACTION -->
        <div class="interaction col" style="border-left:1px solid #222; border-right:none;">
            <div class="chat-box" id="chat">
                <div class="msg sys">I am the Governor. I evaluate intent, optimize costs, and enforce policy. State your objective.</div>
            </div>
            <div class="controls">
                <input type="text" id="prompt" placeholder="E.g., 'Train Llama-70b'..." onkeypress="if(event.key==='Enter') send()">
                <button onclick="send()">Submit Intent</button>
            </div>
        </div>
    </div>

    <script>
        const ws = new WebSocket(`ws://${location.host}/ws/nexus`);
        
        ws.onmessage = (e) => {
            const d = JSON.parse(e.data);
            
            // 1. THOUGHT STREAM
            if(d.type === 'THOUGHT') {
                const s = document.getElementById('stream');
                const t = document.createElement('div');
                t.className = 'thought active';
                t.innerHTML = `
                    <div class="ts">${new Date().toLocaleTimeString()}</div>
                    <div class="content">${d.payload.text}</div>
                    ${d.payload.meta ? `<div class="meta">${d.payload.meta}</div>` : ''}
                `;
                s.prepend(t);
                if(s.children.length > 20) s.lastChild.remove();
            }

            // 2. CHAT / DECISION
            if(d.type === 'DECISION') {
                const c = document.getElementById('chat');
                const dec = d.payload;
                c.innerHTML += `
                    <div class="msg sys">
                        Weighed <b>${dec.alternatives_count} alternatives</b>.<br>
                        Selected: <span style="color:var(--accent)">${dec.selection}</span><br>
                        <i>"${dec.justification}"</i>
                        <div class="decision-popup">
                            <h4>REJECTED:</h4>
                            <ul>${dec.rejected.map(r => `<li>${r}</li>`).join('')}</ul>
                        </div>
                    </div>
                `;
                c.scrollTop = c.scrollHeight;
            }

            // 3. TELEMETRY
            if(d.type === 'SYNC') {
                const jc = document.getElementById('jobs');
                jc.innerHTML = '';
                d.payload.jobs.forEach(j => {
                    const card = document.createElement('div');
                    card.className = 'card';
                    card.innerHTML = `
                        <h3>${j.id}</h3>
                        <div class="stat"><span>TYPE</span> <span>${j.gpu}</span></div>
                        <div class="stat"><span>STATUS</span> <span style="color:${j.status==='running'?'var(--accent)':'#888'}">${j.status.toUpperCase()}</span></div>
                        <div class="bar"><div class="fill" style="width:${j.progress}%"></div></div>
                        <div style="margin-top:5px; font-size:10px; color:#555;">${j.log}</div>
                    `;
                    jc.appendChild(card);
                });
            }
        };

        async function send() {
            const p = document.getElementById('prompt');
            const txt = p.value.trim();
            if(!txt) return;
            
            document.getElementById('chat').innerHTML += `<div class="msg user">${txt}</div>`;
            p.value = '';
            
            await fetch('/api/v1/govern/intent', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({ intent_text: txt })
            });
        }
    </script>
</body>
</html>
"""

# --- BACKEND ---
class Nexus:
    def __init__(self): self.socks = []
    async def connect(self, ws): await ws.accept(); self.socks.append(ws)
    def disconnect(self, ws): self.socks.remove(ws)
    async def broadcast(self, t, p):
        for s in self.socks: 
            try: await s.send_json({"type":t, "payload":p})
            except: pass

nexus = Nexus()
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Intent(BaseModel): intent_text: str

# 🧠 THE META-BRAIN GOVERNOR
async def govern_intent(text: str):
    text = text.lower()
    await nexus.broadcast('THOUGHT', {"text": f"Analyzing Intent: '{text}'...", "meta": "INTENT DETECTED"})
    await asyncio.sleep(0.5) # Simulating compute
    
    # 1. Evaluate
    if "70b" in text or "train" in text:
        selection = "8x H100 (Cluster A)"
        rejected = ["1x A100 (Insufficient SRAM)", "8x T4 (Bandwidth Bottleneck)"]
        justify = "Model parameters (70B) require >160GB combined HBM at >2TB/s/node."
        gpu_type = "H100"
        gpu_count = 8
        confidence = 0.98
    elif "inference" in text:
        selection = "1x A10G"
        rejected = ["1x H100 (Overkill/Cost)", "CPU (Too Slow)"]
        justify = "Inference is latency-bound but low memory. A10G offers best $/token."
        gpu_type = "A10G"
        gpu_count = 1
        confidence = 0.92
    else:
        selection = "1x T4 (Spot)"
        rejected = ["Reserved Instance (Commitment Risk)"]
        justify = "Workload ambiguous. Defaulting to lowest-risk spot instance."
        gpu_type = "T4"
        gpu_count = 1
        confidence = 0.60
    
    await nexus.broadcast('THOUGHT', {"text": "Calculating Strategy Trade-offs...", "meta": f"CONFIDENCE: {int(confidence*100)}%"})
    await asyncio.sleep(0.5)
    
    # 2. Decision Finality
    await nexus.broadcast('DECISION', {
        "selection": selection,
        "rejected": rejected,
        "justification": justify,
        "alternatives_count": len(rejected) + 1
    })
    
    # 3. Execution
    jid = f"GOV-{secrets.token_hex(3).upper()}"
    jobs_db[jid] = {"id": jid, "gpu": f"{gpu_count}x {gpu_type}", "status": "pending", "progress": 0, "log": "Initializing Container..."}
    await nexus.broadcast('THOUGHT', {"text": f"Dispatching Job {jid} to Scheduler.", "meta": "ACTION TAKEN"})

@app.get("/")
def ui(): return HTMLResponse(HTML_CONTENT)

@app.websocket("/ws/nexus")
async def ws_ep(ws: WebSocket):
    await nexus.connect(ws)
    try:
        while True: await ws.receive_text()
    except:
        nexus.disconnect(ws)

@app.post("/api/v1/govern/intent")
async def submit_intent(i: Intent):
    asyncio.create_task(govern_intent(i.intent_text))
    return {"status": "processing"}

async def autonomous_loop():
    while True:
        try:
            active = [j for j in jobs_db.values() if j["status"] != "completed"]
            for j in active:
                if j["status"] == "pending":
                    if random.random() > 0.2:
                        j["status"] = "running"
                        await nexus.broadcast('THOUGHT', {"text": f"Job {j['id']} transitioned to active state.", "meta": "SCHEDULER"})
                elif j["status"] == "running":
                    j["progress"] += random.randint(2, 8)
                    if j["progress"] >= 100:
                        j["status"] = "completed"
                        j["progress"] = 100
                        j["log"] = "Terminated Successfully"
                        await nexus.broadcast('THOUGHT', {"text": f"Job {j['id']} completed. Updating Cost Models.", "meta": "LEARNING"})
            
            await nexus.broadcast('SYNC', {"jobs": list(jobs_db.values())})
            await asyncio.sleep(1)
        except Exception as e:
            print(e)
            await asyncio.sleep(1)

# LIFESPAN
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(autonomous_loop())
    yield

app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn
    print("GOVERNOR ACTIVE...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
