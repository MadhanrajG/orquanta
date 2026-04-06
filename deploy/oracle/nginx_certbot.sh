#!/bin/bash
# =============================================================================
# OrQuanta — Nginx + Certbot HTTPS Setup
# Usage: bash nginx_certbot.sh orquanta.ai your@email.com
# Run AFTER oracle_init.sh and after DNS A record points to this server's IP.
# =============================================================================
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-admin@orquanta.ai}"
COMPOSE="docker compose -f /opt/orquanta/deploy/oracle/docker-compose.oracle.yml"

[[ -z "$DOMAIN" ]] && { echo "Usage: $0 <domain> [email]"; exit 1; }

echo "[certbot] Setting up HTTPS for: $DOMAIN"

# Step 1: Replace placeholder in nginx config
CONF="/opt/orquanta/deploy/oracle/nginx/conf.d/orquanta.conf"
sed -i "s/YOUR_DOMAIN/$DOMAIN/g" "$CONF"
echo "[nginx] Domain substituted in $CONF"

# Step 2: Start Nginx with HTTP-only config first (certbot needs port 80)
$COMPOSE up -d nginx
sleep 3

# Step 3: Get initial certificate (standalone webroot challenge)
docker compose -f /opt/orquanta/deploy/oracle/docker-compose.oracle.yml \
    run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN" \
    -d "www.$DOMAIN"

echo "[certbot] Certificate issued!"

# Step 4: Reload Nginx to pick up the new certs
$COMPOSE exec nginx nginx -s reload
echo "[nginx] Reloaded with TLS config"

# Step 5: Verify
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/health")
echo "[health] https://$DOMAIN/health → HTTP $HTTP"
[[ "$HTTP" == "200" ]] && echo "✅ HTTPS is live at https://$DOMAIN" || echo "⚠️  API returned $HTTP — check docker logs"

echo ""
echo "Auto-renewal runs every 12 hours via the certbot container."
echo "Test renewal: docker compose run --rm certbot renew --dry-run"
