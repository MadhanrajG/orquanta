/**
 * OrQuanta Agentic v1.0  -  Cloudflare Edge Worker
 * ================================================
 * Routes:
 *   /           -> edge landing page (Worker HTML)
 *   /app/*      -> Cloudflare Pages SPA (orquanta-app.pages.dev)
 *   /api/*      -> FastAPI on Render Singapore
 *   /auth/*     -> FastAPI on Render Singapore
 *   /health     -> FastAPI on Render Singapore
 *   /ws/*       -> WebSocket proxy to Render
 *   /docs       -> FastAPI on Render Singapore
 *   everything else -> FastAPI on Render Singapore
 *
 * Environment Variables:
 *   BACKEND_URL  = https://orquanta-sg.onrender.com
 *   PAGES_URL    = https://orquanta-app.pages.dev
 */

const SECURITY_HEADERS = {
  "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' fonts.googleapis.com; font-src 'self' fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self' wss: https:; frame-ancestors 'none'; base-uri 'self'; form-action 'self';",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "X-XSS-Protection": "1; mode=block",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
};

// Relaxed CSP for docs pages — SwaggerUI/ReDoc load scripts from CDN
const DOCS_SECURITY_HEADERS = {
  "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net unpkg.com; style-src 'self' 'unsafe-inline' fonts.googleapis.com cdn.jsdelivr.net unpkg.com; font-src 'self' fonts.gstatic.com; img-src 'self' data: blob: fastapi.tiangolo.com; connect-src 'self' wss: https:; frame-ancestors 'none'; base-uri 'self'; form-action 'self';",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
};

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "https://orquanta.com",
  "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
  "Access-Control-Max-Age": "86400",
};

// Routes that should be proxied to the FastAPI backend
const API_PREFIXES = [
  "/api/", "/auth/", "/health", "/docs", "/redoc",
  "/openapi.json", "/metrics", "/providers/", "/goals",
  "/jobs", "/agents", "/demo", "/welcome", "/ws/",
  "/register", "/pricing", "/signup",
];

function isApiRoute(path) {
  return API_PREFIXES.some(p => path.startsWith(p) || path === p.replace(/\/$/, ""));
}

function addHeaders(response, extra = {}, secHeaders = SECURITY_HEADERS) {
  const r = new Response(response.body, response);
  Object.entries({ ...secHeaders, ...extra }).forEach(([k, v]) => r.headers.set(k, v));
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
  const appUrl = env.APP_URL || "/app";
  return new Response(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OrQuanta — Agentic GPU Cloud | Deploy AI Models at 67% Below AWS</title>
<meta name="description" content="Autonomous GPU Cloud Orchestration. 24+ open-source AI models, 5 AI agents, multi-cloud routing, 67% below AWS pricing. Deploy LLaMA, DeepSeek, Whisper in seconds.">
<meta name="theme-color" content="#ffffff">
<meta property="og:title" content="OrQuanta — Agentic GPU Cloud">
<meta property="og:description" content="Deploy open-source AI models to the cheapest GPU in seconds. 5 AI agents handle everything.">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--brand:#7C6BF0;--brand-light:#9B8BF4;--accent:#10B981;--text:#0F172A;--text-sec:#475569;--text-muted:#94A3B8;--border:rgba(226,232,240,0.8);--white:#FFFFFF;--bg:#F8FAFC}
body{background:var(--white);color:var(--text);font-family:'Inter',system-ui,sans-serif;min-height:100vh;overflow-x:hidden;-webkit-font-smoothing:antialiased}

/* ── Animated Background ───────── */
.aurora{position:fixed;inset:0;pointer-events:none;z-index:0}
.aurora::before{content:'';position:absolute;top:-20%;left:-10%;width:60%;height:60%;background:radial-gradient(ellipse,rgba(124,107,240,0.06),transparent 70%);animation:morph 18s ease-in-out infinite,drift 25s ease-in-out infinite;border-radius:40% 60% 70% 30%/40% 50% 60% 50%}
.aurora::after{content:'';position:absolute;bottom:-10%;right:-10%;width:50%;height:50%;background:radial-gradient(ellipse,rgba(16,185,129,0.04),transparent 70%);animation:morph 15s ease-in-out infinite reverse,drift 20s ease-in-out infinite reverse;border-radius:60% 40% 30% 70%/60% 30% 70% 40%}
.grid-bg{position:fixed;inset:0;background-image:linear-gradient(rgba(124,107,240,0.02) 1px,transparent 1px),linear-gradient(90deg,rgba(124,107,240,0.02) 1px,transparent 1px);background-size:60px 60px;pointer-events:none;z-index:0}

@keyframes morph{0%,100%{border-radius:40% 60% 70% 30%/40% 50% 60% 50%}25%{border-radius:60% 40% 30% 70%/50% 60% 30% 60%}50%{border-radius:30% 60% 70% 40%/60% 30% 70% 40%}75%{border-radius:50% 40% 60% 30%/40% 60% 50% 50%}}
@keyframes drift{0%{transform:translate(0,0) rotate(0deg)}50%{transform:translate(30px,-20px) rotate(3deg)}100%{transform:translate(0,0) rotate(0deg)}}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
@keyframes glow{0%,100%{box-shadow:0 0 20px rgba(124,107,240,0.1)}50%{box-shadow:0 0 40px rgba(124,107,240,0.2)}}
@keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.4)}}
@keyframes textShimmer{0%{background-position:-100% 0}100%{background-position:200% 0}}
@keyframes slideInLeft{from{opacity:0;transform:translateX(-20px)}to{opacity:1;transform:translateX(0)}}
@keyframes scaleIn{from{opacity:0;transform:scale(0.9)}to{opacity:1;transform:scale(1)}}

