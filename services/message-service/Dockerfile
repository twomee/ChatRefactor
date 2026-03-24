# Multi-stage build: small, secure Python image for the message service
FROM python:3.11-slim AS base

# Security: run as non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Install system dependencies and upgrade base packages
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
# Upgrade pip and setuptools first — setuptools vendors jaraco.context and wheel,
# old vendored copies trigger CVE-2026-23949 and CVE-2026-24049 in Trivy scans
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --upgrade -r requirements.txt

# Copy application code (selective — excludes tests, coverage, cache)
COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/

# Switch to non-root user
USER appuser

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
