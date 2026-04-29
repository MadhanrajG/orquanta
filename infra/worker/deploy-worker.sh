#!/usr/bin/env bash
# OrQuanta — Deploy Cloudflare Worker via REST API
# Usage: CF_WORKERS_TOKEN=xxx bash deploy-worker.sh

set -euo pipefail

CF_WORKERS_TOKEN="${CF_WORKERS_TOKEN:?Set CF_WORKERS_TOKEN}"
ACCOUNT_ID="2dd90fe6473410b2605b5b177d606599"
ZONE_ID="ce15f8600b6f1cd8af8ebee53dd08608"
WORKER_NAME="orquanta-proxy"
SCRIPT_FILE="$(dirname "$0")/orquanta-proxy.js"

echo "==> Uploading Worker script: $WORKER_NAME..."
UPLOAD=$(curl -s -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/$WORKER_NAME" \
  -H "Authorization: Bearer $CF_WORKERS_TOKEN" \
  -F "metadata={\"main_module\":\"orquanta-proxy.js\",\"compatibility_date\":\"2024-01-01\"};type=application/json" \
  -F "orquanta-proxy.js=@$SCRIPT_FILE;type=application/javascript+module")

echo "$UPLOAD" | python3 -c "import sys,json; r=json.load(sys.stdin); print('Upload OK:', r.get('success'), r.get('errors'))"

echo ""
echo "==> Creating Worker route: orquanta.com/*..."
ROUTE1=$(curl -s -X POST \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/workers/routes" \
  -H "Authorization: Bearer $CF_WORKERS_TOKEN" \
  -H "Content-Type: application/json" \
  --data "{\"pattern\":\"orquanta.com/*\",\"script\":\"$WORKER_NAME\"}")
echo "$ROUTE1" | python3 -c "import sys,json; r=json.load(sys.stdin); print('Route orquanta.com/*:', r.get('success'), r.get('errors'))"

echo ""
echo "==> Creating Worker route: www.orquanta.com/*..."
ROUTE2=$(curl -s -X POST \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/workers/routes" \
  -H "Authorization: Bearer $CF_WORKERS_TOKEN" \
  -H "Content-Type: application/json" \
  --data "{\"pattern\":\"www.orquanta.com/*\",\"script\":\"$WORKER_NAME\"}")
echo "$ROUTE2" | python3 -c "import sys,json; r=json.load(sys.stdin); print('Route www.orquanta.com/*:', r.get('success'), r.get('errors'))"

echo ""
echo "Done! orquanta.com now routes through Worker → orquanta-sg.onrender.com"
