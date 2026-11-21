import os

checks = []

# 1. Reset token not in INFO log
with open("api/main.py", encoding="utf-8") as f:
    content = f.read()
info_lines = [l for l in content.splitlines() if "logger.info" in l and "URL={reset_url}" in l]
if not info_lines:
    checks.append("PASS: Reset token removed from INFO log")
else:
    checks.append("FAIL: Reset token still in INFO log: " + str(info_lines))

# 2. WebSocket auth present
with open("api/websocket/agent_stream.py", encoding="utf-8") as f:
    ws = f.read()
if "WS_AUTH_REQUIRED" in ws and "_verify_ws_token" in ws and "code=4001" in ws:
    checks.append("PASS: WebSocket JWT auth implemented")
else:
    checks.append("FAIL: WebSocket auth missing")

# 3. Billing hard-fail in production
with open("api/routers/billing.py", encoding="utf-8") as f:
    billing = f.read()
if "is_production" in billing and "status_code=500" in billing:
    checks.append("PASS: Billing webhook hard-fails in production")
else:
    checks.append("FAIL: Billing webhook still soft-warns")

# 4. No bomax in .env.example
with open(".env.example", encoding="utf-8") as f:
    env = f.read()
if "bomax" not in env.lower():
    checks.append("PASS: .env.example clean of bomax")
else:
    checks.append("FAIL: bomax still in .env.example")

# 5. Rate limiter X-Forwarded-For
with open("api/middleware/rate_limit.py", encoding="utf-8") as f:
    rl = f.read()
if "X-Forwarded-For" in rl and "_evict_stale" in rl:
    checks.append("PASS: Rate limiter proxy-aware + eviction")
else:
    checks.append("FAIL: Rate limiter missing X-Forwarded-For or eviction")

# 6. Safety governor blocks high-cost
with open("agents/safety_governor.py", encoding="utf-8") as f:
    sg = f.read()
if "PermissionError" in sg and "REQUIRE_HIGH_COST_APPROVAL" in sg:
    checks.append("PASS: Safety governor blocks high-cost actions")
else:
    checks.append("FAIL: Safety governor still auto-approves")

# 7. DB default creds removed
with open("database/models.py", encoding="utf-8") as f:
    db = f.read()
if "orquanta:orquanta@localhost" not in db:
    checks.append("PASS: Hardcoded DB creds removed from models.py")
else:
    checks.append("FAIL: Hardcoded DB creds still in models.py")

# 8. Open-source files exist
for f in ["../LICENSE", "../CONTRIBUTING.md", "../SECURITY.md", "../CHANGELOG.md", "../docker-compose.dev.yml"]:
    if os.path.exists(f):
        checks.append("PASS: " + f + " exists")
    else:
        checks.append("FAIL: " + f + " MISSING")

for c in checks:
    print(c)

passed = sum(1 for c in checks if c.startswith("PASS"))
print("\nTotal: " + str(passed) + "/" + str(len(checks)) + " passed")
if passed == len(checks):
    print("ALL PHASE 1 CHECKS PASSED")
else:
    print("SOME CHECKS FAILED - review above")
