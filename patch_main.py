"""Patch v4/api/main.py to add OAuth, Help, Contact, Pricing endpoints."""
import pathlib, sys

TARGET = pathlib.Path(__file__).parent / 'v4' / 'api' / 'main.py'
content = TARGET.read_bytes().decode('utf-8', errors='replace')

if 'google_login' in content:
    print('Already patched!')
    sys.exit(0)

lines = content.splitlines(keepends=True)
print(f'Patching {len(lines)}-line file...')

NEW_CODE = '''

# ── Google + GitHub OAuth ─────────────────────────────────────────────────
try:
    from authlib.integrations.starlette_client import OAuth as _OAuth
    from starlette.middleware.sessions import SessionMiddleware
    import hashlib as _hashlib

    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv("SESSION_SECRET", os.getenv("SECRET_KEY", "orquanta-secret-2026")),
    )
    _oauth = _OAuth()
    _oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    _oauth.register(
        name="github",
        client_id=os.getenv("GITHUB_CLIENT_ID"),
        client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email"},
    )

    def _upsert_oauth_user(email, name):
        from .middleware.auth import _get_db
        import secrets as _sec
        conn = _get_db()
        row = conn.execute("SELECT id, email, role FROM users WHERE email = ?", (email.lower(),)).fetchone()
        if row:
            conn.close()
            return {"id": row[0], "email": row[1], "role": row[2]}
        uid = _sec.token_hex(16)
        salt = _sec.token_hex(8)
        fake_pw = _hashlib.sha256((_sec.token_hex(32) + salt).encode()).hexdigest()
        conn.execute(
            "INSERT INTO users (id, email, name, hashed_pw, salt, role, created_at) VALUES (?,?,?,?,?,?,?)",
            (uid, email.lower(), name, fake_pw, salt, "user", datetime.now(timezone.utc).isoformat()),
        )
        conn.commit(); conn.close()
        return {"id": uid, "email": email.lower(), "role": "user"}

    @app.get("/auth/google", tags=["Auth"], include_in_schema=False)
    async def google_login(request: Request):
        return await _oauth.google.authorize_redirect(
            request, os.getenv("GOOGLE_REDIRECT_URI", "https://orquanta.com/auth/google/callback")
        )

    @app.get("/auth/google/callback", tags=["Auth"], include_in_schema=False)
    async def google_callback(request: Request):
        try:
            token = await _oauth.google.authorize_access_token(request)
            info = token.get("userinfo") or {}
            email = info.get("email", "")
            name = info.get("name", email.split("@")[0])
            if not email: return RedirectResponse(url="/app?error=no_email")
            u = _upsert_oauth_user(email, name)
            at = create_access_token(u["id"], u["email"], u["role"])
            return RedirectResponse(url=f"/app?token={at}", status_code=302)
        except Exception as exc:
            logger.warning(f"Google OAuth error: {exc}")
            return RedirectResponse(url="/app?error=oauth_failed", status_code=302)

    @app.get("/auth/github", tags=["Auth"], include_in_schema=False)
    async def github_login(request: Request):
        return await _oauth.github.authorize_redirect(
            request, os.getenv("GITHUB_REDIRECT_URI", "https://orquanta.com/auth/github/callback")
        )

    @app.get("/auth/github/callback", tags=["Auth"], include_in_schema=False)
    async def github_callback(request: Request):
        try:
            token = await _oauth.github.authorize_access_token(request)
            resp = await _oauth.github.get("user", token=token); profile = resp.json()
            er = await _oauth.github.get("user/emails", token=token)
            emails = er.json() if er.status_code == 200 else []
            email = next((e["email"] for e in emails if isinstance(e, dict) and e.get("primary")), profile.get("email") or "")
            name = profile.get("name") or profile.get("login", "GitHub User")
            if not email: return RedirectResponse(url="/app?error=no_email")
            u = _upsert_oauth_user(email, name)
            at = create_access_token(u["id"], u["email"], u["role"])
            return RedirectResponse(url=f"/app?token={at}", status_code=302)
        except Exception as exc:
            logger.warning(f"GitHub OAuth error: {exc}")
            return RedirectResponse(url="/app?error=oauth_failed", status_code=302)

    logger.info("Google + GitHub OAuth registered.")
except ImportError:
    logger.warning("authlib not installed -- OAuth disabled. pip install authlib httpx")


# ── Help Center ───────────────────────────────────────────────────────────

@app.get("/help", response_class=HTMLResponse, include_in_schema=False)
async def help_page():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>OrQuanta Help Center</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#050608;color:#e2e8f0;font-family:Inter,sans-serif;padding:40px 20px}
.container{max-width:800px;margin:0 auto}
h1{font-family:Space Grotesk,sans-serif;font-size:2rem;background:linear-gradient(135deg,#00D4FF,#7B2FFF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px}
.subtitle{color:#64748b;margin-bottom:40px}
.card{background:rgba(15,22,36,.8);border:1px solid rgba(0,212,255,.15);border-radius:16px;padding:24px;margin-bottom:20px}
.card h2{font-family:Space Grotesk,sans-serif;color:#00D4FF;margin-bottom:12px}
.card p{color:#94a3b8;line-height:1.7;font-size:.95rem;margin-bottom:8px}
.cta{display:inline-block;background:linear-gradient(135deg,#00D4FF,#7B2FFF);color:#fff;padding:12px 24px;border-radius:10px;text-decoration:none;font-weight:600;margin-top:12px}
.back{color:#00D4FF;text-decoration:none;display:block;margin-bottom:32px}</style>
</head><body><div class="container">
<a href="/demo" class="back">&larr; Back to OrQuanta</a>
<h1>Help Center</h1><p class="subtitle">Everything you need to get started with OrQuanta</p>
<div class="card"><h2>&#x1F680; Getting Started</h2>
<p>1. Create free account at /auth/register &mdash; no credit card. 14-day trial.</p>
<p>2. Submit a goal in plain English e.g. &ldquo;Fine-tune Llama 3 8B, cost under $80&rdquo;</p>
<p>3. OrQuanta&amprsquo;s 5 AI agents find cheapest GPU and start execution automatically.</p>
<p>4. Monitor on dashboard. Healing Agent auto-recovers failures in 8 seconds.</p></div>
<div class="card"><h2>&#x1F916; The 5 AI Agents</h2>
<p><strong style="color:#e2e8f0">OrMind Orchestrator</strong> &mdash; Creates execution plan from your goal</p>
<p><strong style="color:#e2e8f0">Scheduler Agent</strong> &mdash; Picks best GPU and queues job</p>
<p><strong style="color:#e2e8f0">Cost Optimizer</strong> &mdash; Finds cheapest provider in real-time across 6 clouds</p>
<p><strong style="color:#e2e8f0">Healing Agent</strong> &mdash; Monitors every 30s, auto-recovers failures</p>
<p><strong style="color:#e2e8f0">Forecast Agent</strong> &mdash; Pre-provisions capacity ahead of demand</p></div>
<div class="card"><h2>&#x1F4B0; Pricing</h2>
<p><strong style="color:#00FF88">Starter</strong> &mdash; $99/mo &mdash; up to $5k GPU spend</p>
<p><strong style="color:#00D4FF">Pro</strong> &mdash; $499/mo &mdash; up to $50k GPU spend</p>
<p><strong style="color:#7B2FFF">Enterprise</strong> &mdash; Custom &mdash; unlimited GPU spend</p>
<a href="/pricing" class="cta">View Full Pricing &rarr;</a></div>
<div class="card"><h2>&#x1F4E7; Contact &amp; Support</h2>
<p>Have a question? We respond within 24 hours.</p>
<a href="/contact" class="cta">Contact Support &rarr;</a>
<p style="margin-top:12px;color:#64748b;font-size:.85rem">Email: <a href="mailto:orquanta.founder@gmail.com" style="color:#00D4FF">orquanta.founder@gmail.com</a></p></div>
</div></body></html>""")


# ── Contact page ──────────────────────────────────────────────────────────

@app.get("/contact", response_class=HTMLResponse, include_in_schema=False)
async def contact_page():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Contact OrQuanta</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#050608;color:#e2e8f0;font-family:Inter,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:rgba(15,22,36,.9);border:1px solid rgba(0,212,255,.2);border-radius:20px;padding:48px 40px;width:100%;max-width:480px;box-shadow:0 0 60px rgba(0,212,255,.1)}
h1{font-family:Space Grotesk,sans-serif;font-size:1.8rem;font-weight:700;text-align:center;margin-bottom:8px}
.sub{color:#64748b;text-align:center;margin-bottom:32px}
label{display:block;color:#94a3b8;font-size:.85rem;margin-bottom:6px;margin-top:16px}
input,textarea{width:100%;background:rgba(0,0,0,.4);border:1px solid rgba(0,212,255,.2);border-radius:8px;color:#e2e8f0;padding:12px 16px;font-size:1rem;outline:none}
textarea{min-height:120px;resize:vertical}
.btn{width:100%;background:linear-gradient(135deg,#00D4FF,#7B2FFF);border:none;border-radius:10px;color:#fff;font-size:1rem;font-weight:600;padding:14px;cursor:pointer;margin-top:24px}
.back{color:#00D4FF;text-decoration:none;display:block;text-align:center;margin-top:20px}
.success{display:none;text-align:center;padding:20px;color:#00FF88}
.direct{margin-top:24px;padding-top:24px;border-top:1px solid rgba(255,255,255,.08);text-align:center}
.direct a{color:#00D4FF;text-decoration:none;font-weight:600}</style>
</head><body><div class="card">
<h1>Contact Us</h1><p class="sub">We respond within 24 hours</p>
<div id="fs">
<label>Your Name</label><input type="text" id="cn" placeholder="Your name">
<label>Email Address</label><input type="email" id="ce" placeholder="you@company.com">
<label>Message</label><textarea id="cm" placeholder="Tell us what you need..."></textarea>
<button class="btn" onclick="send()">Send Message &rarr;</button>
<div class="direct"><p style="color:#64748b;font-size:.85rem;margin-bottom:8px">Or email directly:</p>
<a href="mailto:orquanta.founder@gmail.com">orquanta.founder@gmail.com</a></div></div>
<div class="success" id="ok">
<div style="font-size:3rem;margin-bottom:16px">&#x2705;</div>
<h2>Message Sent!</h2><p style="color:#64748b">We will reply within 24 hours.</p></div>
<a href="/demo" class="back">&larr; Back to OrQuanta</a>
</div><script>
function send(){
  var n=document.getElementById('cn').value,e=document.getElementById('ce').value,m=document.getElementById('cm').value;
  if(!n||!e||!m){alert('Please fill in all fields');return;}
  window.location.href='mailto:orquanta.founder@gmail.com?subject='+encodeURIComponent('OrQuanta Inquiry from '+n)+'&body='+encodeURIComponent('Name: '+n+'\\nEmail: '+e+'\\n\\nMessage:\\n'+m);
  document.getElementById('fs').style.display='none';
  document.getElementById('ok').style.display='block';
}
</script></body></html>""")


# ── Pricing page ──────────────────────────────────────────────────────────

@app.get("/pricing", response_class=HTMLResponse, include_in_schema=False)
async def pricing_html_page():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>OrQuanta Pricing</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#050608;color:#e2e8f0;font-family:Inter,sans-serif;padding:60px 20px}
.container{max-width:900px;margin:0 auto}h1{font-family:Space Grotesk,sans-serif;font-size:2.2rem;text-align:center;margin-bottom:8px}
.sub{color:#64748b;text-align:center;margin-bottom:16px}.badge-row{text-align:center;margin-bottom:48px}
.badge{display:inline-block;background:rgba(0,255,136,.1);border:1px solid rgba(0,255,136,.3);color:#00FF88;padding:6px 16px;border-radius:20px}
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px;margin-bottom:48px}
.plan{background:rgba(15,22,36,.8);border:1px solid rgba(0,212,255,.15);border-radius:20px;padding:32px 28px}
.plan.featured{border-color:rgba(0,212,255,.5);box-shadow:0 0 40px rgba(0,212,255,.1)}
.popular{display:inline-block;background:linear-gradient(135deg,#00D4FF,#7B2FFF);color:#fff;font-size:.75rem;padding:3px 12px;border-radius:20px;margin-bottom:16px}
.pn{font-family:Space Grotesk,sans-serif;font-size:1.1rem;font-weight:700;margin-bottom:8px}
.pr{font-family:Space Grotesk,sans-serif;font-size:2.5rem;font-weight:700;color:#00D4FF;margin-bottom:4px}
.pr span{font-size:1rem;color:#64748b;font-weight:400}
.lm{color:#64748b;font-size:.85rem;margin-bottom:24px;padding-bottom:24px;border-bottom:1px solid rgba(255,255,255,.08)}
.ft{display:flex;gap:10px;margin-bottom:12px;font-size:.9rem;color:#94a3b8}
.ck{color:#00FF88;flex-shrink:0}
.pb{display:block;text-align:center;padding:13px;border-radius:10px;text-decoration:none;font-weight:600;font-family:Space Grotesk,sans-serif;margin-top:24px}
.pri{background:linear-gradient(135deg,#00D4FF,#7B2FFF);color:#fff}
.sec{background:rgba(255,255,255,.06);color:#e2e8f0;border:1px solid rgba(255,255,255,.12)}
.faq{margin-top:48px}.faq h2{font-family:Space Grotesk,sans-serif;font-size:1.5rem;text-align:center;margin-bottom:32px}
.fi{background:rgba(15,22,36,.6);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:20px 24px;margin-bottom:12px}
.fq{font-weight:600;margin-bottom:8px;color:#e2e8f0}.fa{color:#94a3b8;line-height:1.6}
.back{color:#00D4FF;text-decoration:none;display:block;text-align:center;margin-bottom:40px}</style>
</head><body><div class="container">
<a href="/demo" class="back">&larr; Back to OrQuanta</a>
<h1>Simple, Transparent Pricing</h1>
<p class="sub">Pay for what you use. Cancel anytime.</p>
<div class="badge-row"><span class="badge">14-Day Free Trial &mdash; No Credit Card Required</span></div>
<div class="plans">
<div class="plan"><div class="pn">Starter</div><div class="pr">$99<span>/month</span></div>
<div class="lm">Up to $5,000 GPU spend managed/month</div>
<div class="ft"><span class="ck">&#x2713;</span>5 AI agents</div>
<div class="ft"><span class="ck">&#x2713;</span>Multi-cloud routing (6 providers)</div>
<div class="ft"><span class="ck">&#x2713;</span>Self-healing job recovery</div>
<div class="ft"><span class="ck">&#x2713;</span>Cost tracking and alerts</div>
<div class="ft"><span class="ck">&#x2713;</span>Email support (24hr response)</div>
<a href="/auth/register" class="pb sec">Start Free Trial &rarr;</a></div>
<div class="plan featured"><div class="popular">Most Popular</div>
<div class="pn">Pro</div><div class="pr">$499<span>/month</span></div>
<div class="lm">Up to $50,000 GPU spend managed/month</div>
<div class="ft"><span class="ck">&#x2713;</span>Everything in Starter</div>
<div class="ft"><span class="ck">&#x2713;</span>Carbon CO2 tracking per job</div>
<div class="ft"><span class="ck">&#x2713;</span>Advanced cost analytics</div>
<div class="ft"><span class="ck">&#x2713;</span>Priority support (4hr response)</div>
<div class="ft"><span class="ck">&#x2713;</span>Python SDK + CLI</div>
<div class="ft"><span class="ck">&#x2713;</span>Webhook notifications</div>
<a href="/auth/register" class="pb pri">Start Free Trial &rarr;</a></div>
<div class="plan"><div class="pn">Enterprise</div><div class="pr" style="font-size:2rem">Custom</div>
<div class="lm">Unlimited GPU spend managed</div>
<div class="ft"><span class="ck">&#x2713;</span>Everything in Pro</div>
<div class="ft"><span class="ck">&#x2713;</span>Dedicated account manager</div>
<div class="ft"><span class="ck">&#x2713;</span>Custom SLA and uptime guarantee</div>
<div class="ft"><span class="ck">&#x2713;</span>SSO and team management</div>
<div class="ft"><span class="ck">&#x2713;</span>On-premise deployment option</div>
<div class="ft"><span class="ck">&#x2713;</span>1hr support response time</div>
<a href="mailto:orquanta.founder@gmail.com" class="pb sec">Contact Sales &rarr;</a></div>
</div>
<div class="faq"><h2>Frequently Asked Questions</h2>
<div class="fi"><div class="fq">Do I need a credit card to start?</div><div class="fa">No. 14-day free trial, no credit card required.</div></div>
<div class="fi"><div class="fq">How does billing work?</div><div class="fa">You pay OrQuanta a monthly management fee. GPU costs billed directly by providers, no markup.</div></div>
<div class="fi"><div class="fq">Is my data secure?</div><div class="fa">HTTPS encrypted. API keys never logged. HMAC-signed audit trail for every agent action.</div></div>
<div class="fi"><div class="fq">Can I cancel anytime?</div><div class="fa">Yes. Cancel anytime. Data exportable for 30 days after cancellation.</div></div>
<div class="fi"><div class="fq">Which GPU providers are supported?</div><div class="fa">Lambda Labs, RunPod, CoreWeave, AWS, Google Cloud, Azure. Vast.ai coming soon.</div></div>
</div></div></body></html>""")

'''

insert_idx = 583
new_lines = lines[:insert_idx] + [NEW_CODE] + lines[insert_idx:]
result = ''.join(new_lines)
TARGET.write_text(result, encoding='utf-8')
final_count = len(result.splitlines())
print(f'Done! File now has {final_count} lines (was {len(lines)}).')
for kw in ['google_login', 'github_login', 'help_page', 'contact_page', 'pricing_html_page']:
    print(f'  {kw}: {"FOUND" if kw in result else "MISSING"}')
