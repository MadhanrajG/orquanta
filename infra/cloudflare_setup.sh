#!/usr/bin/env bash
# OrQuanta — Cloudflare DNS setup script
# Run this AFTER signing up at cloudflare.com and getting your API token
# Usage: CF_API_TOKEN=xxx CF_EMAIL=xxx bash cloudflare_setup.sh

set -euo pipefail

CF_API_TOKEN="${CF_API_TOKEN:?Set CF_API_TOKEN}"
DOMAIN="orquanta.com"
RENDER_TARGET="orquanta-sg.onrender.com"   # Singapore — co-located with PostgreSQL DB

echo "==> Finding Cloudflare Zone ID for $DOMAIN..."
ZONE_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=$DOMAIN" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['result'][0]['id'])")
echo "    Zone ID: $ZONE_ID"

_dns_record() {
  local TYPE=$1 NAME=$2 CONTENT=$3 PROXIED=$4
  echo "==> Adding $TYPE $NAME → $CONTENT (proxied=$PROXIED)..."
  curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data "{\"type\":\"$TYPE\",\"name\":\"$NAME\",\"content\":\"$CONTENT\",\"proxied\":$PROXIED,\"ttl\":1}" | \
    python3 -c "import sys,json; r=json.load(sys.stdin); print('OK:', r.get('success'), r.get('result',{}).get('id',''))"
}

# Root domain — Cloudflare proxied (orange cloud) for DDoS protection + CDN
_dns_record CNAME "@"   "$RENDER_TARGET" true
_dns_record CNAME "www" "$RENDER_TARGET" true

# API subdomain — for Phase 3 (Cloudflare Tunnel)
# _dns_record CNAME "api" "TUNNEL_ID.cfargotunnel.com" true

echo ""
echo "==> Setting SSL/TLS to Full (strict)..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/settings/ssl" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"value":"full"}' | python3 -c "import sys,json; r=json.load(sys.stdin); print('SSL mode set:', r.get('result',{}).get('value',''))"

echo ""
echo "==> Enabling HTTPS redirect..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/settings/always_use_https" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"value":"on"}' | python3 -c "import sys,json; r=json.load(sys.stdin); print('HTTPS redirect:', r.get('result',{}).get('value',''))"

echo ""
echo "==> Enabling HSTS (max-age 6 months, includeSubDomains)..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/settings/security_header" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"value":{"strict_transport_security":{"enabled":true,"max_age":15768000,"include_subdomains":true,"preload":false}}}' | \
  python3 -c "import sys,json; r=json.load(sys.stdin); print('HSTS:', r.get('success'))"

echo ""
echo "==> Setting minimum TLS to 1.2..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/settings/min_tls_version" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"value":"1.2"}' | python3 -c "import sys,json; r=json.load(sys.stdin); print('Min TLS:', r.get('result',{}).get('value',''))"

echo ""
echo "Done! Next steps:"
echo "  1. In Hostinger → orquanta.com → DNS → Change nameservers to Cloudflare NS records"
echo "  2. In Render dashboard → orquanta service → Settings → Custom Domains → Add orquanta.com"
echo "  3. DNS propagation: 5-30 min after NS change"
