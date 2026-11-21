# ─── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-slim AS node-builder

WORKDIR /app/frontend

# Install dependencies first (better layer caching)
COPY v4/frontend/package*.json ./
RUN npm ci

# Copy source and build
# Pass production API URLs as build-time args so Vite bakes them into the bundle
COPY v4/frontend/ ./
ARG VITE_API_BASE_URL=https://orquanta.com
ARG VITE_WS_BASE_URL=wss://orquanta.com
ARG VITE_APP_ENV=production
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_BASE_URL=$VITE_WS_BASE_URL
ENV VITE_APP_ENV=$VITE_APP_ENV
RUN npm run build

# ─── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements_deploy.txt .
RUN pip install --no-cache-dir -r requirements_deploy.txt

# Copy entire application
COPY . .

# Copy the freshly built React frontend (overrides any stale dist/)
COPY --from=node-builder /app/frontend/dist ./v4/frontend/dist

# Expose port
EXPOSE 8000

# Exec-form with explicit shell — guarantees $PORT expands
CMD ["sh", "-c", "exec uvicorn v4.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
