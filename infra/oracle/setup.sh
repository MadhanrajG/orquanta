#!/usr/bin/env bash
# OrQuanta — Oracle Cloud ARM64 bootstrap
# Run on a fresh Oracle Cloud Ampere A1 (Ubuntu 22.04) instance
# Oracle Free Tier: 4 OCPU + 24 GB RAM + 200 GB block storage — always free
#
# Usage (from local machine):
#   ssh ubuntu@<ORACLE_PUBLIC_IP> 'bash -s' < infra/oracle/setup.sh

set -euo pipefail

echo "==> Updating system..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

echo "==> Installing Docker..."
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker ubuntu
sudo systemctl enable --now docker

echo "==> Installing Cloudflare Tunnel (cloudflared)..."
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
  https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | \
  sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update -qq && sudo apt-get install -y cloudflared

echo "==> Setting up persistent volume for PostgreSQL..."
sudo mkdir -p /data/postgres /data/orquanta
sudo chown -R 999:999 /data/postgres   # postgres UID in official docker image

echo "==> Creating orquanta docker network..."
sudo docker network create orquanta 2>/dev/null || true

echo ""
echo "Done! Next steps:"
echo "  1. Run: cloudflared tunnel login"
echo "  2. Run: cloudflared tunnel create orquanta-tunnel"
echo "  3. Copy the tunnel credentials JSON to /etc/cloudflared/"
echo "  4. Run: bash infra/oracle/start-services.sh"
echo "  5. Run: bash infra/oracle/start-tunnel.sh"
