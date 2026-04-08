# Getting Started

Get cHATBOX running from zero. Two paths: **Docker (recommended)** for the fastest start, or **Local Development** if you need hot-reload.

---

## Prerequisites

| Tool | Version | Install | Required For |
|------|---------|---------|--------------|
| Docker | 20+ | [docs.docker.com](https://docs.docker.com/get-docker/) | Both paths |
| Docker Compose | v2+ | Included with Docker Desktop | Both paths |
| Git | 2.x | [git-scm.com](https://git-scm.com/) | Both paths |
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) | Local dev only |
| Go | 1.22+ | [go.dev](https://go.dev/dl/) | Local dev only |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/) | Local dev only |

Verify installations:

```bash
docker --version && docker compose version && git --version
# For local dev, also:
python3 --version && go version && node --version
```

---

## Path 1: Docker (Everything in Containers)

The fastest way to get a running app. No Python, Go, or Node.js needed on your machine.

### Step 1: Clone and Configure

```bash
git clone <repo-url> Chat-Project-Final
cd Chat-Project-Final
cp .env.example .env
```

For production, generate a strong secret key:

```bash
# Edit .env and set:
# SECRET_KEY=$(openssl rand -hex 32)
# ADMIN_PASSWORD=<strong-password>
# POSTGRES_PASSWORD=<strong-password>
```

### Step 2: Build and Start

```bash
make deploy
```

This builds all Docker images, starts all containers, and restarts Kong to resolve DNS. It's equivalent to `docker compose build && docker compose up -d && docker compose restart kong`.

### Step 3: Verify

```bash
docker compose ps          # All containers should show healthy/running
curl http://localhost/api/auth/health
curl http://localhost/api/chat/health
curl http://localhost/api/messages/health
curl http://localhost/api/files/health
```

**Open the app:** http://localhost (port 80, through Kong)

**Default login:** `ido` / `changeme`

> For ongoing Docker Compose operations (logs, rebuilds, troubleshooting), see [Docker Compose Operations](operations/docker-compose.md).

---

## Path 2: Local Development (Hot-Reload)

Infrastructure (Postgres, Redis, Kafka) runs in Docker. Services and frontend run natively for hot-reload.

### Step 1: Clone and Configure

```bash
git clone <repo-url> Chat-Project-Final
cd Chat-Project-Final
cp .env.example .env
# Defaults in .env work for local dev — no changes needed
```

### Step 2: Start Infrastructure

```bash
docker compose -f docker-compose.dev.yml up -d
```

This starts PostgreSQL (port 5432, with 4 databases auto-created), Redis (port 6379), and Kafka (port 29092).

```bash
docker compose -f docker-compose.dev.yml ps   # All should show healthy
```

> Kafka may take 30-60 seconds to become healthy.

### Step 3: Start Each Service

Each service runs in its own terminal:

**Auth Service (Python):**
```bash
cd services/auth-service
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

**Chat Service (Go):**
```bash
cd services/chat-service
go run ./cmd/...
```

**Message Service (Python):**
```bash
cd services/message-service
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8004
```

**File Service (Node.js):**
```bash
cd services/file-service
npm install
npm run dev
```

On first start, each service will run database migrations, connect to Redis and Kafka, and the auth service will seed the admin user and default rooms.

**Services ready at:**
- Auth: http://localhost:8001 (Swagger: http://localhost:8001/docs)
- Chat: http://localhost:8003
- Message: http://localhost:8004 (Swagger: http://localhost:8004/docs)
- File: http://localhost:8005

### Step 4: Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

**Open the app:** http://localhost:5173

**Default login:** `ido` / `changeme`

> In local dev without Kong, update `frontend/.env` to point to individual service ports for API calls.

### Step 5: Verify

1. Open http://localhost:5173
2. Register a new user or log in with `ido` / `changeme`
3. Join a room and send a message
4. Check health endpoints:

```bash
curl http://localhost:8001/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8005/health
```

### Stopping

```bash
# Stop infrastructure
docker compose -f docker-compose.dev.yml down

# Stop each service: Ctrl+C in their terminals
# Stop frontend: Ctrl+C

# Wipe all data (databases, Kafka logs):
docker compose -f docker-compose.dev.yml down -v
```

---

## Project Architecture (Quick Overview)

```
                          +-----------+
                          |  Frontend |  (React + Nginx)
                          +-----+-----+
                                |
                          +-----+-----+
                          |   Kong    |  (API Gateway)
                          +-----+-----+
                                |
          +----------+----------+----------+----------+
          |          |          |          |          |
     /api/auth  /ws/chat  /api/messages  /api/files
          |          |          |          |
    +-----+----+ +--+------+ +-+--------+ +--+------+
    |  Auth    | |  Chat   | | Message  | |  File   |
    | (Python) | |  (Go)   | | (Python) | | (Node)  |
    +-----+----+ +--+------+ +-+--------+ +--+------+
          |          |          |          |
     +----+---+ +---+----+ +--+-----+ +--+-----+
     |Postgres| | Redis  | |Postgres| |Postgres|
     | (auth) | |(cache/ | | (msgs) | | (files)|
     +--------+ |blacklst| +--------+ +--------+
                +--------+
                     |
                  +--+---+
                  | Kafka |
                  +------+
```

Each service owns its own database and communicates asynchronously via Kafka.
Redis is used by the auth-service for token blacklisting and rate-limit state.
WebSocket fan-out currently runs in-process; Redis pub/sub is planned for horizontal scaling.

For the full architecture deep-dive, see [Architecture Overview](architecture/overview.md).

---

## What's Next?

| Goal | Doc |
|------|-----|
| Understand why we chose each technology | [Architecture Overview](architecture/overview.md) |
| Learn the CI/CD workflow before writing code | [Development Workflow](development/dev-workflow.md) |
| Deploy to Kubernetes | [Kubernetes Guide](operations/kubernetes-guide.md) |
| Set up monitoring | [Monitoring](operations/monitoring.md) |
