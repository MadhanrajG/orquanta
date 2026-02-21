FROM python:3.11-slim

WORKDIR /app

# Install dependencies (lean production set)
COPY requirements_deploy.txt .
RUN pip install --no-cache-dir -r requirements_deploy.txt

# Copy entire application
COPY . .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Use entrypoint.sh which properly expands $PORT via the shell
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
