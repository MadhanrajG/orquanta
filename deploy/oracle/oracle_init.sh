#!/bin/bash
# =============================================================================
# OrQuanta — Oracle Cloud ARM64 (VM.Standard.A1.Flex) Initialization Script
# Tested on: Ubuntu 22.04 LTS (aarch64)
# Run as: bash oracle_init.sh
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; R='\033[0m'

log()  { echo -e "${CYAN}[orquanta]${R} $*"; }
ok()   { echo -e "${GREEN}[  OK   ]${R} $*"; }
warn() { echo -e "${YELLOW}[ WARN  ]${R} $*"; }
die()  { echo -e "${RED}[ FAIL  ]${R} $*"; exit 1; }

echo -e "${BOLD}"
cat <<'BANNER'
  ____       ___                    _
 / __ \  ___/ _ \ _   _  __ _ _ __ | |_ __ _
| |  | |/ __| | | | | | |/ _` | '_ \| __/ _` |
| |__| | (__| |_| | |_| | (_| | | | | || (_| |
 \____/ \___|\__\_\\__,_|\__,_|_| |_|\__\__,_|
    Oracle Cloud ARM64 Bootstrap  v1.1
BANNER
echo -e "${R}"

# =============================================================================
# 1. Confirm we're running as non-root with sudo access
# =============================================================================
if [[ $EUID -eq 0 ]]; then
    die "Do not run as root. Run as ubuntu or your VM user with sudo privileges."
fi
log "User: $(whoami) on $(hostname) [$(uname -m)]"
[[ "$(uname -m)" == "aarch64" ]] || warn "Not aarch64 — some Docker images may not work"

# =============================================================================
# 2. System updates & base dependencies
# =============================================================================
log "Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release \
    netfilter-persistent iptables-persistent \
    git jq openssl htop unzip \
    python3-pip python3-venv
ok "Base packages installed"

# =============================================================================
# 3. Docker — ARM64 optimized (docker-ce, not snap version)
# =============================================================================
if command -v docker &>/dev/null; then
    ok "Docker already installed: $(docker --version)"
else
    log "Installing Docker CE (ARM64)..."
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
    ok "Docker installed: $(docker --version)"
    ok "Docker Compose: $(docker compose version)"
fi

# Enable and start Docker
sudo systemctl enable docker --now
ok "Docker daemon running"

# =============================================================================
# 4. Oracle Cloud Firewall Fix (CRITICAL — Oracle iptables override UFW)
# Oracle adds its own REJECT rules that block traffic even if port is open in VCN.
# Must insert at position 6 (before Oracle's default REJECT at position 7+).
# =============================================================================
log "Configuring Oracle iptables firewall rules..."
for port in 80 443 8000 3000; do
    sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null && \
        warn "Port $port already open, skipping" || \
        sudo iptables -I INPUT 6 -p tcp --dport "$port" -j ACCEPT
done

# Persist rules so they survive reboots
sudo netfilter-persistent save
ok "Firewall rules saved (ports 80, 443, 8000, 3000 open)"

# =============================================================================
# 5. Create project directory
# =============================================================================
DEPLOY_DIR="/opt/orquanta"
sudo mkdir -p "$DEPLOY_DIR"
sudo chown "$USER:$USER" "$DEPLOY_DIR"
log "Project directory: $DEPLOY_DIR"

# =============================================================================
# 6. Generate all 256-bit production secrets (never commit these)
# =============================================================================
log "Generating cryptographic secrets..."

SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)
AUDIT_HMAC_KEY=$(openssl rand -hex 32)
ADMIN_PASSWORD=$(openssl rand -base64 16 | tr -d '=+/' | cut -c1-20)
DB_PASSWORD=$(openssl rand -hex 24)
GRAFANA_SECRET=$(openssl rand -hex 16)

# Write .env — this file must NEVER be committed to git
ENV_FILE="$DEPLOY_DIR/.env"
cat > "$ENV_FILE" <<EOF
# OrQuanta Production Secrets — Generated $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# ⚠️  NEVER commit this file to git. Add .env to .gitignore.

# Core security
SECRET_KEY=${SECRET_KEY}
JWT_SECRET_KEY=${JWT_SECRET_KEY}
AUDIT_HMAC_KEY=${AUDIT_HMAC_KEY}

# Admin access
ADMIN_EMAIL=admin@orquanta.ai
ADMIN_PASSWORD=${ADMIN_PASSWORD}

# Database (PostgreSQL via Docker)
DATABASE_URL=postgresql://orquanta:${DB_PASSWORD}@postgres:5432/orquanta
POSTGRES_USER=orquanta
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=orquanta

# LLM & agents
ORQUANTA_DEMO_MODE=false
TURBOQUANT_ENABLED=true
OLLAMA_BASE_URL=http://ollama:11434

# Provider API keys (fill in manually)
RUNPOD_API_KEY=
LAMBDA_LABS_API_KEY=
VAST_API_KEY=

# Monitoring
GRAFANA_SECRET=${GRAFANA_SECRET}
PYTHONUNBUFFERED=1
EOF

chmod 600 "$ENV_FILE"
ok "Secrets generated → $ENV_FILE"

echo ""
echo -e "${BOLD}${GREEN}══════════════════════════════════════════${R}"
echo -e "${BOLD}  ADMIN_PASSWORD: ${YELLOW}${ADMIN_PASSWORD}${R}"
echo -e "${BOLD}  Save this now — it will not be shown again${R}"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════${R}"
echo ""

# =============================================================================
# 7. Clone or pull latest OrQuanta code
# =============================================================================
log "Fetching OrQuanta codebase..."
if [[ -d "$DEPLOY_DIR/.git" ]]; then
    cd "$DEPLOY_DIR" && git pull origin main
    ok "Code updated"
else
    # Replace with your actual repo URL
    REPO_URL="${ORQUANTA_REPO_URL:-https://github.com/MadhanrajG/orquanta.git}"
    git clone "$REPO_URL" "$DEPLOY_DIR"
    ok "Code cloned from $REPO_URL"
fi

# =============================================================================
# 8. Pull Ollama model (Gemma 2B — lightweight, ARM64 native)
# =============================================================================
log "Pulling Ollama Gemma 2B model for local inference..."
if command -v ollama &>/dev/null; then
    ollama pull gemma2:2b && ok "gemma2:2b ready" || warn "Ollama pull failed, will retry after compose up"
else
    warn "Ollama not installed locally — will run via Docker sidecar"
fi

# =============================================================================
# 9. Launch the stack
# =============================================================================
log "Launching OrQuanta stack via Docker Compose..."
cd "$DEPLOY_DIR"
docker compose -f docker-compose.oracle.yml pull
docker compose -f docker-compose.oracle.yml up -d
ok "Stack launched"

# =============================================================================
# 10. Health check
# =============================================================================
log "Waiting for API to become healthy..."
for i in {1..30}; do
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
    if [[ "$HTTP" == "200" ]]; then
        ok "OrQuanta API is live at http://$(curl -s ifconfig.me):8000"
        break
    fi
    echo -n "."
    sleep 3
done
[[ "$HTTP" == "200" ]] || warn "API not responding yet — check: docker compose logs api"

echo ""
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════${R}"
echo -e "  OrQuanta Oracle Bootstrap Complete"
echo -e "  API:      ${GREEN}http://localhost:8000${R}"
echo -e "  Grafana:  ${GREEN}http://localhost:3000${R} (admin / see .env)"
echo -e "  Ollama:   ${GREEN}http://localhost:11434${R}"
echo -e "  Logs:     ${YELLOW}docker compose -f docker-compose.oracle.yml logs -f api${R}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════${R}"
echo ""
echo "Next: Run  bash nginx_certbot.sh <your-domain.com>  to enable HTTPS"
