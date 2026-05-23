#!/usr/bin/env bash
# OrQuanta — End-to-end health verification
# Run from local machine OR on Oracle instance.
# Pass --local to test Oracle directly (port 8000), otherwise tests via orquanta.com.
#
# Usage:
#   bash infra/oracle/verify.sh           # test production (orquanta.com)
#   bash infra/oracle/verify.sh --local   # test Oracle direct (needs SSH tunnel or run on Oracle)

set -euo pipefail

MODE="${1:-}"
if [ "$MODE" = "--local" ]; then
  BASE="http://127.0.0.1:8000"
  echo "Verifying Oracle direct (${BASE})..."
else
  BASE="https://orquanta.com"
  echo "Verifying production (${BASE})..."
fi

PASS=0
FAIL=0

check() {
  local DESC="$1"
  local URL="$2"
  local EXPECT="$3"

  STATUS=$(curl -s -o /tmp/orquanta_verify_body -w "%{http_code}" "${URL}" 2>/dev/null || echo "000")
  BODY=$(cat /tmp/orquanta_verify_body 2>/dev/null || echo "")

  if [ "$STATUS" = "$EXPECT" ]; then
    echo "  PASS  HTTP $STATUS  $DESC"
    PASS=$((PASS+1))
  else
    echo "  FAIL  HTTP $STATUS (expected $EXPECT)  $DESC"
    if [ -n "$BODY" ]; then
      echo "        Body: $(echo "$BODY" | head -c 200)"
    fi
    FAIL=$((FAIL+1))
  fi
}

check_contains() {
  local DESC="$1"
  local URL="$2"
  local NEEDLE="$3"

  BODY=$(curl -s "${URL}" 2>/dev/null || echo "")
  if echo "$BODY" | grep -q "$NEEDLE"; then
    echo "  PASS  contains '$NEEDLE'  $DESC"
    PASS=$((PASS+1))
  else
    echo "  FAIL  missing '$NEEDLE'  $DESC"
    echo "        Body: $(echo "$BODY" | head -c 300)"
    FAIL=$((FAIL+1))
  fi
}

echo ""
echo "--- Core endpoints ---"
check          "Health check"          "${BASE}/health"           "200"
check_contains "Health reports healthy" "${BASE}/health"          "healthy"
check          "API docs available"   "${BASE}/docs"             "200"

echo ""
echo "--- Auth endpoints ---"
check "Register page"  "${BASE}/auth/register" "200"
check "Login endpoint" "${BASE}/auth/login"    "405"   # GET on POST-only returns 405

echo ""
echo "--- API routes ---"
check "Goals (unauth → 401)"   "${BASE}/api/v1/goals"   "401"
check "Jobs  (unauth → 401)"   "${BASE}/api/v1/jobs"    "401"
check "Pricing (public → 200)" "${BASE}/api/v1/pricing" "200"

if [ "$MODE" != "--local" ]; then
  echo ""
  echo "--- Frontend (Cloudflare Pages) ---"
  check          "SPA root"            "${BASE}/app"     "200"
  check_contains "SPA has OrQuanta"    "${BASE}/app"     "OrQuanta"
  check          "Landing page"        "${BASE}/"        "200"
  check_contains "Landing has OrQuanta" "${BASE}/"       "OrQuanta"
fi

echo ""
echo "--- Summary ---"
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "All checks passed. OrQuanta is healthy."
  exit 0
else
  echo "$FAIL check(s) failed. Review output above."
  exit 1
fi
