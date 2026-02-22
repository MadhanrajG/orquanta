FROM python:3.11-slim

WORKDIR /app

# Install dependencies (lean production set)
COPY requirements_deploy.txt .
RUN pip install --no-cache-dir -r requirements_deploy.txt

# Copy entire application
COPY . .

# Expose port
EXPOSE 8000

# Exec-form with explicit shell — guarantees $PORT expands
CMD ["sh", "-c", "exec uvicorn v4.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
