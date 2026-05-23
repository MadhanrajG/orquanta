#!/usr/bin/env bash
# OrQuanta — Cloudflare Tunnel: Oracle Cloud → backend.orquanta.com
#
# Architecture after this script:
#   orquanta.com  →  Cloudflare Worker  →  backend.orquanta.com
#                                               ↓
#                                       Cloudflare Tunnel (private)
#                                               ↓
#                                     Oracle ARM64 :8000 (FastAPI)
#
# Prerequisites (run ONCE as ubuntu user — requires browser):
#   cloudflared tunnel login
#
# Then run this script:
#   CF_API_TOKEN=xxx bash infra/oracle/start-tunnel.sh

set -euo pipefail

CF_API_TOKEN="${CF_API_TOKEN:?ERROR: Set CF_API_TOKEN (Cloudflare API token with DNS:Edit permission)}"
ZONE_ID="ce15f8600b6f1cd8af8ebee53dd08608"
TUNNEL_NAME="orquanta-tunnel"
BACKEND_HOSTNAME="backend.orquanta.com"

echo "=========================================="
echo " OrQuanta — Cloudflare Tunnel Setup"
echo "=========================================="

echo ""
echo "==> [1/5] Creating tunnel '${TUNNEL_NAME}'..."
# Creates tunnel, prints "Created tunnel orquanta-tunnel with id <UUID>"
TUNNEL_OUTPUT=$(cloudflared tunnel create "${TUNNEL_NAME}" 2>&1 || true)

# Handle already-exists case
if echo "$TUNNEL_OUTPUT" | grep -q "already exists"; then
  echo "    Tunnel already exists — fetching ID..."
  TUNNEL_ID=$(cloudflared tunnel list --output json 2>/dev/null | \
    python3 -c "import sys,json; t=[x for x in json.load(sys.stdin) if x['name']=='${TUNNEL_NAME}']; print(t[0]['id'])" )
else
  TUNNEL_ID=$(echo "$TUNNEL_OUTPUT" | grep -oP '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
fi

if [ -z "$TUNNEL_ID" ]; then
  echo "ERROR: Could not determine TUNNEL_ID"
  echo "Output was: $TUNNEL_OUTPUT"
  exit 1
fi
echo "    Tunnel ID: ${TUNNEL_ID}"

echo ""
echo "==> [2/5] Writing tunnel config..."
sudo mkdir -p /etc/cloudflared

# Copy tunnel credentials (created by `cloudflared tunnel login` + `tunnel create`)
CRED_FILE="/home/ubuntu/.cloudflared/${TUNNEL_ID}.json"
if [ ! -f "$CRED_FILE" ]; then
  echo "ERROR: Credential file not found: $CRED_FILE"
  echo "Make sure you ran: cloudflared tunnel login"
  exit 1
fi
sudo cp "$CRED_FILE" "/etc/cloudflared/${TUNNEL_ID}.json"
sudo chmod 600 "/etc/cloudflared/${TUNNEL_ID}.json"

sudo tee /etc/cloudflared/config.yml > /dev/null <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: /etc/cloudflared/${TUNNEL_ID}.json

ingress:
  # Route backend.orquanta.com → local FastAPI (port 8000)
  # The Cloudflare Worker proxies API calls here via BACKEND_URL
  - hostname: ${BACKEND_HOSTNAME}
    service: http://localhost:8000
    originRequest:
      connectTimeout: 15s
      noTLSVerify: false

  # Catch-all required by cloudflared
  - service: http_status:404
EOF

echo "    Config written to /etc/cloudflared/config.yml"

echo ""
echo "==> [3/5] Creating DNS record: ${BACKEND_HOSTNAME} → ${TUNNEL_ID}.cfargotunnel.com..."
# Delete any existing record first
EXISTING_ID=$(curl -s -X GET \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?type=CNAME&name=${BACKEND_HOSTNAME}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | \
  python3 -c "import sys,json; r=json.load(sys.stdin)['result']; print(r[0]['id'] if r else '')" 2>/dev/null || true)

if [ -n "$EXISTING_ID" ]; then
  curl -s -X DELETE \
    "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records/${EXISTING_ID}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" > /dev/null
  echo "    Deleted old DNS record"
fi

RESULT=$(curl -s -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{
    \"type\": \"CNAME\",
    \"name\": \"${BACKEND_HOSTNAME}\",
    \"content\": \"${TUNNEL_ID}.cfargotunnel.com\",
    \"proxied\": true,
    \"ttl\": 1
  }")

if echo "$RESULT" | python3 -c "import sys,json; assert json.load(sys.stdin)['success']" 2>/dev/null; then
  echo "    DNS record created: ${BACKEND_HOSTNAME} → ${TUNNEL_ID}.cfargotunnel.com (proxied)"
else
  echo "    WARNING: DNS record creation may have failed. Check Cloudflare dashboard."
  echo "    Response: $RESULT"
fi

echo ""
echo "==> [4/5] Installing tunnel as systemd service..."
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl restart cloudflared
sleep 3

echo ""
echo "==> [5/5] Verifying tunnel is connected..."
TUNNEL_STATUS=$(sudo systemctl is-active cloudflared 2>/dev/null || echo "unknown")
if [ "$TUNNEL_STATUS" = "active" ]; then
  echo "    Tunnel service: active"
else
  echo "    WARNING: Tunnel service status: $TUNNEL_STATUS"
  echo "    Check: sudo journalctl -u cloudflared -n 50"
fi

echo ""
echo "=========================================="
echo " Tunnel running!"
echo "=========================================="
echo ""
echo "  ${BACKEND_HOSTNAME} → Oracle:8000 (via private tunnel)"
echo ""
echo "Next: run infra/oracle/update-backend.sh to flip the Cloudflare Worker"
echo "  to use Oracle instead of Render."
echo ""
echo "  TUNNEL_ID=${TUNNEL_ID}"
echo ""
echo "Tunnel logs: sudo journalctl -u cloudflared -f"
