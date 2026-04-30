#!/usr/bin/env bash
# Start PostgreSQL + OrQuanta API on Oracle Cloud ARM64
# Usage: ADMIN_PASSWORD=xxx NEON_DB_URL=xxx bash infra/oracle/start-services.sh
#   or:  bash infra/oracle/start-services.sh   (uses env vars already set)

set -euo pipefail

ADMIN_PASSWORD="${ADMIN_PASSWORD:?Set ADMIN_PASSWORD}"
DATABASE_URL="${DATABASE_URL:-postgresql://orquanta:orquanta@postgres:5432/orquanta}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
JWT_SECRET_KEY="${JWT_SECRET_KEY:-$(openssl rand -hex 32)}"

echo "==> Starting PostgreSQL 16 (ARM64)..."
sudo docker run -d \
  --name postgres \
  --network orquanta \
  --restart unless-stopped \
  -e POSTGRES_USER=orquanta \
  -e POSTGRES_PASSWORD=orquanta \
  -e POSTGRES_DB=orquanta \
  -v /data/postgres:/var/lib/postgresql/data \
  -p 127.0.0.1:5432:5432 \
  postgres:16-alpine

echo "Waiting for PostgreSQL to be ready..."
for i in $(seq 1 20); do
  sudo docker exec postgres pg_isready -U orquanta 2>/dev/null && break || sleep 3
done

echo ""
echo "==> Starting OrQuanta API..."
# Pull the latest image from GitHub Container Registry (built by CI)
# Or build locally if GHCR not set up yet
if sudo docker pull ghcr.io/madhanrajg/orquanta:latest 2>/dev/null; then
  IMAGE="ghcr.io/madhanrajg/orquanta:latest"
else
  echo "  GHCR not available — building from local checkout..."
  cd /home/ubuntu/orquanta
  IMAGE="orquanta:local"
  sudo docker build -t "$IMAGE" .
fi

sudo docker run -d \
  --name orquanta-api \
  --network orquanta \
  --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -e PORT=8000 \
  -e ENVIRONMENT=production \
  -e DATABASE_URL="$DATABASE_URL" \
  -e SECRET_KEY="$SECRET_KEY" \
  -e JWT_SECRET_KEY="$JWT_SECRET_KEY" \
  -e ADMIN_EMAIL="admin@orquanta.com" \
  -e ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  -e APP_URL="https://orquanta.com" \
  -e CORS_ORIGINS="https://orquanta.com,https://www.orquanta.com" \
  -e LLM_PROVIDER=auto \
  "$IMAGE"

echo ""
echo "==> Health check..."
sleep 5
curl -s http://127.0.0.1:8000/health | grep -q '"status":"healthy"' && \
  echo "✓ OrQuanta API is healthy on :8000" || \
  echo "⚠ Health check pending — check: docker logs orquanta-api"
