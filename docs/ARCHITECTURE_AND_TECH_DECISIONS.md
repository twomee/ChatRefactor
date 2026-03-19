# Architecture & Technology Decisions

Why we chose every piece of technology in cHATBOX — from infrastructure to individual libraries.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Infrastructure: Why These Services](#2-infrastructure-why-these-services)
   - [PostgreSQL](#postgresql)
   - [Redis](#redis)
   - [Apache Kafka](#apache-kafka)
   - [Nginx](#nginx)
   - [Docker & Docker Compose](#docker--docker-compose)
3. [Backend: Why These Libraries](#3-backend-why-these-libraries)
   - [Framework & Server](#framework--server)
   - [Database & Migrations](#database--migrations)
   - [Authentication & Security](#authentication--security)
   - [Real-Time Communication](#real-time-communication)
   - [Messaging & Async Processing](#messaging--async-processing)
   - [Observability & Protection](#observability--protection)
   - [Utilities & Testing](#utilities--testing)
4. [Frontend: Why These Libraries](#4-frontend-why-these-libraries)
   - [Core Framework](#core-framework)
   - [Build Tooling](#build-tooling)
   - [HTTP & Networking](#http--networking)
   - [Code Quality](#code-quality)
5. [Data Flow: How It All Connects](#5-data-flow-how-it-all-connects)
6. [What Alternatives Were Considered](#6-what-alternatives-were-considered)

---

## 1. System Architecture

cHATBOX separates three concerns that often get tangled in chat apps:

| Concern | What handles it | Why separate? |
|---------|----------------|---------------|
| **Real-time delivery** | WebSocket + Redis pub/sub | Must be fast (sub-100ms). No disk I/O. |
| **Durable storage** | Kafka + PostgreSQL | Can be async. Needs reliability, not speed. |
| **Static serving + routing** | Nginx | Offloads TLS, compression, and SPA routing from the app server. |

This separation means a slow database query doesn't block message delivery, and a WebSocket spike doesn't overwhelm the database.

---

## 2. Infrastructure: Why These Services

### PostgreSQL

**What it does here:** Stores users, rooms, messages, files metadata, admin assignments, and muted users.

**Why PostgreSQL over alternatives:**

| Considered | Why not |
|-----------|---------|
| SQLite | No concurrent writes. Works for dev, breaks with multiple Gunicorn workers writing at once. No network access — can't share between containers. |
| MySQL | Would work, but PostgreSQL has better JSON support, better default behavior for concurrent access, and is the more common choice in the Python ecosystem. |
| MongoDB | Our data is highly relational (users belong to rooms, messages reference both sender and room, admins are a join between users and rooms). Document stores make these relationships awkward and denormalized. |

**Key PostgreSQL features we rely on:**

- **ACID transactions** — When a user sends a message, we need the insert to either fully succeed or fully fail. No partial writes.
- **Foreign keys** — The database enforces that a message can't reference a non-existent user or room. This catches bugs that would silently corrupt data in schema-less stores.
- **`ON CONFLICT DO NOTHING`** — Used for Kafka idempotent writes. When the same `message_id` arrives twice (Kafka at-least-once delivery), PostgreSQL skips the duplicate instead of crashing.
- **Connection pooling** (`pool_size=10, max_overflow=20`) — Reuses database connections across requests instead of opening a new one per query.
- **`pool_pre_ping=True`** — Tests each connection before using it. Prevents "connection closed" errors after database restarts.

---

### Redis

**What it does here:** Three jobs, each leveraging a different Redis capability.

#### Job 1: WebSocket Message Relay (Pub/Sub)

**The problem:** When running multiple Gunicorn workers (separate processes), each worker has its own set of WebSocket connections. If User A's WebSocket is on Worker 1 and User B's is on Worker 2, Worker 1 can't directly send to User B.

**The solution:** Redis pub/sub acts as a message bus between workers.

```
User A sends message
    → Worker 1 receives it
    → Worker 1 publishes to Redis channel "room:5"
    → ALL workers (including Worker 2) receive from Redis
    → Worker 2 delivers to User B's WebSocket
```

**Why Redis for pub/sub (not Kafka)?** Redis pub/sub is fire-and-forget with zero latency overhead. Messages are delivered instantly to subscribers and then gone. We don't need durability here — if a message is missed because a worker crashed, the user will see it when they reconnect (loaded from the database). Kafka's pub/sub adds unnecessary overhead (disk writes, consumer group coordination) for something that should be instant and ephemeral.

**Channels we use:**
- `room:<room_id>` — Room chat messages
- `lobby` — Global updates (room created, room closed, user count changes)
- `user:<username>` — Targeted messages (PMs, kick notifications)

#### Job 2: Token Blacklist (Key-Value)

**The problem:** JWTs are stateless — once issued, they're valid until they expire. When a user logs out, we need to invalidate their token immediately.

**The solution:** On logout, store the token in Redis with a TTL matching the token's remaining lifetime:
```
SET blacklist:<token> "1" EX 86400
```
On every authenticated request, check if the token is blacklisted before accepting it.

**Why Redis (not the database)?** This check happens on every single API request. Redis responds in ~0.1ms from memory. PostgreSQL would be ~1-5ms with disk I/O. At 100 requests/second, that's the difference between 10ms and 500ms of cumulative overhead.

#### Job 3: Rate Limiting State (Key-Value with TTL)

**The problem:** In staging/production, we rate-limit API endpoints (5 registrations/minute, 10 logins/minute, 100 general requests/minute). The rate limiter needs to count requests per IP across all workers.

**The solution:** `slowapi` stores counters in Redis, so all Gunicorn workers share the same rate limit state.

**Why not in-memory?** In-memory rate limiting is per-worker. With 4 workers, a user could make 400 requests/minute instead of 100.

---

### Apache Kafka

**What it does here:** Decouples the real-time message path from the database write path.

**The problem it solves:**

Without Kafka, every chat message must be synchronously written to PostgreSQL before the user gets a response. If the database is slow (high load, vacuum running, complex query), message delivery slows down too.

**With Kafka:**
```
1. User sends message via WebSocket
2. Backend publishes to Kafka (async, ~1ms)
3. Backend broadcasts via Redis pub/sub (instant delivery to all users)
4. Kafka consumer picks up the message (background)
5. Consumer persists to PostgreSQL (async, no user waiting)
```

The user sees the message instantly (step 3). The database write happens whenever it happens (step 5). Even if the database is down for 5 minutes, messages are buffered in Kafka and will be persisted when it comes back.

**Why Kafka over alternatives:**

| Considered | Why not |
|-----------|---------|
| RabbitMQ | Good for task queues but messages are deleted after consumption. Kafka retains messages for 7 days — you can replay them if something goes wrong. |
| Redis Streams | Could work for small scale, but doesn't have native consumer groups with the same reliability guarantees. Kafka handles backpressure better. |
| Direct DB writes | Works but couples message delivery speed to database speed. Under load, users experience lag. |
| No persistence | Messages would be ephemeral only. Users who go offline lose everything. |

**Key Kafka features we rely on:**

- **Consumer groups** (`chat-persistence`) — If we scale to multiple consumer instances, Kafka distributes partitions across them automatically.
- **At-least-once delivery** — Kafka guarantees every message will be consumed at least once. Combined with `ON CONFLICT DO NOTHING` in PostgreSQL, we get exactly-once semantics.
- **Dead Letter Queue** (`chat.dlq`) — Messages that fail 3 times go to a separate topic for investigation instead of being lost.
- **LZ4 compression** — Reduces network and disk usage with minimal CPU overhead.
- **KRaft mode** — Runs without ZooKeeper, simplifying our deployment to a single Kafka container.
- **Configurable retention** — 7 days for messages, 3 days for events, 30 days for DLQ. Old data is automatically cleaned up.

**Graceful degradation:** If Kafka is down, the backend falls back to synchronous database writes. Users don't notice — messages still get delivered in real-time via Redis and persisted to the database directly.

---

### Nginx

**What it does here:** Reverse proxy in front of the React SPA and FastAPI backend.

**Why we need it:**

1. **SPA routing** — React Router uses client-side routes (`/chat`, `/admin`). Without Nginx's `try_files $uri /index.html`, refreshing the page on `/chat` would return a 404 because no file exists at that path.

2. **API path rewriting** — The frontend calls `/api/auth/login`. Nginx strips `/api` and forwards to the backend as `/auth/login`. This keeps the backend unaware of the proxy and lets us change the URL structure without touching backend code.

3. **WebSocket upgrade** — Nginx handles the HTTP→WebSocket protocol upgrade (`Connection: upgrade`), with a long read timeout (86400s = 24 hours) so connections aren't dropped.

4. **Static file serving** — Nginx serves the React build files (JS, CSS, images) directly from disk, which it does much faster than any application server.

5. **File upload limits** — `client_max_body_size 150M` allows our 150MB file uploads without the backend needing to handle chunked transfer encoding at the proxy level.

**Why Nginx over alternatives:**

| Considered | Why not |
|-----------|---------|
| Caddy | Simpler config, auto-HTTPS. But Nginx has better WebSocket support, more ecosystem resources, and we don't need HTTPS in Docker-to-Docker communication. |
| Traefik | Over-engineered for a single-backend setup. Traefik shines with dynamic service discovery in Kubernetes. |
| No proxy (serve from FastAPI) | FastAPI/Uvicorn can serve static files, but it's single-threaded per worker. Nginx handles thousands of concurrent static file requests without breaking a sweat. |

---

### Docker & Docker Compose

**What it does here:** Packages every service (PostgreSQL, Redis, Kafka, backend, frontend) into isolated containers with deterministic dependencies.

**Why Docker:**

1. **Reproducible environments** — `python:3.11-slim` and `node:20-alpine` give us exact, known base images. No "works on my machine" issues.
2. **Service isolation** — Each service runs in its own container with its own filesystem. A Kafka crash can't corrupt the PostgreSQL data directory.
3. **Health checks and dependency ordering** — `depends_on: { postgres: { condition: service_healthy } }` ensures the backend doesn't start until PostgreSQL is actually accepting connections.
4. **Volume management** — `pgdata` persists database files across container restarts. `uploads` persists user-uploaded files.

**Two Compose files for two workflows:**

| File | When to use | What it runs |
|------|------------|--------------|
| `docker-compose.dev.yml` | Daily development | Only PostgreSQL, Redis, Kafka. Backend and frontend run natively for hot-reload. |
| `docker-compose.yml` | Production / CI | All 5 services including backend (Gunicorn) and frontend (Nginx). |

**Why Docker Compose (not Kubernetes):**

Kubernetes makes sense when you need auto-scaling, rolling deployments across multiple nodes, and service mesh. For a single-server deployment, Docker Compose gives the same container benefits with 10% of the complexity.

---

## 3. Backend: Why These Libraries

### Framework & Server

#### `fastapi` — Web Framework

**What it does:** Handles HTTP routing, request validation, dependency injection, WebSocket support, and auto-generates OpenAPI docs.

**Why FastAPI over alternatives:**

| Considered | Why not |
|-----------|---------|
| Django | Full batteries-included framework. Too heavy for a WebSocket-centric app. Django Channels adds async, but it's bolted on, not native. |
| Flask | Simple and mature, but synchronous by default. WebSocket support requires `flask-socketio` (which uses Socket.IO protocol, not native WebSocket). No built-in validation or dependency injection. |
| Express.js (Node) | Would work, but we wanted Python for the backend. Also, FastAPI's type-based validation is more robust than Express middleware. |

**FastAPI features we actively use:**
- **Pydantic validation** — Request/response schemas are validated automatically. A malformed JSON body returns a clear 422 error, not a 500 crash.
- **Dependency injection** — `Depends(get_db)` gives each request its own database session and auto-closes it. `Depends(get_current_user)` handles JWT validation on every protected endpoint.
- **Native WebSocket** — First-class `@router.websocket()` support without extra libraries.
- **Auto-generated docs** — `/docs` gives us Swagger UI for testing endpoints. Free and always up-to-date.

#### `uvicorn[standard]` — ASGI Server (Development)

**What it does:** Runs the FastAPI application in development with `--reload` for auto-restart on code changes.

**Why the `[standard]` extra:** Installs `uvloop` (faster event loop) and `httptools` (faster HTTP parsing). Both are C-based replacements for Python's default implementations, giving ~2-3x better throughput.

#### `gunicorn` — Process Manager (Production)

**What it does:** Spawns multiple Uvicorn worker processes, so the backend can use all CPU cores.

**Why we need it:** Uvicorn alone runs a single process. With Gunicorn as the process manager, we get:
- Multiple workers (formula: `min(cpu_count * 2 + 1, 8)`)
- Automatic worker restart if one crashes
- Graceful shutdown (waits for in-flight requests)

**Configuration:** `worker_class = "uvicorn.workers.UvicornWorker"` means each Gunicorn worker runs a full Uvicorn async event loop. It's not threading — it's genuine multiprocessing with async I/O inside each process.

---

### Database & Migrations

#### `sqlalchemy` — ORM (Object-Relational Mapper)

**What it does:** Maps Python classes to database tables. Lets us write queries as Python code instead of raw SQL.

**Why SQLAlchemy over alternatives:**

| Considered | Why not |
|-----------|---------|
| Raw SQL / `psycopg2` | Works for simple queries, but managing connections, transactions, and result mapping by hand becomes error-prone at scale. |
| Django ORM | Tightly coupled to Django. Can't use it standalone with FastAPI. |
| Tortoise ORM | Async-native, but less mature. SQLAlchemy 2.0 added optional async support while keeping its battle-tested synchronous engine. |
| Peewee | Simpler but less powerful. No connection pooling, weaker migration story. |

**Key SQLAlchemy features we use:**
- **Connection pooling** (`pool_size=10, max_overflow=20`) — Maintains a pool of reusable connections instead of opening/closing one per request.
- **`pool_pre_ping=True`** — Before using a pooled connection, SQLAlchemy runs a quick health check. Prevents "server has gone away" errors after database restarts.
- **DeclarativeBase** — Defines models as Python classes with type-annotated columns. Clean, readable schema definition.
- **Session management** — `SessionLocal()` gives each request an isolated transaction that auto-rolls-back on error.

#### `psycopg2-binary` — PostgreSQL Driver

**What it does:** The low-level driver that SQLAlchemy uses to talk to PostgreSQL over the network.

**Why `binary`:** The `-binary` variant includes pre-compiled C libraries. Without it, you'd need `libpq-dev` and a C compiler on every machine. The binary package trades a slight size increase for zero build-time dependencies.

#### `alembic` — Database Migrations

**What it does:** Tracks schema changes as versioned Python scripts. On startup, `alembic upgrade head` applies any pending migrations.

**Why we need it:** Without migrations, schema changes require manual SQL. If you add a column and forget to tell a teammate, their app crashes. Alembic ensures the schema is always in sync with the code.

**How it works in this project:**
- Migration scripts live in `backend/alembic/versions/`
- On every backend startup, `main.py` runs `alembic upgrade head`
- Migration history is tracked in the `alembic_version` table

---

### Authentication & Security

#### `argon2-cffi` — Password Hashing

**What it does:** Hashes user passwords using the Argon2id algorithm.

**Why Argon2 over alternatives:**

| Algorithm | Why not |
|-----------|---------|
| bcrypt | Industry standard for years, but Argon2 won the Password Hashing Competition (2015). Argon2 is memory-hard, making GPU attacks much more expensive. |
| SHA-256 / MD5 | Not designed for passwords. Too fast — an attacker can try billions of hashes per second. |
| PBKDF2 | CPU-hard but not memory-hard. GPUs can parallelize it efficiently. |

**Why it matters:** If our database is ever breached, attackers get the password hashes. Argon2id's memory-hardness means cracking them requires expensive RAM, not just cheap GPUs. It's the current best practice.

#### `python-jose[cryptography]` — JWT Tokens

**What it does:** Creates and verifies JSON Web Tokens for stateless authentication.

**Why JWTs for a chat app:**
- **Stateless** — The backend doesn't need to store session data. The token itself contains the user ID and expiration.
- **WebSocket-friendly** — The token is passed as a query parameter during WebSocket connection. No cookie/session management needed.
- **Multi-worker safe** — Any Gunicorn worker can verify any token because they all share the same `SECRET_KEY`.

**The `[cryptography]` extra:** Uses the `cryptography` package for HMAC-SHA256 signing instead of pure Python. Faster and more secure.

#### `python-multipart` — Form Data Parsing

**What it does:** Parses `multipart/form-data` request bodies — required for file uploads.

**Why a separate library:** FastAPI delegates form parsing to this library. Without it, file upload endpoints would fail at runtime with a confusing import error.

---

### Real-Time Communication

#### `websockets` — WebSocket Protocol Library

**What it does:** Provides the underlying WebSocket protocol implementation that Uvicorn uses for FastAPI's WebSocket endpoints.

**Why we use native WebSockets (not Socket.IO):**

| Considered | Why not |
|-----------|---------|
| Socket.IO | Adds a custom protocol on top of WebSockets (event names, rooms, acknowledgements). Our use case is simple enough that native WebSockets + manual room management is cleaner and has fewer dependencies. |
| Server-Sent Events (SSE) | One-way only (server→client). Chat needs bidirectional communication. |
| Long polling | High latency, high server load. WebSockets are always better when you need real-time. |

#### `redis[hiredis]` — Redis Client

**What it does:** Connects to Redis for pub/sub, token blacklisting, and rate limit state storage.

**The `[hiredis]` extra:** Installs `hiredis`, a C-based Redis protocol parser. Makes response parsing ~10x faster than pure Python. Essential when handling high-throughput pub/sub.

**Two Redis client modes in our code:**
1. **Synchronous** (`redis.Redis`) — Used for token blacklist checks and pub/sub publishing.
2. **Async** (`redis.asyncio`) — Used for the pub/sub subscriber that runs as a background task.

---

### Messaging & Async Processing

#### `aiokafka` — Async Kafka Client

**What it does:** Produces and consumes Kafka messages using Python's `asyncio`, so Kafka operations don't block the event loop.

**Why `aiokafka` over `confluent-kafka`:**

| Considered | Why not |
|-----------|---------|
| `confluent-kafka` | The "official" Python client, but it's synchronous. Requires thread pools to avoid blocking FastAPI's event loop. More complex integration. |
| `kafka-python` | Pure Python, synchronous. Simpler but slower, and would block the event loop. |

`aiokafka` is purpose-built for asyncio applications. Producer `send_and_wait()` and consumer iteration are all native coroutines.

#### `cramjam` — Compression Codecs

**What it does:** Provides the LZ4 compression codec that `aiokafka` uses for message compression.

**Why LZ4:** LZ4 gives ~2-4x compression with negligible CPU overhead (~1ms per message). Kafka stores messages on disk, so compression saves both network bandwidth and storage. LZ4 is the standard compression choice for Kafka.

---

### Observability & Protection

#### `structlog` — Structured Logging

**What it does:** Produces log messages as structured key-value pairs instead of unformatted strings.

**Why structured logging over `print()` or stdlib `logging`:**

Standard log:
```
2024-01-15 10:30:00 INFO Message persisted for room 5
```

Structured log:
```json
{"event": "message_persisted", "room_id": 5, "msg_id": "abc-123", "timestamp": "2024-01-15T10:30:00Z", "level": "info"}
```

The structured version can be parsed by log aggregation tools (Datadog, ELK, Loki) for searching, filtering, and alerting. "Show me all errors in room 5" becomes a query, not a grep.

**Dual rendering:** In dev, structlog uses `ConsoleRenderer` (pretty, colored output). In staging/production, it uses `JSONRenderer` (machine-parseable).

#### `slowapi` — Rate Limiting

**What it does:** Limits the number of requests per IP per time window. Prevents abuse like brute-force login attempts or registration spam.

**Current limits:**
- Registration: 5/minute
- Login: 10/minute
- General: 100/minute

**Why `slowapi`:** It's a FastAPI-specific wrapper around `limits`, with native support for Redis as a shared backend. Minimal setup — a single decorator per endpoint.

**Environment-aware:** Rate limiting is disabled in dev (avoids interfering with rapid testing) and enabled in staging/prod using Redis for cross-worker state.

---

### Utilities & Testing

#### `python-dotenv` — Environment Variables

**What it does:** Loads variables from the `.env` file at project root into `os.environ` at startup.

**Why:** Keeps secrets (database passwords, JWT key) out of the code. Different `.env` files for different environments (dev/staging/prod) without changing any code.

#### `aiofiles` — Async File I/O

**What it does:** Provides async wrappers for file read/write operations.

**Why:** FastAPI's file upload handler needs to write uploaded files to disk. Using synchronous `open()` would block the event loop during large file writes. `aiofiles` makes file I/O non-blocking.

#### `httpx` — HTTP Client

**What it does:** Modern async HTTP client used in tests for calling the FastAPI app.

**Why `httpx` over `requests`:** `httpx` has an `AsyncClient` that integrates with FastAPI's `TestClient` for testing async endpoints. Also supports HTTP/2.

#### `pytest` + `pytest-asyncio` — Testing

**What it does:** `pytest` runs the test suite. `pytest-asyncio` adds support for testing `async def` test functions.

**Why:** pytest is the de facto Python test framework. `pytest-asyncio` is needed because our services use async Kafka and Redis operations that need to be awaited in tests.

---

## 4. Frontend: Why These Libraries

### Core Framework

#### `react` + `react-dom` — UI Framework

**What it does:** Component-based UI framework. Manages DOM updates, component lifecycle, and state.

**Why React:**
- Component model maps naturally to chat UI (MessageList, RoomList, UserList are independent components).
- Large ecosystem — any problem we hit has a solution.
- Context API handles our state management needs without extra libraries.

**Why not:**

| Considered | Why not |
|-----------|---------|
| Vue.js | Would work well. React was chosen for broader ecosystem and team familiarity. |
| Svelte | Smaller bundle, but smaller ecosystem. Less tooling support. |
| Vanilla JS | Too much manual DOM manipulation for a dynamic chat interface with multiple rooms, real-time updates, and context menus. |

#### `react-router-dom` — Client-Side Routing

**What it does:** Maps URLs to React components (`/` → LoginPage, `/chat` → ChatPage, `/admin` → AdminPage).

**Why:** Without routing, the entire app would be a single page with conditional rendering. Router gives us proper URLs, browser back/forward support, and route-based code organization.

---

### Build Tooling

#### `vite` — Build Tool & Dev Server

**What it does:** Development server with instant Hot Module Replacement (HMR), and a production bundler.

**Why Vite over alternatives:**

| Considered | Why not |
|-----------|---------|
| Create React App (CRA) | Deprecated. Uses Webpack under the hood, which is slow for dev server startup. |
| Webpack | Powerful but complex config. Vite does the same with near-zero config. |
| Parcel | Zero-config is nice, but Vite has better ecosystem support and plugin system. |

**Key Vite features we use:**
- **HMR** — Change a component, see it update in <100ms without losing state.
- **Environment variables** — `import.meta.env.VITE_API_BASE` injects variables at build time.
- **Optimized builds** — Production build uses Rollup for tree-shaking and code splitting.

#### `@vitejs/plugin-react` — React Integration for Vite

**What it does:** Adds React Fast Refresh (HMR for React components) and JSX transformation to Vite.

**Why it's separate:** Vite is framework-agnostic. This plugin teaches it how to handle React's JSX syntax and component hot-reloading.

---

### HTTP & Networking

#### `axios` — HTTP Client

**What it does:** Makes HTTP requests to the backend API with automatic JSON parsing and request/response interceptors.

**Why Axios over `fetch`:**

| Feature | Axios | Native `fetch` |
|---------|-------|----------------|
| Request interceptors | Built-in. We use it to auto-attach JWT to every request. | Manual. Would need a wrapper function. |
| Response interceptors | Built-in. Could auto-redirect on 401. | Manual. |
| Base URL | `axios.create({ baseURL })` | Must prepend URL manually every time. |
| JSON auto-parsing | Automatic. | Need `response.json()` every time. |
| Error handling | Rejects on 4xx/5xx. | Only rejects on network errors. 404 is a "success." |

**Our setup:** A single Axios instance (`http.js`) with the JWT interceptor means every API call in every service file automatically includes authentication. Zero boilerplate per request.

---

### Code Quality

#### `eslint` + Plugins — Linting

**What it does:** Static analysis to catch bugs and enforce consistent code style.

**Plugins we use:**
- **`eslint-plugin-react-hooks`** — Enforces the Rules of Hooks (no conditional hooks, correct dependency arrays in `useEffect`). These rules prevent some of the most common React bugs.
- **`eslint-plugin-react-refresh`** — Ensures components are compatible with Vite's Fast Refresh. Catches patterns that would break HMR.

#### `@types/react` + `@types/react-dom` — TypeScript Definitions

**What it does:** Provides TypeScript type definitions for React, used by editors (VS Code) for autocompletion and type checking even in JavaScript files.

**Why in a JS project?** VS Code reads these types to provide better IntelliSense. Even without TypeScript, you get autocomplete for React's API (`useState`, `useEffect`, props, etc.).

---

## 5. Data Flow: How It All Connects

### Sending a Chat Message (Happy Path)

```
Browser                  FastAPI              Redis           Kafka          PostgreSQL
  |                        |                   |               |               |
  |-- WebSocket msg ------>|                   |               |               |
  |                        |-- publish ------->|               |               |
  |                        |-- produce ------->|               |               |
  |                        |                   |               |               |
  |                        |   Redis delivers  |               |               |
  |<---- all users --------|<-- pub/sub -------|               |               |
  |                        |                   |               |               |
  |                        |                   |    Consumer   |               |
  |                        |                   |    picks up   |               |
  |                        |                   |       |------>|-- INSERT ---->|
  |                        |                   |               |   (async)     |
```

### When Kafka Is Down (Graceful Degradation)

```
Browser                  FastAPI              Redis           PostgreSQL
  |                        |                   |               |
  |-- WebSocket msg ------>|                   |               |
  |                        |-- publish ------->|               |
  |                        |-- INSERT (sync) --|-------------->|
  |                        |                   |               |
  |<---- all users --------|<-- pub/sub -------|               |
```

The user experience is identical. The only difference is the database write happens synchronously instead of asynchronously.

### When Redis Is Down (Single-Worker Fallback)

```
Browser                  FastAPI              PostgreSQL
  |                        |                   |
  |-- WebSocket msg ------>|                   |
  |                        |-- local broadcast |
  |<---- same-worker ------|                   |
  |                        |-- INSERT -------->|
```

Users connected to other Gunicorn workers won't receive the message until they refresh. This is acceptable as a degraded mode — Redis downtime should be rare and short.

---

## 6. What Alternatives Were Considered

### "Why not just use Socket.IO?"

Socket.IO adds a protocol layer (event names, rooms, auto-reconnect, fallback to long-polling). We implement rooms ourselves with a simple dictionary (`room_id → [websockets]`). Our approach is:
- More transparent — no magic protocol, just JSON over WebSocket
- Lighter — no Socket.IO client library (saves ~40KB gzipped)
- More flexible — custom reconnect logic, custom room management with admin succession

### "Why not store sessions in the database?"

JWT + Redis blacklist gives us:
- Stateless auth (any worker validates any token)
- Fast logout (Redis is sub-millisecond)
- WebSocket auth (pass token as query param, no cookie issues)

Database sessions would require a session lookup on every request and complicate WebSocket auth.

### "Why not use a monorepo tool like Turborepo?"

Two folders (`backend/` and `frontend/`) with separate dependency management is simpler. We don't share code between them, so there's no benefit to a monorepo tool. The overhead isn't justified.

### "Why not use TypeScript for the frontend?"

The frontend is intentionally lightweight — thin API wrappers, context providers, and presentational components. TypeScript would add value in a larger codebase, but for our scale, the JSDoc hints from `@types/react` give us good-enough editor support without the build complexity.
