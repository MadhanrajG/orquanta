#!/usr/bin/env bash
# OrQuanta — Start API on Oracle Cloud ARM64
# Uses Neon PostgreSQL (free forever) — no local Postgres needed.
#
# Required env vars (set before running):
#   DATABASE_URL    — Neon connection string (postgresql://...neon.tech/neondb?sslmode=require)
#   JWT_SECRET_KEY  — random 64-char hex (openssl rand -hex 32)
#   ADMIN_PASSWORD  — password for admin@orquanta.com
#
# Optional:
#   OPENAI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY
#   SENTRY_DSN, STRIPE_SECRET_KEY

set -euo pipefail

echo "=========================================="
echo " OrQuanta — Start API Services"
echo "=========================================="

DATABASE_URL="${DATABASE_URL:?ERROR: Set DATABASE_URL to your Neon connection string}"
JWT_SECRET_KEY="${JWT_SECRET_KEY:?ERROR: Set JWT_SECRET_KEY (run: openssl rand -hex 32)}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:?ERROR: Set ADMIN_PASSWORD}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"

echo ""
echo "==> [1/3] Pulling latest Docker image..."
REPO="ghcr.io/madhanrajg/orquanta"
if sudo docker pull "${REPO}:latest" 2>/dev/null; then
  IMAGE="${REPO}:latest"
  echo "    Using GHCR image: ${IMAGE}"
else
  echo "    GHCR image not available — building from /home/ubuntu/orquanta..."
  echo "    (This takes ~5 min on ARM64 the first time)"
  cd /home/ubuntu/orquanta
  sudo docker build --platform linux/arm64 -t orquanta:local .
  IMAGE="orquanta:local"
fi

echo ""
echo "==> [2/3] Starting OrQuanta API..."

# Stop and remove old container if it exists
sudo docker stop orquanta-api 2>/dev/null && echo "    Stopped old container" || true
sudo docker rm   orquanta-api 2>/dev/null && echo "    Removed old container" || true

# Write env file so restarts don't need these args again
sudo mkdir -p /etc/orquanta
sudo tee /etc/orquanta/env > /dev/null <<ENVEOF
PORT=8000
ENVIRONMENT=production
DATABASE_URL=${DATABASE_URL}
SECRET_KEY=${SECRET_KEY}
JWT_SECRET_KEY=${JWT_SECRET_KEY}
ADMIN_EMAIL=admin@orquanta.com
ADMIN_PASSWORD=${ADMIN_PASSWORD}
APP_URL=https://orquanta.com
CORS_ORIGINS=https://orquanta.com,https://www.orquanta.com
LLM_PROVIDER=auto
USE_REAL_PROVIDERS=false
OPENAI_API_KEY=${OPENAI_API_KEY:-}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
GROQ_API_KEY=${GROQ_API_KEY:-}
SENTRY_DSN=${SENTRY_DSN:-}
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY:-}
ENVEOF

sudo chmod 600 /etc/orquanta/env
echo "    Secrets saved to /etc/orquanta/env (mode 600)"

sudo docker run -d \
  --name orquanta-api \
  --network orquanta \
  --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  --env-file /etc/orquanta/env \
  "${IMAGE}"

echo ""
echo "==> [3/3] Waiting for health check..."
for i in $(seq 1 24); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    echo "    OrQuanta API is healthy (HTTP 200)"
    break
  fi
  echo "    Attempt $i/24 — HTTP ${STATUS} — waiting 5s..."
  sleep 5
done

if [ "$STATUS" != "200" ]; then
  echo ""
  echo "ERROR: API did not become healthy in 2 minutes"
  echo "Check logs: sudo docker logs orquanta-api"
  exit 1
fi

echo ""
echo "=========================================="
echo " API running at http://127.0.0.1:8000"
echo "=========================================="
echo ""
echo "Next: run infra/oracle/start-tunnel.sh to expose it at backend.orquanta.com"
echo "Logs: sudo docker logs -f orquanta-api"
