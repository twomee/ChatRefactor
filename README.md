# cHATBOX

A production-ready, real-time chat application with multi-room support, private messaging, file sharing, and admin controls — built as a **microservices architecture** with **FastAPI**, **Go**, **Node.js/TypeScript**, **React**, **PostgreSQL**, **Redis**, **Kafka**, and **Kong API Gateway**.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, Axios, React Router |
| API Gateway | Kong (routes, auth, rate limiting) |
| Auth Service | Python, FastAPI, Argon2, JWT |
| Chat Service | Go, Gin, gorilla/websocket |
| Message Service | Python, FastAPI, SQLAlchemy, Alembic |
| File Service | Node.js, TypeScript, Express, Multer |
| Database | PostgreSQL 16 (database per service) |
| Cache | Redis 7 (token blacklist, rate limiting, URL preview cache) |
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
cp .env.example .env   # configure environment
make deploy            # build all images + start all services + restart Kong
```

> **Why `make deploy` and not `docker compose up -d --build`?**
> Kong caches DNS at startup. When app containers are rebuilt and get new internal IPs, Kong still routes to the old IPs (502 errors) until it is restarted. `make deploy` handles this automatically — it rebuilds, starts, then restarts Kong so it re-resolves service names. See the [Makefile Reference](docs/development/makefile-reference.md) for all Docker Compose targets.

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

**Prerequisites:** Docker, `kubectl`, `kind`, `helm` — see [docs/operations/k8s-operations.md](docs/operations/k8s-operations.md) for install instructions.

```bash
# 1. Spin up the cluster, install infra, build images, and deploy everything
make k8s-setup-local

# 2. Verify all pods are running
make k8s-status

# 3. Run the full E2E test suite (46 tests covering every service)
bash infra/k8s/scripts/e2e-test.sh
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

For concepts and architecture: [docs/operations/k8s-concepts.md](docs/operations/k8s-concepts.md)
For step-by-step commands and troubleshooting: [docs/operations/k8s-operations.md](docs/operations/k8s-operations.md)

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

### Core
- **Multi-room chat** — Three default rooms (politics, sports, movies) + create custom rooms
- **Real-time messaging** — Native WebSocket with in-memory fan-out (single-instance); Redis pub/sub is the planned path for horizontal scaling
- **Private messages** — Direct messaging between users with online/offline presence indicators
- **File sharing** — Upload and download files in rooms (up to 150 MB)
- **Durable persistence** — Messages flow through Kafka for async database writes with DLQ support
- **Room admin controls** — Kick, mute/unmute, promote users, auto admin succession
- **Global admin panel** — Manage all rooms, users, and files from a dedicated dashboard

### Phase 1 Features (v2)
- **Message editing** — Edit your own sent messages; an "(edited)" badge is shown to all users in real time via WebSocket. Only the original sender can edit. Persisted in PostgreSQL with `edited_at` timestamp.
- **Message deletion** — Soft-delete your own messages; the content is replaced with "[deleted]" for all users in real time. The original content is preserved in the database (`is_deleted` flag) for audit purposes.
- **Emoji reactions** — React to any message with emojis using an integrated emoji picker (emoji-mart). Reactions are broadcast in real time and persisted in a `reactions` table with a unique constraint per user/emoji/message. Click an existing reaction to toggle it on/off.
- **Typing indicators** — See who is currently typing in a room. Typing events are broadcast via WebSocket (excluded from the sender) and auto-clear after 3 seconds of inactivity.
- **Read position tracking** — The server tracks each user's last-read message per room. On reconnect, the frontend receives the read position and renders a "New messages" divider. Positions are updated when the user sends a `mark_read` WebSocket command.
- **Message search** — Full-text search across all messages using PostgreSQL `tsvector` with GIN indexing for relevance-ranked results. Accessible via the Search button (or Ctrl+K). Results show sender, room, timestamp, and highlighted matching terms. Supports optional `room_id` filtering.
- **Link previews** — When a message contains a URL, the frontend fetches OpenGraph metadata (title, description, image) from the message-service's `/link-preview` endpoint and renders a compact preview card. Results are cached client-side for the session duration. The backend validates URLs against SSRF attacks (blocks private IPs, cloud metadata endpoints).
- **Two-Factor Authentication (2FA)** — TOTP-based 2FA via the Settings panel. Users scan a QR code with Google Authenticator or Authy, then verify with a 6-digit code. TOTP secrets are encrypted at rest using AES-256-GCM (`TOTP_ENCRYPTION_KEY`). A manual entry key is available for apps that can't scan QR codes.
- **Browser notifications** — Desktop notifications for @mentions. When another user mentions you with `@username`, a browser notification is sent (requires notification permission). Mention detection is case-insensitive.
- **Online presence** — Lobby-based presence tracking. Each user maintains a lobby WebSocket connection independent of room connections. When the last lobby connection closes (full logout), `user_offline` is broadcast to all connected users. On login, `user_online` is broadcast. This decouples presence from room membership — a user can leave a room without appearing offline.

