#!/usr/bin/env bash
# OrQuanta — Switch Cloudflare Worker BACKEND_URL from Render → Oracle
#
# Run this from your LOCAL machine after:
#   1. Oracle API is healthy (verified by verify.sh)
#   2. Cloudflare Tunnel is running (start-tunnel.sh completed)
#
# Requirements: wrangler installed, CLOUDFLARE_API_TOKEN set
#
# Usage:
#   CLOUDFLARE_API_TOKEN=xxx bash infra/oracle/update-backend.sh

set -euo pipefail

CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:?ERROR: Set CLOUDFLARE_API_TOKEN}"
WRANGLER_TOML="$(cd "$(dirname "$0")/../.." && pwd)/wrangler.toml"
NEW_BACKEND="https://backend.orquanta.com"

echo "=========================================="
echo " OrQuanta — Flip Worker to Oracle Backend"
echo "=========================================="
echo ""

# Show current value
CURRENT=$(grep 'BACKEND_URL' "$WRANGLER_TOML" | head -1 | sed 's/.*= *//' | tr -d '"')
echo "Current BACKEND_URL : $CURRENT"
echo "New     BACKEND_URL : $NEW_BACKEND"
echo ""

read -rp "Confirm switch? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted."
  exit 0
fi

echo ""
echo "==> [1/3] Updating wrangler.toml..."
# Replace the BACKEND_URL line in wrangler.toml
sed -i "s|BACKEND_URL = \".*\"|BACKEND_URL = \"${NEW_BACKEND}\"|" "$WRANGLER_TOML"
grep 'BACKEND_URL' "$WRANGLER_TOML"
echo "    Updated."

echo ""
echo "==> [2/3] Deploying updated Cloudflare Worker..."
cd "$(dirname "$WRANGLER_TOML")"
CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" npx wrangler deploy --config wrangler.toml
echo "    Worker deployed."

echo ""
echo "==> [3/3] Smoke test via Worker..."
sleep 5
for i in $(seq 1 6); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://orquanta.com/health 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    echo "    orquanta.com/health → HTTP 200  (Oracle backend confirmed)"
    break
  fi
  echo "    Attempt $i/6 — HTTP $STATUS — waiting 5s..."
  sleep 5
done

if [ "$STATUS" != "200" ]; then
  echo ""
  echo "WARNING: orquanta.com/health not returning 200."
  echo "The Worker update may still be propagating (up to 30s)."
  echo "To roll back: change BACKEND_URL back to https://orquanta-sg.onrender.com"
  echo "and run: npx wrangler deploy"
fi

echo ""
echo "=========================================="
echo " Done! OrQuanta now runs on Oracle (free forever)."
echo "=========================================="
echo ""
echo "You can now disable Render to avoid any future charges:"
echo "  Go to render.com → orquanta-sg → Settings → Suspend Service"
