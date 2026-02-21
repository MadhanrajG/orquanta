FROM python:3.11-slim

WORKDIR /app

# Install dependencies (lean production set)
COPY requirements_deploy.txt .
RUN pip install --no-cache-dir -r requirements_deploy.txt

# Copy entire application
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run OrQuanta v4 API
CMD uvicorn v4.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