### Phase 2 Features (feat/pm-files-and-persistence)
- **PM file sharing** — Upload and download files in direct message conversations. Files are stored securely with participant-only authorization — only the sender and recipient can download a private file. Images render as inline previews; other files show a download button.
- **PM history persistence** — DM message history is fetched from the server on first open and lazy-loaded per conversation. The `message-service` exposes a `GET /messages/pm/history/{username}` endpoint backed by a dedicated DB index for efficient participant-pair queries.
- **PM sidebar persistence** — The DM sidebar (list of conversations) is saved to `localStorage` and restored on page reload, so conversations reappear without needing to receive a new message first.
- **Instant logout presence** — On logout the frontend sends an explicit `{"type":"logout"}` message over the lobby WebSocket before closing it. The server skips the 5-second reconnect grace period and immediately broadcasts `user_left` to all rooms. Page refreshes are unaffected — the grace period still applies when the socket closes without the logout signal.
- **PM clear history UX fix** — Clearing a conversation's history empties the messages but keeps the contact in the sidebar. Previously the contact icon disappeared until the next page reload.

### Infrastructure
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
├── infra/                       # All infrastructure configs
│   ├── docker/init/             # init-db.sh, init-kafka.sh
│   ├── kong/                    # kong.yml (declarative gateway config)
│   └── k8s/                    # Kubernetes manifests and scripts
│       ├── base/                # Base Kustomize config (env-agnostic)
│       ├── overlays/            # Environment overlays: dev, staging, prod, *-kind
│       ├── infra/               # Helm values for PostgreSQL, Redis, Kafka
│       ├── jobs/                # Init jobs (db-init, kafka-init)
│       └── scripts/             # Automation scripts (setup, teardown, deploy, e2e)
│
├── loadtests/                   # Load testing suite (Locust)
│   ├── locustfile.py            # Microservices load test (4 user classes via Kong)
│   ├── scenarios/               # Legacy monolith scenario files
│   ├── scripts/                 # CI gate scripts
│   ├── benchmarks/              # pytest-benchmark micro-benchmarks
│   └── README.md
│
├── docs/                        # Documentation
│   ├── architecture/
│   │   ├── overview.md          # Why every technology was chosen
│   │   ├── frontend.md          # Frontend architecture and component guide
│   │   └── diagrams/            # Visual assets and diagram generators
│   ├── operations/
│   │   ├── runbook.md           # How to run, debug, and troubleshoot
│   │   ├── k8s-concepts.md      # Kubernetes architecture and concepts
│   │   ├── k8s-operations.md    # K8s commands and troubleshooting
│   │   ├── security-audit.md    # Security audit report
│   │   └── verification-checklist.md  # 174-item feature parity checklist
│   ├── development/
│   │   ├── dev-platform-guide.md     # CI/CD, linting, testing, security scanning
│   │   ├── ci-tools-setup.md         # CI tool configuration and troubleshooting
│   │   └── makefile-reference.md     # Make targets, K8s scripts, monitoring
│   └── archive/                 # Deprecated / historical docs
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
| **[Architecture & Tech Decisions](docs/architecture/overview.md)** | Why every technology was chosen, microservice architecture, design patterns, trade-offs |
| **[Frontend Explained](docs/architecture/frontend.md)** | Frontend architecture, React concepts, component structure, data flow |
| **[Operations Runbook](docs/operations/runbook.md)** | Setup, running, debugging, and troubleshooting for all microservices |
| **[K8s Concepts](docs/operations/k8s-concepts.md)** | Kubernetes architecture, namespaces, Kustomize overlays, secrets, migrations |
| **[K8s Operations](docs/operations/k8s-operations.md)** | Step-by-step K8s commands, scripts reference, troubleshooting |
| **[Security Audit](docs/operations/security-audit.md)** | Security audit report (2026-03-24) |
| **[Verification Checklist](docs/operations/verification-checklist.md)** | 174-item feature parity checklist (171/174 passed) |
| **[Dev Platform Guide](docs/development/dev-platform-guide.md)** | CI/CD pipelines, per-service linting/testing, security scanning, pre-commit hooks |
| **[CI Tools Setup](docs/development/ci-tools-setup.md)** | CodeQL, SonarCloud, Codecov configuration and troubleshooting |
| **[Makefile Reference](docs/development/makefile-reference.md)** | Make targets, K8s scripts, monitoring setup |
| **[Kafka Event Contracts](services/contracts/README.md)** | Kafka event schemas, producer/consumer mapping, contract rules |
| **[Load Tests](loadtests/README.md)** | Load testing suite, performance baselines, user classes, pass/fail criteria |

---

For the full Makefile reference, K8s scripts, and monitoring setup, see [docs/development/makefile-reference.md](docs/development/makefile-reference.md).

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
| `TOTP_ENCRYPTION_KEY` | (generate) | AES-256-GCM key for encrypting 2FA TOTP secrets (`python3 -c "import secrets; print(secrets.token_hex(32))"`) |
| `KONG_DATABASE` | `off` | Kong config mode (dbless) |

Each service connects to its own database (`chatbox_auth`, `chatbox_chat`, `chatbox_messages`, `chatbox_files`) created automatically by the init script.

See the [Operations Runbook](docs/operations/runbook.md) for full configuration reference.
