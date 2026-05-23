#!/usr/bin/env bash
# OrQuanta — Oracle Cloud ARM64 bootstrap
# Oracle Free Tier: 4 OCPU / 24 GB RAM / 200 GB block storage — always free, no expiry
#
# Run once on a fresh Oracle Cloud Ampere A1 instance (Ubuntu 22.04):
#   ssh ubuntu@<ORACLE_PUBLIC_IP> 'bash -s' < infra/oracle/setup.sh

set -euo pipefail

echo "=========================================="
echo " OrQuanta — Oracle ARM64 Bootstrap"
echo "=========================================="

echo ""
echo "==> [1/6] System update..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

echo ""
echo "==> [2/6] Installing Docker..."
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker ubuntu
sudo systemctl enable --now docker
echo "    Docker $(sudo docker --version | cut -d' ' -f3) ready"

echo ""
echo "==> [3/6] Adding 4 GB swap (helps Docker ARM64 builds)..."
if [ ! -f /swapfile ]; then
  sudo fallocate -l 4G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  echo "    Swap enabled"
else
  echo "    Swap already exists, skipping"
fi

echo ""
echo "==> [4/6] Installing Cloudflare Tunnel (cloudflared)..."
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | \
  sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update -qq && sudo apt-get install -y cloudflared
echo "    cloudflared $(cloudflared --version | head -1) ready"

echo ""
echo "==> [5/6] Cloning OrQuanta repo..."
if [ ! -d /home/ubuntu/orquanta ]; then
  git clone https://github.com/madhanrajg/orquanta.git /home/ubuntu/orquanta
  echo "    Repo cloned to /home/ubuntu/orquanta"
else
  echo "    Repo already exists, pulling latest..."
  git -C /home/ubuntu/orquanta pull origin main
fi

echo ""
echo "==> [6/6] Creating Docker network..."
sudo docker network create orquanta 2>/dev/null && echo "    Network 'orquanta' created" || echo "    Network 'orquanta' already exists"

echo ""
echo "=========================================="
echo " Bootstrap complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1.  Set your secrets, then run:"
echo "        export DATABASE_URL='<your-neon-connection-string>'"
echo "        export JWT_SECRET_KEY='$(openssl rand -hex 32)'"
echo "        export ADMIN_PASSWORD='<your-admin-password>'"
echo "        bash /home/ubuntu/orquanta/infra/oracle/start-services.sh"
echo ""
echo "  2.  Authenticate Cloudflare Tunnel (browser required once):"
echo "        cloudflared tunnel login"
echo ""
echo "  3.  Then run:"
echo "        bash /home/ubuntu/orquanta/infra/oracle/start-tunnel.sh"
