/**
 * OrQuanta Agentic v1.0 — Cloudflare Edge Worker
 * ================================================
 * Routes:
 *   /           → edge landing page (Worker HTML)
 *   /app/*      → Cloudflare Pages SPA (orquanta-app.pages.dev)
 *   /api/*      → FastAPI on Render Singapore
 *   /auth/*     → FastAPI on Render Singapore
 *   /health     → FastAPI on Render Singapore
 *   /ws/*       → WebSocket proxy to Render
 *   /docs       → FastAPI on Render Singapore
 *   everything else → FastAPI on Render Singapore
 *
 * Environment Variables:
 *   BACKEND_URL  = https://orquanta-sg.onrender.com
 *   PAGES_URL    = https://orquanta-app.pages.dev
 */

const SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "X-XSS-Protection": "1; mode=block",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
};

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
  "Access-Control-Max-Age": "86400",
};

// Routes that should be proxied to the FastAPI backend
const API_PREFIXES = [
  "/api/", "/auth/", "/health", "/docs", "/redoc",
  "/openapi.json", "/metrics", "/providers/", "/goals",
  "/jobs", "/agents", "/demo", "/welcome", "/ws/",
];

function isApiRoute(path) {
  return API_PREFIXES.some(p => path.startsWith(p) || path === p.replace(/\/$/, ""));
}

function addHeaders(response, extra = {}) {
  const r = new Response(response.body, response);
  Object.entries({ ...SECURITY_HEADERS, ...extra }).forEach(([k, v]) => r.headers.set(k, v));
  return r;
}

