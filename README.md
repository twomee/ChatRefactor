# cHATBOX

A production-ready, real-time chat application with multi-room support, private messaging, file sharing, and admin controls — built as a **microservices architecture** with **FastAPI**, **Go**, **Node.js/TypeScript**, **React**, **PostgreSQL**, **Redis**, **Kafka**, and **Kong API Gateway**.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, Axios, React Router |
| API Gateway | Kong (routes, auth, rate limiting) |
| Auth Service | Python, FastAPI, Argon2, JWT |
| Chat Service | Go, gorilla/websocket, Redis pub/sub |
| Message Service | Python, FastAPI, SQLAlchemy, Alembic |
| File Service | Node.js, TypeScript, Express, Multer |
| Database | PostgreSQL 16 (database per service) |
| Cache & PubSub | Redis 7 |
| Message Queue | Apache Kafka (KRaft) |
| Reverse Proxy | Nginx 1.25 (frontend), Kong (API gateway) |
| Containerization | Docker, Docker Compose |

---

## Architecture

cHATBOX uses a microservices architecture with four backend services behind a Kong API Gateway:

```
                          +-----------+
                          |  Frontend |  (React + Nginx, port 80)
                          +-----+-----+
                                |
                          +-----+-----+
                          |   Kong    |  (API Gateway, port 80)
                          |  Gateway  |
                          +-----+-----+
                                |
          +----------+----------+----------+----------+
          |          |          |          |          |
     /api/auth  /ws/chat  /api/messages  /api/files
          |          |          |          |
    +-----+----+ +--+------+ +-+--------+ +--+------+
    |  Auth    | |  Chat   | | Message  | |  File   |
    | Service  | | Service | | Service  | | Service |
    | (Python) | |  (Go)   | | (Python) | | (Node)  |
    | :8001    | | :8003   | | :8004    | | :8005   |
    +-----+----+ +--+------+ +-+--------+ +--+------+
          |          |          |          |
     +----+---+ +---+----+ +--+-----+ +--+-----+
     |Postgres| | Redis  | |Postgres| |Postgres|
     | (auth) | | PubSub | | (msgs) | | (files)|
     +--------+ +--------+ +--------+ +--------+
                     |
                  +--+---+
                  | Kafka |
                  +------+
```

Each service owns its own database (database-per-service pattern), communicates asynchronously via Kafka, and is independently deployable.

---

## Quick Start

### Option A: Full Stack (Docker) — Recommended

```bash
cp .env.example .env          # configure environment
docker compose up -d --build  # start all microservices + Kong + frontend
```

Services available at:
- **App**: http://localhost (Kong gateway routes all traffic)
- **Auth Service**: http://localhost:8001 (direct) or http://localhost/api/auth
- **Chat Service**: http://localhost:8003 (direct) or ws://localhost/ws/chat
- **Message Service**: http://localhost:8004 (direct) or http://localhost/api/messages
- **File Service**: http://localhost:8005 (direct) or http://localhost/api/files

### Option B: Local Development (recommended for daily work)

```bash
# 1. Start infrastructure (PostgreSQL, Redis, Kafka)
docker compose -f docker-compose.dev.yml up -d

# 2. Start each microservice natively (in separate terminals)
cd services/auth-service && source venv/bin/activate && uvicorn app.main:app --reload --port 8001
cd services/chat-service && go run ./cmd/...
cd services/message-service && source venv/bin/activate && uvicorn app.main:app --reload --port 8004
cd services/file-service && npm install && npm run dev

# 3. Start frontend (in a new terminal)
cd frontend
npm install
npm run dev
```

Frontend at **http://localhost:5173** | Services at ports **8001, 8003, 8004, 8005**

> **Note:** In local dev without Kong, the frontend `.env` must point directly to service ports. In Docker, Kong handles all routing through port 80.

### Option C: Kubernetes (kind — local cluster)

Run the full platform on a local Kubernetes cluster using `kind`.

**Prerequisites:** Docker, `kubectl`, `kind`, `helm` — see [docs/k8s-operations.md](docs/k8s-operations.md) for install instructions.

