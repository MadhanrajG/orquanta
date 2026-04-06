# OrQuanta — Production Deployment Guide

## 1. Prerequisites
- Docker & Docker Compose installed
- A Linux VPS or cloud VM (Ubuntu 22.04 recommended — DigitalOcean, Hetzner, AWS EC2, GCP Compute)
- A domain name pointing to your server's IP
- Port 80 and 443 open in firewall

---

## 2. Clone & Configure

```bash
git clone https://github.com/YOUR_ORG/orquanta.git
cd orquanta
```

### Create production env file
```bash
cp v4/.env.production v4/.env.prod
# IMPORTANT: Edit .env.prod and set:
#   ADMIN_PASSWORD=<your strong password>
#   OPENAI_API_KEY=sk-...
#   Any other real API keys
nano v4/.env.prod
```

---

## 3. SSL Certificate (Let's Encrypt)

```bash
# Install certbot
sudo apt install certbot
sudo certbot certonly --standalone -d orquanta.com -d www.orquanta.com

# Certificates will be at:
# /etc/letsencrypt/live/orquanta.com/fullchain.pem
# /etc/letsencrypt/live/orquanta.com/privkey.pem
```

Update `v4/infra/nginx/nginx.prod.conf` ssl paths if different.

---

## 4. Build & Launch with Docker Compose

```bash
cd v4/infra

# Build all images
docker compose -f docker-compose.yml --env-file ../`.env.prod` build

# Start all services (postgres, redis, chromadb, api, nginx, grafana)
docker compose -f docker-compose.yml --env-file ../.env.prod up -d

# Verify all containers are healthy
docker compose ps
```

---

## 5. Verify Launch

| URL | Expected |
|-----|----------|
| `https://orquanta.com` | Demo landing page |
| `https://orquanta.com/app` | React login page |
| `https://orquanta.com/demo` | Interactive demo |
| `https://orquanta.com/health` | `{"status":"ok"}` JSON |
| `https://orquanta.com/docs` | Swagger API |
| `http://YOUR_IP:3001` | Grafana monitoring |

---

## 6. First Admin Login

1. Browse to `https://orquanta.com/app`
2. Email: `admin@orquanta.com`
3. Password: *(the value you set for `ADMIN_PASSWORD` in .env.prod)*

---

## 7. Enable Real AI & GPU Providers

In `.env.prod`, set:
```ini
LLM_PROVIDER=openai
USE_REAL_PROVIDERS=true
OPENAI_API_KEY=sk-...
LAMBDA_LABS_API_KEY=...
RUNPOD_API_KEY=...
```

Then restart:
```bash
docker compose restart api
```

---

## 8. Auto-renew SSL

```bash
# Add to cron:
0 3 * * * certbot renew --quiet && docker compose -f /path/to/docker-compose.yml restart nginx
```

---

## 9. Monitoring (Grafana)

- URL: `http://YOUR_IP:3001`
- Login: `admin` / *(GRAFANA_PASSWORD from .env.prod)*
- Dashboards: GPU Jobs, Agent Activity, Cost Tracker, API Latency

---

## 10. Quick Deploy to Railway (Alternative — No VPS needed)

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

Set environment variables in Railway dashboard from `.env.production`.

---

## Security Checklist Before Going Live
- [ ] Changed ADMIN_PASSWORD from placeholder
- [ ] Added real OPENAI_API_KEY or ANTHROPIC_API_KEY
- [ ] SSL certificate working (HTTPS green lock)
- [ ] .env.prod is NOT committed to git
- [ ] Firewall blocks all ports except 80, 443, 22
- [ ] Database accessible only from internal docker network
