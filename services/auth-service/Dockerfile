# Auth Service Dockerfile — Python 3.11 slim multi-stage build
FROM python:3.11-slim AS base

# Security: don't run as root
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install system dependencies (psycopg2-binary needs libpq)
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy application code
COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/

# Switch to non-root user
USER appuser

# Expose auth service port
EXPOSE 8001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run with uvicorn (single worker for simplicity)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