.fade-up{animation:fadeUp .6s cubic-bezier(.23,1,.32,1) both}
.fade-up-1{animation-delay:.1s}.fade-up-2{animation-delay:.2s}.fade-up-3{animation-delay:.3s}
.fade-up-4{animation-delay:.4s}.fade-up-5{animation-delay:.5s}.fade-up-6{animation-delay:.6s}

/* ── Nav ───────────────────────── */
nav{display:flex;align-items:center;justify-content:space-between;padding:16px 48px;border-bottom:1px solid var(--border);position:sticky;top:0;z-index:50;background:rgba(255,255,255,0.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)}
.logo{font-family:'Space Grotesk',sans-serif;font-size:1.4rem;font-weight:800;background:linear-gradient(135deg,var(--brand),var(--brand-light));-webkit-background-clip:text;-webkit-text-fill-color:transparent;text-decoration:none;letter-spacing:-.02em}
.logo-sub{font-size:.65rem;font-weight:600;color:var(--text-muted);letter-spacing:.1em;text-transform:uppercase;margin-left:10px;vertical-align:middle}
.nav-r{display:flex;align-items:center;gap:8px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 20px;border-radius:10px;font-size:.875rem;font-weight:600;cursor:pointer;text-decoration:none;transition:all .25s cubic-bezier(.23,1,.32,1);border:none;font-family:inherit}
.btn-ghost{background:transparent;color:var(--text-sec);padding:9px 14px}
.btn-ghost:hover{color:var(--brand);background:rgba(124,107,240,0.05)}
.btn-outline{background:transparent;border:1px solid var(--border);color:var(--text-sec)}
.btn-outline:hover{border-color:rgba(124,107,240,0.3);color:var(--brand)}
.btn-primary{background:linear-gradient(135deg,var(--brand),var(--brand-light));color:#fff;box-shadow:0 4px 20px rgba(124,107,240,0.25);position:relative;overflow:hidden}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(124,107,240,0.35)}
.btn-primary:active{transform:scale(.97)}
.btn-primary::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.15),transparent);transform:translateX(-100%);transition:transform .5s}.btn-primary:hover::after{transform:translateX(100%)}