```bash
# 1. Spin up the cluster, install infra, build images, and deploy everything
make k8s-setup-local

# 2. Verify all pods are running
make k8s-status

# 3. Run the full E2E test suite (46 tests covering every service)
bash k8s/scripts/e2e-test.sh
```

Services available at:
- **Frontend:** http://localhost:30000
- **API (Kong):** http://localhost:30080
- **Grafana:** http://localhost:30030 (admin / admin)
- **Prometheus:** `make k8s-prometheus` (port-forwards to http://localhost:9090)

Tear everything down when done:
```bash
make k8s-teardown
```

For concepts and architecture: [docs/k8s-readme.md](docs/k8s-readme.md)
For step-by-step commands and troubleshooting: [docs/k8s-operations.md](docs/k8s-operations.md)

### Option D: Legacy Monolith (reference only)

The original monolith is preserved at `v1/backend/` for reference. See [v1/backend/](v1/backend/) if you need to run it.

---

## Default Credentials

| Username | Password | Role |
|----------|----------|------|
| `ido` | `changeme` | Global Admin |

Register additional accounts from the login page.

---

## Features

- **Multi-room chat** — Three default rooms (politics, sports, movies) + create custom rooms
- **Real-time messaging** — Native WebSocket with Redis pub/sub relay for multi-worker support
- **Private messages** — Direct messaging between users
- **File sharing** — Upload and download files in rooms (up to 150 MB)
- **Durable persistence** — Messages flow through Kafka for async database writes with DLQ support
- **Room admin controls** — Kick, mute/unmute, promote users, auto admin succession
- **Global admin panel** — Manage all rooms, users, and files from a dedicated dashboard
- **Graceful degradation** — Works without Kafka (sync fallback) and without Redis (local-only delivery)
- **Health checks** — `/health` (liveness) and `/ready` (readiness) endpoints per service
- **Rate limiting** — Per-IP rate limits with Redis-backed state in production
- **Structured logging** — Human-readable in dev, JSON in production
- **Microservices** — Polyglot backend (Python, Go, Node.js) with Kong API Gateway

---

## Project Structure

```
Chat-Project-Final/
├── services/                    # Microservices (current architecture)
│   ├── auth-service/            # Python/FastAPI — JWT auth, registration, token blacklist
│   │   ├── app/                 # FastAPI application (routers, services, dal, models)
│   │   ├── alembic/             # Database migrations
│   │   ├── tests/               # pytest test suite
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── chat-service/            # Go — WebSocket server, real-time messaging, admin commands
│   │   ├── cmd/                 # Entry point (main.go)
│   │   ├── internal/            # Handlers, hub, ws manager, delivery, middleware
│   │   ├── migrations/          # SQL migrations
│   │   ├── tests/               # Go test suite
│   │   └── Dockerfile
│   │
│   ├── message-service/         # Python/FastAPI — message persistence, history, CQRS
│   │   ├── app/                 # FastAPI application (routers, services, dal, consumers)
│   │   ├── alembic/             # Database migrations
│   │   ├── tests/               # pytest test suite
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── file-service/            # Node.js/TypeScript — file upload, download, metadata
│       ├── src/                 # Express app (routes, services, middleware, kafka)
│       ├── prisma/              # Prisma ORM schema
│       ├── tests/               # Vitest test suite
│       ├── Dockerfile
│       └── package.json
│
├── frontend/                    # React 19 + Vite 8
│   ├── src/
│   │   ├── pages/               # LoginPage, ChatPage, AdminPage
│   │   ├── components/          # MessageList, RoomList, UserList, PMView, etc.
│   │   ├── context/             # AuthContext, ChatContext, PMContext
│   │   ├── services/            # API client wrappers (authApi, roomApi, pmApi, etc.)
│   │   ├── hooks/               # Custom hooks (useMultiRoomChat)
│   │   └── api/http.js          # Axios instance with JWT interceptor
│   ├── nginx.conf               # Reverse proxy config (SPA routing)
│   ├── Dockerfile               # Production container (Node 20 build + Nginx 1.25)
│   └── package.json
│
├── k8s/                         # Kubernetes manifests and scripts
│   ├── base/                    # Base Kustomize config (env-agnostic)
│   ├── overlays/                # Environment overlays: dev, staging, prod, *-kind
│   ├── infra/                   # Helm values for PostgreSQL, Redis, Kafka
│   ├── jobs/                    # Init jobs (db-init, kafka-init)
│   └── scripts/                 # Automation scripts
│       ├── setup-local.sh       # One-command cluster setup
│       ├── teardown.sh          # Full teardown
│       ├── build-images.sh      # Build + load images into kind
│       ├── deploy.sh            # Apply overlay + wait for rollouts
│       ├── generate-secrets.sh  # Create K8s Secrets from secrets.env
│       └── e2e-test.sh          # 46-test E2E functional test suite
│
├── contracts/                   # Kafka event schemas (JSON Schema)
│   └── events/                  # 6 event contract files (chat, file, auth, dlq)
│
├── infra/                       # Infrastructure configs
│   ├── docker/init/             # init-db.sh, init-kafka.sh
│   └── kong/                    # kong.yml (declarative gateway config)
│
├── loadtests/                   # Load testing suite (Locust)
│   ├── locustfile.py            # Microservices load test (4 user classes via Kong)
│   ├── scenarios/               # Legacy monolith scenario files
│   ├── scripts/                 # CI gate scripts
│   ├── benchmarks/              # pytest-benchmark micro-benchmarks
│   └── README.md
│
├── docs/                        # Documentation
│   ├── OPERATIONS_GUIDE.md      # How to run, debug, and troubleshoot
│   ├── ARCHITECTURE_AND_TECH_DECISIONS.md  # Why every technology was chosen
│   ├── FRONTEND_EXPLAINED.md    # Frontend architecture and component guide
│   └── MICROSERVICES_VERIFICATION_CHECKLIST.md  # 174-item feature parity checklist
│
├── v1/                          # Original monolith (kept for reference)
│   └── backend/                 # FastAPI monolith — deprecated
│
├── .github/workflows/           # CI/CD pipelines
│   ├── ci.yml                   # Legacy monolith CI (lint, test, build)
│   ├── ci-auth.yml              # Auth service CI
│   ├── ci-chat.yml              # Chat service CI
│   ├── ci-message.yml           # Message service CI
│   ├── ci-file.yml              # File service CI
│   ├── ci-microservices.yml     # Docker Compose syntax validation
│   ├── security.yml             # Trivy vulnerability scanning
│   └── secrets.yml              # Gitleaks secret scanning
│
├── docker-compose.yml           # Production: microservices + Kong + frontend
├── docker-compose.dev.yml       # Development: PostgreSQL + Redis + Kafka only
├── .env.example                 # Environment variable template
├── .pre-commit-config.yaml      # Pre-commit hooks (gitleaks, ruff, eslint)
└── .env                         # Local environment config (not committed)
```

---

## Documentation

| Document | What's in it |
|----------|-------------|
| **[Operations Guide](docs/OPERATIONS_GUIDE.md)** | Setup, running, debugging, and troubleshooting for all microservices |
| **[Architecture & Tech Decisions](docs/ARCHITECTURE_AND_TECH_DECISIONS.md)** | Why every technology was chosen, microservice architecture, design patterns, trade-offs |
| **[Dev Platform Guide](DEV_PLATFORM_GUIDE.md)** | CI/CD pipelines, per-service linting/testing, security scanning, pre-commit hooks |
| **[Frontend Explained](docs/FRONTEND_EXPLAINED.md)** | Frontend architecture, React concepts, component structure, data flow |
| **[K8s Guide](docs/k8s-readme.md)** | Kubernetes architecture, namespaces, Kustomize overlays, secrets, migrations — the "why" |
| **[K8s Operations](docs/k8s-operations.md)** | Step-by-step K8s commands, scripts reference, Makefile targets, troubleshooting |
| **[Kafka Event Contracts](contracts/README.md)** | Kafka event schemas, producer/consumer mapping, contract rules |
| **[Verification Checklist](docs/MICROSERVICES_VERIFICATION_CHECKLIST.md)** | 174-item feature parity checklist (171/174 passed) |
| **[Load Tests](loadtests/README.md)** | Load testing suite, performance baselines, user classes, pass/fail criteria |

---

## Makefile Reference

All K8s tasks have a `make` shortcut. Run `make <target>` from the project root.

### Variables

| Variable | Default | Used By |
|----------|---------|---------|
| `SVC` | *(required for some targets)* | `k8s-logs`, `k8s-shell`, `k8s-restart`, `k8s-redeploy` |
| `OVERLAY` | `dev` | `k8s-deploy`, `k8s-validate` |
| `CLUSTER_NAME` | `chatbox` | All kind commands |

Valid values for `SVC`: `auth-service`, `chat-service`, `message-service`, `file-service`, `frontend`, `kong`

Valid values for `OVERLAY`: `dev`, `staging`, `prod`, `staging-kind`, `prod-kind`

### Cluster Lifecycle

```bash
make k8s-setup-local      # Full zero-to-running setup (kind + infra + build + deploy)
make k8s-teardown         # Tear everything down and delete the kind cluster
```

### Infrastructure

```bash
make k8s-infra-setup      # Install PostgreSQL, Redis, Kafka via Helm
make k8s-infra-teardown   # Uninstall Helm releases (keeps kind cluster)
make k8s-init-jobs        # Run db-init + kafka-init jobs (creates databases and topics)
make k8s-secrets          # Generate K8s Secrets from k8s/secrets.env
```

### Application

```bash
make k8s-build                          # Build all 5 Docker images and load into kind
make k8s-deploy                         # Deploy with dev overlay (default)
make k8s-deploy OVERLAY=staging-kind    # Deploy with a different overlay
make k8s-validate                       # Dry-run YAML validation (no cluster changes)
make k8s-validate OVERLAY=prod          # Validate a specific overlay

make k8s-redeploy SVC=auth-service      # Rebuild image + reload into kind + rolling restart
make k8s-redeploy SVC=chat-service      # Same for chat-service
```

### Operations

```bash
make k8s-status                         # Show pods, services, infra, recent events
make k8s-logs SVC=auth-service          # Tail live logs (all pods for that service)
make k8s-logs SVC=chat-service          # Same for chat-service
make k8s-shell SVC=auth-service         # Open a shell inside a running pod
make k8s-restart SVC=message-service    # Rolling restart (zero downtime)
make k8s-port-forward                   # Print access URLs (NodePort already exposed)
```

### Monitoring

```bash
make k8s-monitoring-setup   # Install Prometheus + Grafana (first time only)
make k8s-grafana            # Print Grafana URL and credentials
make k8s-prometheus         # Port-forward Prometheus → http://localhost:9090
```

---

## Kubernetes Scripts

All scripts live in `k8s/scripts/`. Run them from the project root.

### Before You Run Any Script

**1. Create your secrets file** (first time only):

```bash
cp k8s/base/secrets.env.example k8s/secrets.env
# Edit k8s/secrets.env with your passwords — never commit this file
```

The file contains:

```bash
POSTGRES_PASSWORD=chatbox_pass      # PostgreSQL password for all 4 service databases
REDIS_PASSWORD=chatbox_redis_pass   # Redis auth password
SECRET_KEY=change-this-in-prod      # JWT signing secret (use: openssl rand -hex 32)
ADMIN_USERNAME=admin                # Bootstrap admin user created on first deploy
ADMIN_PASSWORD=changeme             # Bootstrap admin password
```

> If `k8s/secrets.env` is missing, scripts fall back to the insecure example defaults — fine for local dev, never for staging/prod.

**2. Install the WebSocket test dependency** (for `e2e-test.sh` only):

```bash
pip install websockets
# or: pip3 install websockets
```

Without this, the WebSocket test in `e2e-test.sh` silently skips rather than fails.

---

### Script Reference

| Script | What It Does | Usage |
|--------|-------------|-------|
| `setup-local.sh` | Full setup: creates kind cluster → installs Postgres/Redis/Kafka → generates secrets → runs init jobs → builds images → deploys app | `bash k8s/scripts/setup-local.sh` |
| `teardown.sh` | Removes app, init jobs, Helm releases, monitoring, and deletes the kind cluster | `bash k8s/scripts/teardown.sh` |
| `build-images.sh` | Builds Docker images for all 5 services and loads them into the kind cluster | `bash k8s/scripts/build-images.sh` |
| `deploy.sh` | Applies a Kustomize overlay and waits for all 6 rollouts to complete | `bash k8s/scripts/deploy.sh [overlay]` |
| `generate-secrets.sh` | Creates or updates all K8s Secrets from `k8s/secrets.env`. Reads the actual Redis password from the cluster to work around Bitnami's password-on-upgrade behavior | `bash k8s/scripts/generate-secrets.sh` |
| `e2e-test.sh` | Full end-to-end functional test — 46 tests across every service, WebSocket, and monitoring. Requires `python3` + `pip install websockets` | `bash k8s/scripts/e2e-test.sh` |

### setup-local.sh

```bash
bash k8s/scripts/setup-local.sh
```

Runs 7 steps in order:
1. Creates kind cluster `chatbox` with NodePorts 30000/30080/30030 — **idempotent**, skips if cluster already exists
2. Creates namespaces: `chatbox`, `chatbox-infra`, `chatbox-monitoring`
3. Installs PostgreSQL v18.5.14 + Redis v25.3.9 via Helm, Kafka via manifest
4. Generates K8s Secrets from `k8s/secrets.env`
5. Runs `db-init` job (creates 4 databases + tables) and `kafka-init` job (creates topics)
6. Builds all 5 Docker images and loads them into kind
7. Deploys with the `dev` overlay + re-applies secrets (Kustomize overwrites them)

### teardown.sh

```bash
bash k8s/scripts/teardown.sh
```

Runs 5 steps in order:
1. Deletes all application resources (dev overlay)
2. Deletes init jobs
3. Uninstalls Redis + PostgreSQL Helm releases, removes Kafka manifest
4. Uninstalls the Prometheus/Grafana monitoring Helm release
5. Deletes the kind cluster

### build-images.sh

```bash
bash k8s/scripts/build-images.sh
```

Builds all 5 images in sequence and loads each into the kind cluster:
- `auth-service:latest` ← `services/auth-service/`
- `chat-service:latest` ← `services/chat-service/`
- `message-service:latest` ← `services/message-service/`
- `file-service:latest` ← `services/file-service/`
- `frontend:latest` ← `frontend/` (with `VITE_API_BASE=http://localhost:30080`)

Run this after code changes, then `make k8s-redeploy SVC=<name>` for a specific service, or `make k8s-deploy` to redeploy everything.

### deploy.sh

```bash
bash k8s/scripts/deploy.sh           # defaults to dev overlay
bash k8s/scripts/deploy.sh dev
bash k8s/scripts/deploy.sh staging-kind   # staging config with local images
bash k8s/scripts/deploy.sh prod-kind      # prod config with local images
bash k8s/scripts/deploy.sh staging        # requires DockerHub images to exist
bash k8s/scripts/deploy.sh prod           # requires DockerHub images to exist
```

Applies `kubectl apply -k k8s/overlays/<overlay>` then waits for all 6 deployments (`auth-service`, `chat-service`, `message-service`, `file-service`, `frontend`, `kong`) to finish rolling out.

### generate-secrets.sh

```bash
bash k8s/scripts/generate-secrets.sh
```

Creates or updates 6 K8s Secrets in the `chatbox` namespace:
- `chatbox-infra-secrets` — shared passwords and JWT key
- `auth-service-secrets`, `chat-service-secrets`, `message-service-secrets`, `file-service-secrets` — per-service `DATABASE_URL`
- `auth-admin-secret` — admin username + password

**Important:** Bitnami Redis v25 ignores `--set auth.password` on `helm upgrade` if the secret already exists. This script reads the actual Redis password from the cluster (`kubectl get secret redis`) so the `REDIS_URL` in the app secrets always matches the real password.

### e2e-test.sh

```bash
# Run against the default local cluster
bash k8s/scripts/e2e-test.sh

# Run against a custom endpoint (e.g. staging)
bash k8s/scripts/e2e-test.sh http://staging.example.com http://staging.example.com:3000 http://grafana.example.com
```

**Arguments (all optional):**
- `$1` — Kong URL (default: `http://localhost:30080`)
- `$2` — Frontend URL (default: `http://localhost:30000`)
- `$3` — Grafana URL (default: `http://localhost:30030`)

**Dependencies:**
- `python3` — for JSON parsing and WebSocket test
- `pip install websockets` — for WebSocket test (silently skipped if missing)
- `kubectl` — to read admin credentials and check Prometheus targets

**Reads admin credentials automatically** from the `auth-admin-secret` K8s Secret — no hardcoded passwords.

Tests cover (8 sections, 46 tests total):
- **Frontend** — HTML served through Kong
- **Auth** — Register, duplicate detection, login (JWT), wrong password, token ping
- **Chat rooms** — List rooms, admin creates room (RBAC), regular user blocked (403)
- **WebSocket** — Connect to room, send message, receive broadcast
- **Messages** — History endpoint, replay (`?since=`), auth enforcement
- **Files** — Multipart upload, list, download with content verification
- **Logout** — Token blacklisted in Redis after logout; other users unaffected
- **Monitoring** — Grafana health + datasources, Prometheus targets + app metrics

---

## Monitoring (Grafana + Prometheus)

Install the monitoring stack (first time only):
```bash
make k8s-monitoring-setup
```

### Grafana

```
URL:      http://localhost:30030
Username: admin
Password: admin
```

```bash
# Or open it via make
make k8s-grafana
```

Pre-loaded dashboards (Dashboards → Browse):
- **Kubernetes / Compute Resources / Namespace (Pods)** — CPU and memory per pod
- **Kubernetes / Compute Resources / Cluster** — Cluster-wide resource usage
- **Node Exporter / Nodes** — Host machine metrics

### Prometheus

```bash
# Port-forward to http://localhost:9090
make k8s-prometheus
```

Useful queries in the Prometheus UI:
```promql
# CPU usage per chatbox pod
rate(container_cpu_usage_seconds_total{namespace="chatbox"}[5m])

# Memory per chatbox pod
container_memory_working_set_bytes{namespace="chatbox"}

# Active HTTP requests (if service exposes /metrics)
http_requests_total{namespace="chatbox"}
```

Quick health check (no browser needed):
```bash
make k8s-status                                         # all pods running?
kubectl top pods -n chatbox                             # live CPU/memory
kubectl get events -n chatbox --field-selector type=Warning  # any warnings?
```

---

## Running Tests

```bash
# Auth service (Python)
cd services/auth-service
pytest tests/ -v

# Chat service (Go)
cd services/chat-service
go test ./... -v

# Message service (Python)
cd services/message-service
pytest tests/ -v

# File service (Node.js/TypeScript)
cd services/file-service
npm test

# Legacy monolith tests (reference only)
cd v1/backend
pytest tests/ -v
```

---

## Health Checks

```bash
# Through Kong gateway (production)
curl http://localhost/api/auth/health
curl http://localhost/api/chat/health
curl http://localhost/api/messages/health
curl http://localhost/api/files/health

# Direct service access (development)
curl http://localhost:8001/health     # Auth service
curl http://localhost:8003/health     # Chat service
curl http://localhost:8004/health     # Message service
curl http://localhost:8005/health     # File service
```

---

## Environment Configuration

Copy `.env.example` to `.env` and customize. Key variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ENV` | `dev` | Environment mode: `dev`, `staging`, `prod` |
| `SECRET_KEY` | (change me) | JWT signing key (shared across all services) |
| `POSTGRES_USER` | `chatbox` | PostgreSQL superuser |
| `POSTGRES_PASSWORD` | `chatbox_pass` | PostgreSQL password |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | Kafka broker address (host), `kafka:9092` (Docker) |
| `KONG_DATABASE` | `off` | Kong config mode (dbless) |

Each service connects to its own database (`chatbox_auth`, `chatbox_chat`, `chatbox_messages`, `chatbox_files`) created automatically by the init script.

See the [Operations Guide](docs/OPERATIONS_GUIDE.md) for full configuration reference.
