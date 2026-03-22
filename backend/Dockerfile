# ── Stage 1: Build dependencies ──────────────────────────────────────────────
# Install packages that need compilation (psycopg2, argon2-cffi) in a
# temporary builder stage so gcc and dev headers don't ship in the runtime image.
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
# Slim image with only the runtime libraries — no compiler, no dev headers.
FROM python:3.11-slim

WORKDIR /app

# Runtime-only system deps: libpq for psycopg2, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from builder
COPY --from=builder /install /usr/local

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["gunicorn", "main:app", "-c", "gunicorn.conf.py"]