/* ── Hero ──────────────────────── */
.hero{display:flex;flex-direction:column;align-items:center;text-align:center;padding:80px 24px 48px;position:relative;z-index:1}
.live-badge{display:inline-flex;align-items:center;gap:8px;padding:7px 18px;border-radius:999px;border:1px solid rgba(16,185,129,0.3);background:rgba(16,185,129,0.05);font-size:.82rem;font-weight:600;color:var(--accent);margin-bottom:28px;animation:fadeUp .5s both,glow 3s ease-in-out infinite}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent);animation:pulse 2s infinite}
h1{font-family:'Space Grotesk',sans-serif;font-size:clamp(2.4rem,7vw,4.5rem);font-weight:800;line-height:1.05;letter-spacing:-.04em;margin-bottom:20px;color:var(--text)}
.grad{background:linear-gradient(135deg,var(--brand),#F472B6,var(--accent),var(--brand));background-size:300% 100%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:textShimmer 6s ease-in-out infinite}
.hero-sub{font-size:1.15rem;color:var(--text-sec);max-width:620px;line-height:1.75;margin-bottom:36px;font-weight:400}
.hero-sub strong{color:var(--text);font-weight:600}
.cta-row{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;margin-bottom:20px}
.trust-line{font-size:.78rem;color:var(--text-muted);margin-bottom:50px;display:flex;align-items:center;gap:6px}
.trust-line::before,.trust-line::after{content:'';width:40px;height:1px;background:var(--border)}

/* ── Stats ─────────────────────── */
.stats{display:flex;gap:2px;border-radius:18px;border:1px solid var(--border);background:rgba(255,255,255,0.8);backdrop-filter:blur(12px);overflow:hidden;margin-bottom:70px;box-shadow:0 2px 12px rgba(0,0,0,0.03)}
.stat{flex:1;text-align:center;padding:28px 24px;position:relative;transition:all .3s}
.stat:not(:last-child)::after{content:'';position:absolute;right:0;top:20%;height:60%;width:1px;background:var(--border)}
.stat:hover{background:rgba(124,107,240,0.02)}
.stat-val{font-family:'JetBrains Mono',monospace;font-size:2rem;font-weight:800;background:linear-gradient(135deg,var(--brand),var(--brand-light));-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-.03em}
.stat-label{font-size:.75rem;color:var(--text-muted);margin-top:4px;text-transform:uppercase;letter-spacing:.1em;font-weight:600}

/* ── Section Headers ───────────── */
.section{max-width:1100px;margin:0 auto;padding:0 24px 80px;position:relative;z-index:1}
.section-tag{display:inline-flex;align-items:center;gap:6px;font-size:.7rem;font-weight:700;color:var(--brand);letter-spacing:.12em;text-transform:uppercase;padding:5px 14px;border-radius:999px;background:rgba(124,107,240,0.06);border:1px solid rgba(124,107,240,0.12);margin-bottom:16px}
.section-title{font-family:'Space Grotesk',sans-serif;font-size:2rem;font-weight:800;letter-spacing:-.03em;color:var(--text);margin-bottom:8px}
.section-sub{font-size:1rem;color:var(--text-sec);margin-bottom:36px;max-width:600px}

/* ── Model Cards ───────────────── */
.model-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
.m-card{background:rgba(255,255,255,0.92);border:1px solid var(--border);border-radius:14px;padding:20px;position:relative;overflow:hidden;transition:all .35s cubic-bezier(.23,1,.32,1);box-shadow:0 1px 4px rgba(0,0,0,0.03)}
.m-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:3px 3px 0 0}
.m-card:hover{transform:translateY(-4px);border-color:rgba(124,107,240,0.2);box-shadow:0 16px 48px rgba(0,0,0,0.07),0 0 0 1px rgba(124,107,240,0.06)}
.m-card-head{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.m-icon{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0}
.m-name{font-family:'Space Grotesk',sans-serif;font-size:.9rem;font-weight:700;color:var(--text)}
.m-org{font-size:.72rem;color:var(--text-muted);font-weight:500}
.m-params{font-family:'JetBrains Mono',monospace;font-size:.72rem;font-weight:700;padding:2px 8px;border-radius:6px;background:rgba(124,107,240,0.06);color:var(--brand);margin-left:auto;white-space:nowrap}
.m-desc{font-size:.78rem;color:var(--text-sec);line-height:1.6;margin-bottom:10px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.m-tags{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px}
.m-tag{font-size:.65rem;font-weight:600;padding:2px 7px;border-radius:5px;background:rgba(241,245,249,0.9);border:1px solid rgba(226,232,240,0.6);color:var(--text-sec)}
.m-foot{display:flex;align-items:center;justify-content:space-between;padding-top:10px;border-top:1px solid rgba(226,232,240,0.5)}
.m-gpu{font-size:.7rem;color:var(--text-muted);font-weight:500;display:flex;align-items:center;gap:4px}
.m-deploy{display:inline-flex;align-items:center;gap:4px;padding:5px 12px;border-radius:7px;border:none;cursor:pointer;font-size:.72rem;font-weight:700;color:#fff;background:linear-gradient(135deg,var(--brand),var(--brand-light));box-shadow:0 2px 10px rgba(124,107,240,0.2);transition:all .25s;text-decoration:none}
.m-deploy:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(124,107,240,0.3)}
.m-new{position:absolute;top:10px;right:12px;font-size:.6rem;font-weight:800;padding:1px 6px;border-radius:999px;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.25);color:#059669;text-transform:uppercase;letter-spacing:.04em}

/* ── Agent Cards ───────────────── */
.agents{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.a-card{background:rgba(255,255,255,0.9);border:1px solid var(--border);border-radius:14px;padding:20px;transition:all .3s cubic-bezier(.23,1,.32,1);box-shadow:0 1px 3px rgba(0,0,0,0.03)}
.a-card:hover{transform:translateY(-3px);border-color:rgba(124,107,240,0.2);box-shadow:0 12px 36px rgba(0,0,0,0.06)}
.a-icon{font-size:1.6rem;margin-bottom:10px;display:block}
.a-name{font-family:'Space Grotesk',sans-serif;font-size:.9rem;font-weight:700;color:var(--text);margin-bottom:4px}
.a-desc{font-size:.78rem;color:var(--text-sec);line-height:1.5;margin-bottom:8px}
.a-status{display:inline-flex;align-items:center;gap:5px;font-size:.7rem;font-weight:700;color:var(--accent);padding:3px 10px;border-radius:999px;background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.15)}

/* ── Providers ─────────────────── */
.providers{display:flex;gap:24px;flex-wrap:wrap;justify-content:center;align-items:center;margin-bottom:80px}
.provider{font-family:'Space Grotesk',sans-serif;font-size:.85rem;font-weight:600;color:var(--text-muted);padding:10px 20px;border-radius:10px;border:1px solid var(--border);background:rgba(255,255,255,0.6);transition:all .25s}
.provider:hover{border-color:rgba(124,107,240,0.2);color:var(--brand);transform:translateY(-1px)}

/* ── Bottom CTA ────────────────── */
.bottom-cta{text-align:center;padding:60px 24px 80px;position:relative;z-index:1}
.bottom-cta h2{font-family:'Space Grotesk',sans-serif;font-size:2rem;font-weight:800;letter-spacing:-.03em;margin-bottom:12px}
.bottom-cta p{color:var(--text-sec);margin-bottom:28px;font-size:1rem}

/* ── Footer ────────────────────── */
footer{border-top:1px solid var(--border);padding:24px 48px;display:flex;align-items:center;justify-content:space-between;color:var(--text-muted);font-size:.82rem;background:var(--bg);position:relative;z-index:1;flex-wrap:wrap;gap:12px}
footer a{color:var(--brand);text-decoration:none;font-weight:600}
.footer-links{display:flex;gap:20px}

/* ── Responsive ────────────────── */
@media(max-width:768px){
  nav{padding:14px 20px}
  .hero{padding:50px 20px 32px}
  .stats{flex-direction:column;border-radius:14px}
  .stat:not(:last-child)::after{width:60%;height:1px;top:auto;bottom:0;left:20%;right:auto}
  .section{padding:0 20px 60px}
  .model-grid{grid-template-columns:1fr}
  footer{padding:20px;flex-direction:column;text-align:center}
}
</style>
</head>
<body>
<div class="aurora"></div>
<div class="grid-bg"></div>

<nav>
  <div style="display:flex;align-items:center">
    <a href="/" class="logo">OrQuanta</a>
    <span class="logo-sub">Agentic GPU Cloud</span>
  </div>
  <div class="nav-r">
    <a href="/status" class="btn btn-ghost">Status</a>
    <a href="/docs" class="btn btn-ghost">API Docs</a>
    <a href="${appUrl}" class="btn btn-primary">Launch Dashboard →</a>
  </div>
</nav>

<div class="hero">
  <div class="live-badge fade-up"><span class="live-dot"></span> 5 AI Agents Online · 24+ Open-Source Models</div>
  <h1 class="fade-up fade-up-1">Deploy AI Models<br><span class="grad">67% Below AWS</span></h1>
  <p class="hero-sub fade-up fade-up-2">Submit goals in plain English. <strong>5 specialized AI agents</strong> handle GPU scheduling, cost optimization, self-healing, and forecasting — routing across <strong>AWS, GCP, Azure, Lambda, CoreWeave</strong> to find the cheapest GPU in seconds.</p>
  <div class="cta-row fade-up fade-up-3">
    <a href="${appUrl}" class="btn btn-primary" style="font-size:1rem;padding:14px 32px">Start Free →</a>
    <a href="/docs" class="btn btn-outline" style="font-size:1rem;padding:14px 28px">API Reference</a>
  </div>
  <div class="trust-line fade-up fade-up-4">Trusted by ML engineers worldwide · No credit card required</div>

  <div class="stats fade-up fade-up-4">
    <div class="stat"><div class="stat-val">67%</div><div class="stat-label">Below AWS</div></div>
    <div class="stat"><div class="stat-val">24+</div><div class="stat-label">AI Models</div></div>
    <div class="stat"><div class="stat-val">5</div><div class="stat-label">AI Agents</div></div>
    <div class="stat"><div class="stat-val">99.95%</div><div class="stat-label">SLA Uptime</div></div>
    <div class="stat"><div class="stat-val">&lt;30s</div><div class="stat-label">GPU Launch</div></div>
  </div>
</div>

<!-- AI Models Section -->
<div class="section">
  <div style="text-align:center;margin-bottom:40px">
    <div class="section-tag">🧠 Open-Source AI Models</div>
    <div class="section-title">One-Click Deploy. Any Model.</div>
    <div class="section-sub" style="margin:8px auto 0">Deploy the world's best open-source models to the cheapest GPU — automatically configured and optimized.</div>
  </div>
  <div class="model-grid">
    ${[
      ['🦙','LLaMA 3.1 405B','Meta AI','405B','Flagship open LLM. GPT-4 class reasoning, 128K context.',['Flagship','128K Ctx'],'8×A100','#7C6BF0',false],
      ['🔮','DeepSeek-V3','DeepSeek AI','671B MoE','SOTA MoE. Outperforms GPT-4o on coding & math.',['SOTA','MIT'],'8×H100','#8B5CF6',true],
      ['🧪','DeepSeek-R1','DeepSeek AI','671B MoE','Reasoning-first. Matches OpenAI o1 on complex tasks.',['Reasoning','CoT'],'8×H100','#10B981',true],
      ['💬','Mistral Large 2','Mistral AI','123B','Multilingual, 12 languages. Strong function calling.',['Multilingual','Apache'],'4×A100','#F472B6',false],
      ['📐','Qwen 2.5 72B','Alibaba','72B','Bilingual CN/EN. 128K context, strong reasoning.',['Bilingual','Apache'],'2×A100','#F59E0B',false],
      ['🖼️','FLUX.1 [dev]','BFL','12B','SOTA text-to-image. Photorealistic, typography-aware.',['Text-to-Image','12B'],'1×A100','#F472B6',false],
      ['🎙️','Whisper v3 Turbo','OpenAI','809M','8× faster ASR. 99+ languages. MIT licensed.',['ASR','99+ Lang'],'1×T4','#10B981',false],
      ['💻','DeepSeek-Coder-V2','DeepSeek AI','236B MoE','Best open code model. 338 languages, beats GPT-4o.',['338 Lang','MIT'],'4×A100','#F59E0B',true],
      ['🔬','InternVL 2.5','OpenGVLab','78B','Top multimodal. OCR, chart QA, visual reasoning.',['Multimodal','MIT'],'2×A100','#8B5CF6',true],
      ['⚡','Phi-4','Microsoft','14B','Small model, big results. Beats 5× larger models.',['Compact','MIT'],'1×4090','#7C6BF0',true],
      ['🎬','Stable Video','Stability','1.5B','Image-to-video generation. 14-25 frames.',['Video Gen','SVD'],'1×A100','#F472B6',false],
      ['📊','GTE-Qwen2 7B','DAMO','7B','#1 MTEB embeddings. 8K context for documents.',['MTEB #1','8K Ctx'],'1×T4','#06B6D4',false],
    ].map(([icon,name,org,params,desc,tags,gpu,color,isNew]) => `
    <div class="m-card" style="animation:fadeUp .5s both;animation-delay:${Math.random()*.3}s">
      <div style="position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,${color},${color}60);border-radius:3px 3px 0 0"></div>
      ${isNew?'<span class="m-new">New</span>':''}
      <div class="m-card-head">
        <div class="m-icon" style="background:${color}12;border:1px solid ${color}20">${icon}</div>
        <div><div class="m-name">${name}</div><div class="m-org">${org}</div></div>
        <span class="m-params">${params}</span>
      </div>
      <div class="m-desc">${desc}</div>
      <div class="m-tags">${tags.map(t=>`<span class="m-tag">${t}</span>`).join('')}</div>
      <div class="m-foot">
        <span class="m-gpu">⚡ ${gpu}</span>
        <a href="${appUrl}" class="m-deploy">Deploy →</a>
      </div>
    </div>`).join('')}
  </div>
  <div style="text-align:center;margin-top:24px">
    <a href="${appUrl}" class="btn btn-outline" style="font-size:.9rem">View All 24+ Models →</a>
  </div>
</div>

<!-- Agents Section -->
<div class="section">
  <div style="text-align:center;margin-bottom:36px">
    <div class="section-tag">🤖 AI-Powered Infrastructure</div>
    <div class="section-title">5 Autonomous Agents</div>
    <div class="section-sub" style="margin:8px auto 0">Submit goals — agents handle everything from GPU selection to cost optimization.</div>
  </div>
  <div class="agents">
    ${[
      ['🧠','OrMind Orchestrator','Decomposes goals, routes to agents with RL-based decisions'],
      ['📅','Scheduler Agent','Packs GPU jobs optimally across time windows and providers'],
      ['💰','Cost Optimizer','Monitors spend in real-time, auto-switches to cheaper instances'],
      ['🔧','Healing Agent','Detects anomalies, auto-restarts failed GPU workloads'],
      ['📈','Forecast Agent','Predicts costs & demand 6hrs ahead with 92% accuracy'],
    ].map(([icon,name,desc],i) => `
    <div class="a-card" style="animation:fadeUp .5s both;animation-delay:${i*.08}s">
      <span class="a-icon">${icon}</span>
      <div class="a-name">${name}</div>
      <div class="a-desc">${desc}</div>
      <span class="a-status"><span style="width:6px;height:6px;border-radius:50%;background:#10B981;display:inline-block"></span> Online</span>
    </div>`).join('')}
  </div>
</div>

<!-- Providers -->
<div class="section" style="text-align:center;padding-bottom:20px">
  <div class="section-tag" style="margin-bottom:24px">☁️ Multi-Cloud Routing</div>
  <div class="providers">
    ${['AWS','Google Cloud','Azure','Lambda Labs','CoreWeave','RunPod','Vast.ai','FluidStack'].map(p=>
      `<div class="provider">${p}</div>`
    ).join('')}
  </div>
</div>

<!-- Bottom CTA -->
<div class="bottom-cta">
  <h2>Ready to Deploy?</h2>
  <p>Start free — no credit card required. Deploy your first model in under 30 seconds.</p>
  <a href="${appUrl}" class="btn btn-primary" style="font-size:1.1rem;padding:16px 40px">Launch OrQuanta Free →</a>
</div>

<footer>
  <div>OrQuanta Agentic v1.0 · <a href="mailto:hello@orquanta.com">hello@orquanta.com</a></div>
  <div class="footer-links">
    <a href="/docs">API Docs</a>
    <a href="/status">Status</a>
    <a href="${appUrl}">Dashboard</a>
  </div>
</footer>
</body>
</html>`, {
    status: 200,
    headers: { "Content-Type": "text/html;charset=UTF-8", ...SECURITY_HEADERS },
  });
}


function statusPage(healthData) {
  const isHealthy = healthData && healthData.status === 'healthy';
  const statusColor = isHealthy ? '#10B981' : '#EF4444';
  const statusText = isHealthy ? 'All Systems Operational' : 'Degraded Performance';
  const version = healthData && healthData.version ? healthData.version : '—';
  const ts = healthData && healthData.timestamp ? new Date(healthData.timestamp).toUTCString() : new Date().toUTCString();

  return new Response(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OrQuanta — API Status</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#F8FAFC;color:#0F172A;font-family:'Inter',sans-serif;min-height:100vh;display:flex;flex-direction:column}
.bg{position:fixed;inset:0;background:radial-gradient(ellipse 70% 50% at 50% -10%,rgba(0,145,255,.05),transparent 70%);pointer-events:none;z-index:0}
nav{display:flex;align-items:center;justify-content:space-between;padding:18px 40px;border-bottom:1px solid rgba(0,0,0,.06);background:rgba(255,255,255,.9);backdrop-filter:blur(16px);position:relative;z-index:1}
.logo{font-family:'Space Grotesk',sans-serif;font-size:1.4rem;font-weight:800;background:linear-gradient(135deg,#0091FF,#7B2FFF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;text-decoration:none}
.back{font-size:.85rem;color:#0091FF;text-decoration:none;font-weight:600;padding:8px 16px;border:1px solid rgba(0,145,255,.3);border-radius:8px;transition:all .2s}.back:hover{background:rgba(0,145,255,.06)}
main{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;padding:60px 24px;position:relative;z-index:1}
.status-hero{text-align:center;margin-bottom:48px}
.status-pill{display:inline-flex;align-items:center;gap:10px;padding:10px 24px;border-radius:999px;background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);margin-bottom:20px}
.status-pill.degraded{background:rgba(239,68,68,.08);border-color:rgba(239,68,68,.25)}
.status-dot{width:10px;height:10px;border-radius:50%;background:${statusColor};box-shadow:0 0 10px ${statusColor};animation:pulse 2s infinite}
.status-label{font-family:'Space Grotesk',sans-serif;font-size:1rem;font-weight:700;color:${statusColor}}
h1{font-family:'Space Grotesk',sans-serif;font-size:2.5rem;font-weight:800;letter-spacing:-.02em;color:#0F172A;margin-bottom:8px}
.sub{color:#64748B;font-size:1rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;max-width:900px;width:100%;margin-bottom:40px}
.card{background:#FFFFFF;border:1px solid rgba(0,0,0,.08);border-radius:14px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.card-title{font-family:'Space Grotesk',sans-serif;font-size:.9rem;font-weight:700;color:#0F172A;text-transform:uppercase;letter-spacing:.04em}
.tag{font-size:.75rem;font-weight:600;padding:3px 10px;border-radius:6px}
.tag.ok{background:rgba(16,185,129,.1);color:#10B981}
.tag.warn{background:rgba(239,68,68,.1);color:#EF4444}
.metric{font-family:'Space Grotesk',sans-serif;font-size:2rem;font-weight:800;color:#0F172A}
.metric-sub{font-size:.82rem;color:#64748B;margin-top:4px}
.ts{font-size:.8rem;color:#94A3B8;text-align:center;margin-top:8px}
.links{display:flex;gap:12px;margin-top:16px}
.link-btn{display:inline-flex;align-items:center;gap:6px;padding:10px 22px;border-radius:8px;font-size:.875rem;font-weight:600;text-decoration:none;transition:all .2s;border:1px solid rgba(0,0,0,.12);color:#475569;background:#fff}
.link-btn:hover{border-color:rgba(0,145,255,.4);color:#0091FF}
.link-btn.primary{background:linear-gradient(135deg,#0091FF,#7B2FFF);color:#fff;border:none;box-shadow:0 4px 20px rgba(0,145,255,.2)}
.link-btn.primary:hover{opacity:.9;transform:translateY(-1px)}
footer{padding:20px 40px;text-align:center;color:#94A3B8;font-size:.82rem;border-top:1px solid rgba(0,0,0,.06);background:#F8FAFC;position:relative;z-index:1}
footer a{color:#0091FF;text-decoration:none}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.4)}}
</style>
</head>
<body>
<div class="bg"></div>
<nav>
  <a href="/" class="logo">OrQuanta</a>
  <a href="/" class="back">&larr; Home</a>
</nav>
<main>
  <div class="status-hero">
    <div class="status-pill ${isHealthy ? '' : 'degraded'}">
      <span class="status-dot"></span>
      <span class="status-label">${statusText}</span>
    </div>
    <h1>API Status</h1>
    <p class="sub">Real-time health of the OrQuanta platform</p>
  </div>
  <div class="cards">
    <div class="card">
      <div class="card-header">
        <span class="card-title">API Backend</span>
        <span class="tag ${isHealthy ? 'ok' : 'warn'}">${isHealthy ? 'Operational' : 'Degraded'}</span>
      </div>
      <div class="metric">${isHealthy ? '✓' : '✗'}</div>
      <div class="metric-sub">FastAPI — Render Singapore</div>
    </div>
    <div class="card">
      <div class="card-header">
        <span class="card-title">Version</span>
        <span class="tag ok">Live</span>
      </div>
      <div class="metric" style="font-size:1.5rem">${version}</div>
      <div class="metric-sub">Latest stable release</div>
    </div>
    <div class="card">
      <div class="card-header">
        <span class="card-title">Edge Worker</span>
        <span class="tag ok">Operational</span>
      </div>
      <div class="metric">✓</div>
      <div class="metric-sub">Cloudflare — Global CDN</div>
    </div>
    <div class="card">
      <div class="card-header">
        <span class="card-title">Last Check</span>
        <span class="tag ok">Live</span>
      </div>
      <div class="metric" style="font-size:1rem;word-break:break-all">${ts}</div>
      <div class="metric-sub">UTC timestamp</div>
    </div>
  </div>
  <div class="links">
    <a href="/docs" class="link-btn">API Docs &rarr;</a>
    <a href="/app" class="link-btn primary">Open Dashboard &rarr;</a>
  </div>
  <p class="ts">Auto-fetched from live backend &mdash; no caching</p>
</main>
<footer>OrQuanta Agentic v1.0 &middot; <a href="mailto:hello@orquanta.com">hello@orquanta.com</a></footer>
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

    // Canonical www redirect
    if (url.hostname === 'www.orquanta.com') {
      return Response.redirect('https://orquanta.com' + url.pathname + url.search, 301);
    }

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: { ...CORS_HEADERS, ...SECURITY_HEADERS } });
    }

    // Root landing page  -  marketing page served at the edge
    if (path === "/") return landingPage(env);

    // /status  -  beautiful HTML status page (fetches /health from backend)
    if (path === "/status") {
      let healthData = null;
      try {
        const backend = env.BACKEND_URL || "https://orquanta-sg.onrender.com";
        const res = await fetch(`${backend}/health`, { method: "GET", signal: AbortSignal.timeout(8000) });
        if (res.ok) healthData = await res.json();
      } catch (_) { /* backend may be cold-starting; show degraded */ }
      return statusPage(healthData);
    }

    // Cloudflare Pages SPA  -  /app/* served from edge CDN (fast global load)
    // Vite builds with base:'/app/', so built index.html references /app/assets/chunk.js
    // Pages deploys flat dist/ where assets are at /assets/chunk.js (no /app prefix)
    // => Strip /app prefix for ALL Pages requests so assets resolve correctly
    const pagesUrl = env.PAGES_URL || "https://orquanta-app.pages.dev";
    if (path.startsWith("/app")) {
      const pagesPath = path.replace(/^\/app/, "") || "/";
      const pagesTarget = `${pagesUrl}${pagesPath}${url.search}`;
      const proxied = new Request(pagesTarget, {
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
          JSON.stringify({ error: "Pages error", detail: err.message }),
          { status: 502, headers: { "Content-Type": "application/json", ...CORS_HEADERS } }
        );
      }
    }

    // /register -> /app (React handles registration)
    if (path === "/register" || path === "/signup") {
      return Response.redirect(url.origin + '/app', 302);
    }

    // API route check  -  proxy to backend
    // For /docs and /redoc use relaxed CSP so SwaggerUI/ReDoc CDN scripts load correctly
    if (path === "/docs" || path === "/redoc" || path === "/openapi.json") {
      const proxied = new Request(
        `${env.BACKEND_URL || "https://orquanta-sg.onrender.com"}${url.pathname}${url.search}`,
        { method: request.method, headers: request.headers, redirect: "follow" }
      );
      try {
        const resp = await fetch(proxied);
        return addHeaders(resp, CORS_HEADERS, DOCS_SECURITY_HEADERS);
      } catch (err) {
        return new Response(
          JSON.stringify({ error: "Docs unavailable", detail: err.message }),
          { status: 502, headers: { "Content-Type": "application/json", ...CORS_HEADERS } }
        );
      }
    }

    if (isApiRoute(path)) return proxyToBackend(request, env);

    // FastAPI backend on Render Singapore  -  all other routes
    return proxyToBackend(request, env);
  },

  // Cron: every 5 min  -  keeps Render free tier alive (prevents 30-60s cold starts)
  async scheduled(_event, env, ctx) {
    const backend = env.BACKEND_URL || "https://orquanta-sg.onrender.com";
    ctx.waitUntil(
      fetch(`${backend}/health`, { method: "GET" }).then(r =>
        console.log(`[keepalive] ${new Date().toISOString()} -> HTTP ${r.status}`)
      ).catch(e =>
        console.error(`[keepalive] failed: ${e.message}`)
      )
    );
  },
};
