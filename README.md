# cHATBOX

A production-ready, real-time chat application with multi-room support, private messaging, file sharing, and admin controls — built with **FastAPI**, **React**, **PostgreSQL**, **Redis**, and **Kafka**.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, Axios, React Router |
| Backend | FastAPI, SQLAlchemy, Gunicorn, Uvicorn |
| Database | PostgreSQL 16 |
| Cache & PubSub | Redis 7 |
| Message Queue | Apache Kafka (KRaft) |
| Reverse Proxy | Nginx 1.25 |
| Containerization | Docker, Docker Compose |

---

## Quick Start

### Option A: Full Production Stack (Docker)

```bash
cp .env.example .env          # configure environment
docker compose up -d --build  # start all 5 services
```

App available at **http://localhost**

### Option B: Local Development (recommended for daily work)

```bash
# 1. Start infrastructure
docker compose -f docker-compose.dev.yml up -d

# 2. Start backend
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
- **Health checks** — `/health` (liveness) and `/ready` (readiness) endpoints
- **Rate limiting** — Per-IP rate limits with Redis-backed state in production
- **Structured logging** — Human-readable in dev, JSON in production

---

## Project Structure

```
Chat-Project-Final/
├── backend/                  # FastAPI server
│   ├── main.py               # Entry point with lifespan hooks
│   ├── routers/              # API endpoints (auth, rooms, ws, files, admin, pm, messages)
│   ├── services/             # Business logic layer
│   ├── dal/                  # Data access layer (database queries)
│   ├── models.py             # SQLAlchemy ORM models
│   ├── ws_manager.py         # WebSocket state + Redis pub/sub relay
│   ├── kafka_client.py       # Kafka producer (graceful degradation)
│   ├── kafka_consumers.py    # Kafka consumer (async persistence + DLQ)
│   ├── alembic/              # Database migrations
│   ├── tests/                # Test suite
│   ├── Dockerfile            # Production container (Python 3.11 + Gunicorn)
│   └── requirements.txt
│
├── frontend/                 # React + Vite app
│   ├── src/
│   │   ├── pages/            # LoginPage, ChatPage, AdminPage
│   │   ├── components/       # MessageList, RoomList, UserList, PMView, etc.
│   │   ├── context/          # AuthContext, ChatContext, PMContext
│   │   ├── services/         # API client wrappers (authApi, roomApi, pmApi, etc.)
│   │   ├── hooks/            # Custom hooks (useMultiRoomChat)
│   │   └── api/http.js       # Axios instance with JWT interceptor
│   ├── nginx.conf            # Reverse proxy config (API + WebSocket + SPA)
│   ├── Dockerfile            # Production container (Node 20 build + Nginx 1.25)
│   └── package.json
│
├── docs/                     # Documentation
│   ├── OPERATIONS_GUIDE.md   # How to run, debug, and troubleshoot
│   └── ARCHITECTURE_AND_TECH_DECISIONS.md  # Why every technology was chosen
│
├── docker-compose.yml        # Production: all services
├── docker-compose.dev.yml    # Development: PostgreSQL + Redis + Kafka only
├── .env.example              # Environment variable template
└── .env                      # Local environment config (not committed)
```

---

## Documentation

| Document | What's in it |
|----------|-------------|
| **[Operations Guide](docs/OPERATIONS_GUIDE.md)** | Step-by-step setup for dev/staging/production, PostgreSQL commands, Redis commands, Kafka commands, health checks, troubleshooting |
| **[Architecture & Tech Decisions](docs/ARCHITECTURE_AND_TECH_DECISIONS.md)** | Why every technology and library was chosen, data flow diagrams, alternatives considered, design trade-offs |

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

---

## Health Checks

```bash
curl http://localhost:8000/health    # Liveness: is the process running?
curl http://localhost:8000/ready     # Readiness: DB + Redis + Kafka status
```

---

## Environment Configuration

Copy `.env.example` to `.env` and customize. Key variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ENV` | `dev` | Environment mode: `dev`, `staging`, `prod` |
| `SECRET_KEY` | (change me) | JWT signing key |
| `DATABASE_URL` | `postgresql://chatbox:chatbox_pass@localhost:5432/chatbox` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | Kafka broker address |

See the [Operations Guide](docs/OPERATIONS_GUIDE.md) for full configuration reference.
