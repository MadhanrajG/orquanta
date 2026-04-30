#!/usr/bin/env bash
# Cloudflare Tunnel: connect Oracle Cloud → orquanta.com edge
# Prerequisite: cloudflared tunnel login + cloudflared tunnel create orquanta-tunnel
#
# Usage: TUNNEL_ID=xxx bash infra/oracle/start-tunnel.sh

set -euo pipefail

TUNNEL_ID="${TUNNEL_ID:?Set TUNNEL_ID (from: cloudflared tunnel list)}"
TUNNEL_NAME="orquanta-tunnel"

# Write tunnel config
sudo mkdir -p /etc/cloudflared
cat <<EOF | sudo tee /etc/cloudflared/config.yml
tunnel: ${TUNNEL_ID}
credentials-file: /root/.cloudflared/${TUNNEL_ID}.json

ingress:
  # API + SPA backend on local port 8000
  - hostname: orquanta.com
    service: http://localhost:8000
    originRequest:
      connectTimeout: 10s
      noTLSVerify: false
  - hostname: www.orquanta.com
    service: http://localhost:8000
    originRequest:
      connectTimeout: 10s
      noTLSVerify: false
  # Catch-all (required by cloudflared)
  - service: http_status:404
EOF

echo "==> Installing tunnel as systemd service..."
sudo cloudflared service install

echo "==> Starting tunnel..."
sudo systemctl enable --now cloudflared

echo ""
echo "==> Tunnel status:"
sudo systemctl status cloudflared --no-pager

echo ""
echo "Done! Update Cloudflare DNS:"
echo "  Change A @ 192.0.2.1 → CNAME @ ${TUNNEL_ID}.cfargotunnel.com (proxied)"
echo "  Change A www → CNAME www ${TUNNEL_ID}.cfargotunnel.com (proxied)"
echo "  The Cloudflare Worker will route through the tunnel automatically."
