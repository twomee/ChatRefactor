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

### Option A: Full Microservices Stack (Docker)

```bash
cp .env.example .env                          # configure environment
docker compose -f docker-compose.microservices.yml up -d --build  # start all services
```

Services available at:
- **App**: http://localhost (Kong gateway)
- **Kong Admin**: http://localhost:8001
- **Auth Service**: http://localhost:8001
- **Chat Service**: http://localhost:8003
- **Message Service**: http://localhost:8004
- **File Service**: http://localhost:8005

### Option B: Monolith Stack (Docker)

```bash
cp .env.example .env          # configure environment
docker compose up -d --build  # start all 5 services
```

App available at **http://localhost**

### Option C: Local Development (recommended for daily work)

```bash
# 1. Start infrastructure
docker compose -f docker-compose.dev.yml up -d

# 2. Start backend (monolith)
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 3. Start frontend (in a new terminal)
cd frontend
npm install
npm run dev
```

Frontend at **http://localhost:5173** | API at **http://localhost:8000** | API Docs at **http://localhost:8000/docs**

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
├── backend/                     # Monolith FastAPI server
│   ├── main.py                  # Entry point with lifespan hooks
│   ├── routers/                 # API endpoints (auth, rooms, ws, files, admin, pm, messages)
│   ├── services/                # Business logic layer
│   ├── dal/                     # Data access layer (database queries)
│   ├── models.py                # SQLAlchemy ORM models
│   ├── ws_manager.py            # WebSocket state + Redis pub/sub relay
│   ├── kafka_client.py          # Kafka producer (graceful degradation)
│   ├── kafka_consumers.py       # Kafka consumer (async persistence + DLQ)
│   ├── alembic/                 # Database migrations
│   ├── tests/                   # Test suite (111 tests, 87% coverage)
│   ├── Dockerfile               # Production container (Python 3.11 + Gunicorn)
│   └── requirements.txt
│
├── services/                    # Microservices
│   ├── auth-service/            # Python/FastAPI — JWT auth, registration, token blacklist
│   │   ├── app/                 # FastAPI application (routers, services, dal, models)
│   │   ├── alembic/             # Database migrations
│   │   ├── tests/               # pytest test suite
│   │   ├── Dockerfile           # Production container
│   │   └── requirements.txt
│   │
│   ├── chat-service/            # Go — WebSocket server, real-time messaging
│   │   ├── cmd/                 # Entry point
│   │   ├── internal/            # Handlers, hub, Redis pub/sub
│   │   ├── migrations/          # SQL migrations
│   │   └── Dockerfile
│   │
│   ├── message-service/         # Python/FastAPI — message history, replay, persistence
│   │   ├── app/                 # FastAPI application (routers, services, dal, consumers)
│   │   ├── alembic/             # Database migrations
│   │   ├── tests/               # pytest test suite
│   │   ├── Dockerfile           # Production container
│   │   └── requirements.txt
│   │
│   └── file-service/            # Node.js/TypeScript — file upload, download, metadata
│       ├── src/                 # Express app (routes, services, middleware, kafka)
│       ├── prisma/              # Prisma ORM schema
│       ├── tests/               # Vitest test suite
│       ├── Dockerfile           # Production container
│       └── package.json
│
├── frontend/                    # React + Vite app
│   ├── src/
│   │   ├── pages/               # LoginPage, ChatPage, AdminPage
│   │   ├── components/          # MessageList, RoomList, UserList, PMView, etc.
│   │   ├── context/             # AuthContext, ChatContext, PMContext
│   │   ├── services/            # API client wrappers (authApi, roomApi, pmApi, etc.)
│   │   ├── hooks/               # Custom hooks (useMultiRoomChat)
│   │   └── api/http.js          # Axios instance with JWT interceptor
│   ├── nginx.conf               # Reverse proxy config (API + WebSocket + SPA)
│   ├── Dockerfile               # Production container (Node 20 build + Nginx 1.25)
│   └── package.json
│
├── loadtests/                   # Load testing suite (Locust)
│   ├── locustfile.py            # Microservices load test (4 user classes via Kong)
│   ├── scenarios/               # Monolith-era scenario files
│   ├── scripts/                 # Automation and CI gate scripts
│   ├── benchmarks/              # pytest-benchmark micro-benchmarks
│   └── README.md                # Load test documentation
│
├── docs/                        # Documentation
│   ├── OPERATIONS_GUIDE.md      # How to run, debug, and troubleshoot
│   └── ARCHITECTURE_AND_TECH_DECISIONS.md  # Why every technology was chosen
│
├── .github/workflows/           # CI/CD pipelines
│   ├── ci.yml                   # Monolith CI (lint, test, build)
│   ├── ci-auth.yml              # Auth service CI
│   ├── ci-chat.yml              # Chat service CI
│   ├── ci-message.yml           # Message service CI
│   ├── ci-file.yml              # File service CI
│   ├── security.yml             # Trivy vulnerability scanning
│   └── secrets.yml              # Gitleaks secret scanning
│
├── docker-compose.yml           # Production: monolith stack
├── docker-compose.microservices.yml  # Production: microservices stack
├── docker-compose.dev.yml       # Development: PostgreSQL + Redis + Kafka only
├── .env.example                 # Environment variable template
└── .env                         # Local environment config (not committed)
```

---

## Documentation

| Document | What's in it |
|----------|-------------|
| **[Operations Guide](docs/OPERATIONS_GUIDE.md)** | Step-by-step setup for dev/staging/production, PostgreSQL commands, Redis commands, Kafka commands, health checks, troubleshooting, microservices operations |
| **[Architecture & Tech Decisions](docs/ARCHITECTURE_AND_TECH_DECISIONS.md)** | Why every technology and library was chosen, data flow diagrams, microservice architecture, alternatives considered, design trade-offs |
| **[Dev Platform Guide](DEV_PLATFORM_GUIDE.md)** | CI/CD pipelines, linting, testing, security scanning, per-service CI |
| **[Load Tests](loadtests/README.md)** | Load testing suite, performance baselines, user classes, pass/fail criteria |

---

## Running Tests

```bash
# Monolith backend tests
cd backend
pytest tests/ -v

# Auth service tests
cd services/auth-service
pytest tests/ -v

# Message service tests
cd services/message-service
pytest tests/ -v

# Chat service tests (Go)
cd services/chat-service
go test ./...

# File service tests (Node.js)
cd services/file-service
npm test
```

---

## Health Checks

```bash
# Monolith
curl http://localhost:8000/health    # Liveness: is the process running?
curl http://localhost:8000/ready     # Readiness: DB + Redis + Kafka status

# Microservices (through Kong)
curl http://localhost/api/auth/health
curl http://localhost/api/chat/health
curl http://localhost/api/messages/health
curl http://localhost/api/files/health

# Kong Gateway status
curl http://localhost:8001/status
```

---

## Environment Configuration

Copy `.env.example` to `.env` and customize. Key variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ENV` | `dev` | Environment mode: `dev`, `staging`, `prod` |
| `SECRET_KEY` | (change me) | JWT signing key (shared across services) |
| `DATABASE_URL` | `postgresql://chatbox:chatbox_pass@localhost:5432/chatbox` | PostgreSQL connection (monolith) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | Kafka broker address |
| `KONG_DATABASE` | `off` | Kong config mode (dbless) |

See the [Operations Guide](docs/OPERATIONS_GUIDE.md) for full configuration reference.