async function proxyTo(request, originUrl) {
  const url = new URL(request.url);
  const target = `${originUrl}${url.pathname}${url.search}`;

  // WebSocket upgrade
  if (request.headers.get("Upgrade") === "websocket") {
    return fetch(target.replace(/^https?:\/\//, "wss://"), request);
  }

  const proxied = new Request(target, {
    method: request.method,
    headers: request.headers,
    body: ["GET", "HEAD"].includes(request.method) ? null : request.body,
    redirect: "follow",
  });

  try {
    const resp = await fetch(proxied);
    return addHeaders(resp, CORS_HEADERS);
  } catch (err) {
    return new Response(
      JSON.stringify({ error: "Gateway error", detail: err.message }),
      { status: 502, headers: { "Content-Type": "application/json", ...CORS_HEADERS } }
    );
  }
}

// Keep backward compat alias
const proxyToBackend = (req, env) =>
  proxyTo(req, env.BACKEND_URL || "https://orquanta-sg.onrender.com");

function landingPage(env) {
  const backendUrl = env.BACKEND_URL || "https://orquanta-api.up.railway.app";
  const appUrl = env.APP_URL || "/app";
  return new Response(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OrQuanta — Agentic GPU Cloud</title>
<meta name="description" content="Autonomous GPU Cloud Orchestration. 5 AI agents, multi-cloud routing, 67% below AWS pricing.">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#050608;color:#e2e8f0;font-family:'Inter',sans-serif;min-height:100vh;overflow-x:hidden}
.bg{position:fixed;inset:0;background:radial-gradient(ellipse 70% 50% at 50% -10%,rgba(0,212,255,.12),transparent 70%),radial-gradient(ellipse 50% 40% at 80% 80%,rgba(123,47,255,.08),transparent 70%);pointer-events:none}
nav{display:flex;align-items:center;justify-content:space-between;padding:20px 40px;border-bottom:1px solid rgba(255,255,255,.06);position:sticky;top:0;z-index:10;background:rgba(5,6,8,.8);backdrop-filter:blur(16px)}
.logo{font-family:'Space Grotesk',sans-serif;font-size:1.4rem;font-weight:800;background:linear-gradient(135deg,#00D4FF,#7B2FFF);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.nav-links{display:flex;gap:8px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 20px;border-radius:8px;font-size:.875rem;font-weight:600;cursor:pointer;text-decoration:none;transition:all .2s;border:none}
.btn-outline{background:transparent;border:1px solid rgba(255,255,255,.12);color:#94a3b8}
.btn-outline:hover{border-color:rgba(0,212,255,.4);color:#00D4FF}
.btn-primary{background:linear-gradient(135deg,#00D4FF,#7B2FFF);color:#fff;box-shadow:0 4px 20px rgba(0,212,255,.25)}
.btn-primary:hover{opacity:.9;transform:translateY(-1px)}
hero{display:flex;flex-direction:column;align-items:center;text-align:center;padding:100px 24px 60px;position:relative}
.badge{display:inline-flex;align-items:center;gap:8px;padding:6px 16px;border-radius:999px;border:1px solid rgba(0,255,136,.3);background:rgba(0,255,136,.07);font-size:.8rem;font-weight:600;color:#00FF88;margin-bottom:28px}
.dot{width:7px;height:7px;border-radius:50%;background:#00FF88;animation:pulse 2s infinite}
h1{font-family:'Space Grotesk',sans-serif;font-size:clamp(2.2rem,6vw,4rem);font-weight:800;line-height:1.1;letter-spacing:-.03em;margin-bottom:20px}
.grad{background:linear-gradient(135deg,#00D4FF,#7B2FFF);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sub{font-size:1.1rem;color:#94a3b8;max-width:560px;line-height:1.7;margin-bottom:40px}
.cta-row{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;margin-bottom:60px}
.stats{display:flex;gap:40px;flex-wrap:wrap;justify-content:center;padding:32px;border:1px solid rgba(255,255,255,.06);border-radius:16px;background:rgba(255,255,255,.02);margin-bottom:80px;max-width:700px}
.stat-item{text-align:center}
.stat-val{font-family:'Space Grotesk',sans-serif;font-size:2rem;font-weight:800;background:linear-gradient(135deg,#00D4FF,#7B2FFF);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat-label{font-size:.8rem;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:.08em}
.agents{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;max-width:900px;margin:0 auto 80px;padding:0 24px}
.agent-card{background:rgba(15,22,36,.8);border:1px solid rgba(255,255,255,.07);border-radius:14px;padding:20px;transition:all .2s}
.agent-card:hover{border-color:rgba(0,212,255,.2);transform:translateY(-2px)}
.agent-icon{font-size:1.8rem;margin-bottom:10px}
.agent-name{font-family:'Space Grotesk',sans-serif;font-size:.95rem;font-weight:700;color:#e2e8f0;margin-bottom:4px}
.agent-desc{font-size:.8rem;color:#64748b;line-height:1.5}
.agent-status{display:inline-flex;align-items:center;gap:5px;margin-top:8px;font-size:.72rem;font-weight:600;color:#00FF88}
footer{border-top:1px solid rgba(255,255,255,.06);padding:24px 40px;text-align:center;color:#475569;font-size:.85rem}
footer a{color:#00D4FF;text-decoration:none}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.4)}}
</style>
</head>
<body>
<div class="bg"></div>
<nav>
  <div class="logo">OrQuanta</div>
  <div class="nav-links">
    <a href="/health" class="btn btn-outline">API Status</a>
    <a href="/docs" class="btn btn-outline">API Docs</a>
    <a href="${appUrl}" class="btn btn-primary">Launch Dashboard →</a>
  </div>
</nav>
<hero style="display:flex;flex-direction:column;align-items:center;text-align:center;padding:100px 24px 60px">
  <div class="badge"><span class="dot"></span> 5 AI Agents Online · Demo Mode Active</div>
  <h1>Autonomous<br><span class="grad">GPU Cloud</span><br>Orchestration</h1>
  <p class="sub">Submit goals in plain English. OrQuanta's 5 specialized AI agents handle scheduling, cost optimization, self-healing, forecasting, and auditing — across AWS, GCP, Azure, and CoreWeave.</p>
  <div class="cta-row">
    <a href="${appUrl}" class="btn btn-primary" style="font-size:1rem;padding:14px 28px">Open Dashboard →</a>
    <a href="/docs" class="btn btn-outline" style="font-size:1rem;padding:14px 28px">API Reference</a>
  </div>
  <div class="stats">
    <div class="stat-item"><div class="stat-val">67%</div><div class="stat-label">Below AWS Price</div></div>
    <div class="stat-item"><div class="stat-val">5</div><div class="stat-label">AI Agents</div></div>
    <div class="stat-item"><div class="stat-val">99.95%</div><div class="stat-label">SLA Uptime</div></div>
    <div class="stat-item"><div class="stat-val">&lt;30s</div><div class="stat-label">GPU Launch</div></div>
  </div>
</hero>
<div class="agents">
  ${[
    ["🎯","OrMind Orchestrator","Routes goals to the right agents with RL-based decision making"],
    ["📅","Scheduler Agent","Packs GPU jobs optimally across time windows and providers"],
    ["💰","Cost Optimizer","Monitors spend in real time and switches to cheaper instances"],
    ["🔧","Healing Agent","Detects anomalies and auto-restarts failed GPU workloads"],
    ["📊","Forecast Agent","Predicts costs and demand 6 hours ahead with 92% accuracy"],
  ].map(([icon,name,desc]) => `
  <div class="agent-card">
    <div class="agent-icon">${icon}</div>
    <div class="agent-name">${name}</div>
    <div class="agent-desc">${desc}</div>
    <div class="agent-status"><span style="width:6px;height:6px;border-radius:50%;background:#00FF88;display:inline-block"></span> Online</div>
  </div>`).join("")}
</div>
<footer>
  OrQuanta Agentic v1.0 · <a href="mailto:orquanta.founder@gmail.com">orquanta.founder@gmail.com</a> ·
  Backend: <a href="${backendUrl}/health">${backendUrl}</a>
</footer>
</body>
</html>`, {
    status: 200,
    headers: { "Content-Type": "text/html;charset=UTF-8", ...SECURITY_HEADERS },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: { ...CORS_HEADERS, ...SECURITY_HEADERS } });
    }

    // Root landing page — marketing page served at the edge
    if (path === "/") return landingPage(env);

    // Cloudflare Pages SPA — /app/* served from edge CDN (fast global load)
    const pagesUrl = env.PAGES_URL || "https://orquanta-app.pages.dev";
    if (path.startsWith("/app")) return proxyTo(request, pagesUrl);

    // FastAPI backend on Render Singapore — all other routes
    return proxyToBackend(request, env);
  },

  // Cron: every 5 min — keeps Render free tier alive (prevents 30-60s cold starts)
  async scheduled(_event, env, ctx) {
    const backend = env.BACKEND_URL || "https://orquanta-sg.onrender.com";
    ctx.waitUntil(
      fetch(`${backend}/health`, { method: "GET" }).then(r =>
        console.log(`[keepalive] ${new Date().toISOString()} → HTTP ${r.status}`)
      ).catch(e =>
        console.error(`[keepalive] failed: ${e.message}`)
      )
    );
  },
};
