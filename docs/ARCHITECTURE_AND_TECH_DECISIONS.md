# Architecture & Technology Decisions

Why we chose every piece of technology in cHATBOX — from infrastructure to individual libraries.

> **Reading guide:** cHATBOX has evolved from a monolith to a **microservices architecture**. If you're new to the project, start with **[Section 7: Microservice Architecture](#7-microservice-architecture)** for the current design. Sections 1-6 cover foundational decisions (infrastructure, libraries, data flow) that still apply — they were made during the monolith phase but remain relevant to the microservices architecture.

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
7. [Microservice Architecture](#7-microservice-architecture)
   - [Service Decomposition](#service-decomposition)
   - [Polyglot Stack](#polyglot-stack-why-different-languages)
   - [Kong API Gateway](#kong-api-gateway)
   - [Inter-Service Communication](#inter-service-communication)
   - [Design Patterns](#design-patterns-used)
   - [Data Architecture](#data-architecture-database-per-service)
   - [Trade-offs vs Monolith](#trade-offs-vs-monolith)

---

## 1. System Architecture

cHATBOX separates four concerns that often get tangled in chat apps:

| Concern | What handles it | Why separate? |
|---------|----------------|---------------|
| **Real-time delivery** | Chat service (Go) + Redis pub/sub | Must be fast (sub-100ms). No disk I/O. Go handles thousands of concurrent WebSockets efficiently. |
| **Durable storage** | Kafka → Message service (Python) → PostgreSQL | Can be async. Needs reliability, not speed. CQRS pattern — writes via Kafka, reads via REST. |
| **API routing + auth** | Kong API Gateway | Single entry point, JWT validation, rate limiting, request logging across all services. |
| **Static serving** | Nginx (frontend container) | Serves the React SPA build. SPA routing via `try_files`. |

This separation means a slow database query doesn't block message delivery, a WebSocket spike doesn't overwhelm the auth service, and each service scales independently based on its specific bottleneck.

---

## 2. Infrastructure: Why These Services

### PostgreSQL

**What it does here:** Each microservice has its own PostgreSQL database (database-per-service pattern): `chatbox_auth` (users, tokens), `chatbox_chat` (rooms, muted users), `chatbox_messages` (messages, private messages), and `chatbox_files` (file metadata via Prisma).

**Why PostgreSQL over alternatives:**

| Considered | Why not |
|-----------|---------|
| SQLite | No concurrent writes. Can't share between containers. No network access — each service runs in its own container. |
| MySQL | Would work, but PostgreSQL has better JSON support, better default behavior for concurrent access, and is the more common choice in the Python ecosystem. |
| MongoDB | Our data is highly relational (users belong to rooms, messages reference both sender and room). Document stores make these relationships awkward and denormalized. |

**Key PostgreSQL features we rely on:**

- **ACID transactions** — When a user sends a message, we need the insert to either fully succeed or fully fail. No partial writes.
- **Foreign keys** — The database enforces that a message can't reference a non-existent user or room. This catches bugs that would silently corrupt data in schema-less stores.
- **`ON CONFLICT DO NOTHING`** — Used for Kafka idempotent writes in the message-service. When the same `message_id` arrives twice (Kafka at-least-once delivery), PostgreSQL skips the duplicate instead of crashing.
- **Connection pooling** (per service, e.g., `pool_size=10, max_overflow=20`) — Each service maintains its own pool of reusable connections, isolated from other services.
- **`pool_pre_ping=True`** — Tests each connection before using it. Prevents "connection closed" errors after database restarts.

---

### Redis

**What it does here:** Three jobs, each leveraging a different Redis capability.

#### Job 1: WebSocket Message Relay (Pub/Sub)

**The problem:** When running multiple chat-service instances (or scaling horizontally), each instance has its own set of WebSocket connections. If User A's WebSocket is on Instance 1 and User B's is on Instance 2, Instance 1 can't directly send to User B.

**The solution:** Redis pub/sub acts as a message bus between chat-service instances.

```
User A sends message
    → Chat-service Instance 1 receives it
    → Instance 1 publishes to Redis channel "room:5"
    → ALL instances (including Instance 2) receive from Redis
    → Instance 2 delivers to User B's WebSocket
```

**Why Redis for pub/sub (not Kafka)?** Redis pub/sub is fire-and-forget with zero latency overhead. Messages are delivered instantly to subscribers and then gone. We don't need durability here — if a message is missed because an instance crashed, the user will see it when they reconnect (loaded from the message-service database). Kafka's pub/sub adds unnecessary overhead (disk writes, consumer group coordination) for something that should be instant and ephemeral.

**Channels we use:**
- `room:<room_id>` — Room chat messages
- `lobby` — Global updates (room created, room closed, user count changes)
- `user:<username>` — Targeted messages (PMs, kick notifications)

#### Job 2: Token Blacklist (Key-Value)

**The problem:** JWTs are stateless — once issued, they're valid until they expire. When a user logs out, we need to invalidate their token immediately.

**The solution:** On logout, the auth-service stores the token in Redis with a TTL matching the token's remaining lifetime:
```
SET blacklist:<token> "1" EX 86400
```
On every authenticated request, the auth-service (or any service validating tokens) checks if the token is blacklisted before accepting it.

**Why Redis (not the database)?** This check happens on every single API request across all services. Redis responds in ~0.1ms from memory. PostgreSQL would be ~1-5ms with disk I/O. At 100 requests/second, that's the difference between 10ms and 500ms of cumulative overhead.

#### Job 3: Rate Limiting State (Key-Value with TTL)

**The problem:** In production, we rate-limit API endpoints (5 registrations/minute, 10 logins/minute, 100 general requests/minute per IP). Rate limits need to be shared across all service instances.

**The solution:** Kong API Gateway handles rate limiting with Redis as the shared state store. This means all incoming requests, regardless of which service instance handles them, share the same rate limit counters.

**Why not in-memory?** In-memory rate limiting is per-instance. With multiple service replicas, a user could bypass limits by hitting different instances.

---

### Apache Kafka

**What it does here:** Decouples the real-time message path from the database write path.

**The problem it solves:**

Without Kafka, every chat message must be synchronously written to PostgreSQL before the user gets a response. If the database is slow (high load, vacuum running, complex query), message delivery slows down too.

**With Kafka:**
```
1. User sends message via WebSocket to chat-service (Go)
2. Chat-service publishes to Kafka topic chat.messages (async, ~1ms)
3. Chat-service broadcasts via Redis pub/sub (instant delivery to all users)
4. Message-service's Kafka consumer picks up the message (background)
5. Message-service persists to its PostgreSQL database (async, no user waiting)
```

The user sees the message instantly (step 3). The database write happens whenever it happens (step 5). Even if the message-service database is down for 5 minutes, messages are buffered in Kafka and will be persisted when it comes back.

**Why Kafka over alternatives:**

| Considered | Why not |
|-----------|---------|
| RabbitMQ | Good for task queues but messages are deleted after consumption. Kafka retains messages for 7 days — you can replay them if something goes wrong. |
| Redis Streams | Could work for small scale, but doesn't have native consumer groups with the same reliability guarantees. Kafka handles backpressure better. |
| Direct DB writes | Works but couples message delivery speed to database speed. Under load, users experience lag. |
| No persistence | Messages would be ephemeral only. Users who go offline lose everything. |

**Key Kafka features we rely on:**

- **Consumer groups** (`message-persistence`) — If we scale to multiple message-service instances, Kafka distributes partitions across them automatically.
- **At-least-once delivery** — Kafka guarantees every message will be consumed at least once. Combined with `ON CONFLICT DO NOTHING` in PostgreSQL, we get exactly-once semantics.
- **Dead Letter Queue** (`chat.dlq`) — Messages that fail 3 times go to a separate topic for investigation instead of being lost.
- **LZ4 compression** — Reduces network and disk usage with minimal CPU overhead.
- **KRaft mode** — Runs without ZooKeeper, simplifying our deployment to a single Kafka container.
- **Configurable retention** — 7 days for messages, 3 days for events, 30 days for DLQ. Old data is automatically cleaned up.

**Graceful degradation:** If Kafka is down, the chat-service falls back to synchronous delivery. Users don't notice — messages still get delivered in real-time via Redis. Persistence resumes when Kafka and the message-service reconnect.

---

### Nginx

**What it does here:** Serves the React SPA inside the frontend Docker container. In the microservices architecture, Kong API Gateway handles API routing, JWT validation, and rate limiting — Nginx's role is limited to frontend static file serving.

**Why we still need Nginx (for the frontend):**

1. **SPA routing** — React Router uses client-side routes (`/chat`, `/admin`). Without Nginx's `try_files $uri /index.html`, refreshing the page on `/chat` would return a 404 because no file exists at that path.

2. **Static file serving** — Nginx serves the React build files (JS, CSS, images) directly from disk, which it does much faster than any application server.

3. **Gzip compression** — Compresses static assets before sending them to the browser, reducing load times.

> **Note:** API routing (`/api/*`), WebSocket upgrade (`/ws/*`), rate limiting, and JWT validation are all handled by **Kong API Gateway**, not Nginx. See [Section 7: Kong API Gateway](#kong-api-gateway) for details.

**Why Nginx for the frontend (not alternatives):**

| Considered | Why not |
|-----------|---------|
| Caddy | Simpler config, auto-HTTPS. But Nginx has broader ecosystem support and we don't need HTTPS for internal container serving. |
| Serve from Node.js | Could use `serve` or Express, but Nginx handles thousands of concurrent static file requests with minimal resources. |
| No proxy (serve from Kong) | Kong can serve static files, but it's an API gateway — adding static file serving overloads its purpose. Better separation of concerns. |

---

### Docker & Docker Compose

**What it does here:** Packages every service (PostgreSQL, Redis, Kafka, Kong, auth-service, chat-service, message-service, file-service, frontend) into isolated containers with deterministic dependencies.

**Why Docker:**

1. **Reproducible environments** — `python:3.11-slim`, `golang:1.22-alpine`, and `node:20-alpine` give us exact, known base images per language. No "works on my machine" issues.
2. **Service isolation** — Each microservice runs in its own container with its own filesystem. A file-service crash can't affect the chat-service.
3. **Health checks and dependency ordering** — `depends_on: { postgres: { condition: service_healthy } }` ensures services don't start until infrastructure is ready. Init containers run migrations before application services start.
4. **Volume management** — `pgdata` persists database files across container restarts. `uploads` persists user-uploaded files.

**Two Compose files for two workflows:**

| File | When to use | What it runs |
|------|------------|--------------|
| `docker-compose.dev.yml` | Daily development | Only PostgreSQL, Redis, Kafka. Services run natively for hot-reload. |
| `docker-compose.yml` | Production / CI | Full microservices stack: Kong, 4 services, frontend, PostgreSQL, Redis, Kafka. |

**Why Docker Compose (not Kubernetes):**

Kubernetes makes sense when you need auto-scaling, rolling deployments across multiple nodes, and service mesh. For a single-server deployment, Docker Compose gives the same container benefits with 10% of the complexity.

---

## 3. Backend: Why These Libraries

> **Scope note:** This section covers the Python libraries used in **auth-service** and **message-service**. The chat-service (Go) and file-service (Node.js/TypeScript) use language-specific libraries documented in [Section 7: Polyglot Stack](#polyglot-stack-why-different-languages).

### Framework & Server

#### `fastapi` — Web Framework (auth-service, message-service)

**What it does:** Handles HTTP routing, request validation, dependency injection, and auto-generates OpenAPI docs.

**Why FastAPI over alternatives:**

| Considered | Why not |
|-----------|---------|
| Django | Full batteries-included framework. Too heavy for focused microservices. Django Channels adds async, but it's bolted on, not native. |
| Flask | Simple and mature, but synchronous by default. No built-in validation or dependency injection. |
| Express.js (Node) | Used for file-service where streaming I/O matters. FastAPI's Pydantic validation is better for data-heavy services like auth and messages. |

**FastAPI features we actively use:**
- **Pydantic validation** — Request/response schemas are validated automatically. A malformed JSON body returns a clear 422 error, not a 500 crash.
- **Dependency injection** — `Depends(get_db)` gives each request its own database session and auto-closes it. `Depends(get_current_user)` handles JWT validation on every protected endpoint.
- **Auto-generated docs** — `/docs` gives us Swagger UI for testing endpoints on each Python service.

#### `uvicorn[standard]` — ASGI Server (Development)

**What it does:** Runs the FastAPI application (auth-service, message-service) in development with `--reload` for auto-restart on code changes.

**Why the `[standard]` extra:** Installs `uvloop` (faster event loop) and `httptools` (faster HTTP parsing). Both are C-based replacements for Python's default implementations, giving ~2-3x better throughput.

#### `gunicorn` — Process Manager (Production)

**What it does:** Spawns multiple Uvicorn worker processes for each Python service, so they can use all CPU cores.

**Why we need it:** Uvicorn alone runs a single process. With Gunicorn as the process manager, each Python service gets:
- Multiple workers (formula: `min(cpu_count * 2 + 1, 8)`)
- Automatic worker restart if one crashes
- Graceful shutdown (waits for in-flight requests)

**Configuration:** `worker_class = "uvicorn.workers.UvicornWorker"` means each Gunicorn worker runs a full Uvicorn async event loop. It's not threading — it's genuine multiprocessing with async I/O inside each process.

> **Note:** The chat-service (Go) doesn't need Gunicorn — Go's goroutines handle concurrency natively. The file-service (Node.js) uses its own clustering mechanism.

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
- Each Python service has its own migrations: `services/auth-service/alembic/versions/` and `services/message-service/alembic/versions/`
- On every service startup, migrations are applied via `alembic upgrade head`
- Migration history is tracked in the `alembic_version` table within each service's database
- The file-service uses Prisma migrations instead of Alembic

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
- **Stateless** — No service needs to store session data. The token itself contains the user ID and expiration.
- **WebSocket-friendly** — The token is passed as a query parameter during WebSocket connection to the chat-service. No cookie/session management needed.
- **Multi-service safe** — Any service can verify any token because they all share the same `SECRET_KEY`. The auth-service issues tokens, but the chat-service, message-service, and file-service can all validate them independently.

**The `[cryptography]` extra:** Uses the `cryptography` package for HMAC-SHA256 signing instead of pure Python. Faster and more secure.

#### `python-multipart` — Form Data Parsing

**What it does:** Parses `multipart/form-data` request bodies — used by FastAPI for form-based login endpoints in the auth-service.

**Why a separate library:** FastAPI delegates form parsing to this library. Without it, form-based endpoints would fail at runtime with a confusing import error.

> **Note:** File uploads are now handled by the file-service (Node.js) using Multer, not by the Python services.

---

### Real-Time Communication

#### WebSocket — Chat Service (Go)

**What it does:** The chat-service uses Go's `gorilla/websocket` library for WebSocket connections. In the monolith, this was handled by Python's `websockets` library via FastAPI — but the microservices migration moved WebSocket handling to Go for dramatically better concurrency (goroutines handle 10,000+ connections with ~40MB total memory).

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

#### Rate Limiting — Kong API Gateway

**What it does:** Limits the number of requests per IP per time window. Prevents abuse like brute-force login attempts or registration spam.

**Current limits (configured in Kong):**
- Registration: 5/minute
- Login: 10/minute
- General: 100/minute

**Why Kong for rate limiting (not per-service):** In the monolith, `slowapi` handled rate limiting per FastAPI endpoint. In the microservices architecture, Kong centralizes rate limiting at the gateway layer — before requests even reach individual services. This is more efficient (one enforcement point) and consistent (limits apply regardless of which service handles the request).

> **Note:** The chat-service also implements its own WebSocket-level rate limiting (30 messages/10 seconds per user, sliding window) since WebSocket connections bypass Kong's HTTP rate limiting.

---

### Utilities & Testing

#### `python-dotenv` — Environment Variables

**What it does:** Loads variables from the `.env` file at project root into `os.environ` at startup.

**Why:** Keeps secrets (database passwords, JWT key) out of the code. Different `.env` files for different environments (dev/staging/prod) without changing any code.

#### `aiofiles` — Async File I/O (legacy monolith)

**What it does:** Provides async wrappers for file read/write operations.

**Why (in monolith):** FastAPI's file upload handler needed to write uploaded files to disk without blocking the event loop.

> **Note:** File uploads are now handled by the file-service (Node.js), which uses native streams for non-blocking I/O without needing a wrapper library.

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

### Sending a Chat Message (Microservices Architecture)

```
Browser       Kong        Chat Service     Redis        Kafka        Message Service   PostgreSQL
  |            |               |             |            |               |               |
  |--WS msg-->|---upgrade---->|              |            |               |               |
  |            |               |--publish--->|            |               |               |
  |            |               |--produce--->|            |               |               |
  |            |               |             |            |               |               |
  |            |               |  Redis pub  |            |               |               |
  |<--all users|<--broadcast--|<--sub--------|            |               |               |
  |            |               |             |            |               |               |
  |            |               |             |   Consumer |               |               |
  |            |               |             |   picks up |               |               |
  |            |               |             |      |---->|---INSERT----->|               |
  |            |               |             |            |   (async)     |               |
```

In the microservices architecture, the chat-service (Go) handles WebSocket connections and real-time delivery via Redis pub/sub. The message-service (Python) consumes from Kafka and persists to its own database asynchronously.

### When Kafka Is Down (Graceful Degradation)

```
Browser       Kong        Chat Service     Redis        PostgreSQL
  |            |               |             |               |
  |--WS msg-->|---upgrade---->|              |               |
  |            |               |--publish--->|               |
  |            |               |--sync write-|-------------->|
  |            |               |             |               |
  |<--all users|<--broadcast--|<--sub--------|               |
```

The user experience is identical. The chat-service falls back to synchronous delivery when Kafka is unavailable.

### When Redis Is Down (Local-Only Delivery)

```
Browser       Kong        Chat Service     PostgreSQL
  |            |               |               |
  |--WS msg-->|---upgrade---->|                |
  |            |               |--local bcast  |
  |<--same-ws-|<--broadcast---|                |
  |            |               |--INSERT------>|
```

Users connected to other instances won't receive the message until they reconnect. This is acceptable as a degraded mode — Redis downtime should be rare and short.

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

### "Why not use a monorepo tool like Turborepo or Nx?"

With 4 microservices (Python, Go, Node.js) plus a React frontend, a monorepo tool could help coordinate builds and testing. However, each service has its own CI pipeline that triggers independently on path changes, and there's minimal shared code between services (only Kafka event contracts). The overhead of learning and configuring a polyglot monorepo tool isn't justified when `docker compose` and per-service CI already handle orchestration.

### "Why not use TypeScript for the frontend?"

The frontend is intentionally lightweight — thin API wrappers, context providers, and presentational components. TypeScript would add value in a larger codebase, but for our scale, the JSDoc hints from `@types/react` give us good-enough editor support without the build complexity.

---

## 7. Microservice Architecture

### Why Microservices?

The monolith served us well for the first phase — fast iteration, simple deployment, one codebase. But as the system grew, we hit natural boundaries where different parts of the application had different scaling needs, different change frequencies, and different optimal technology choices:

| Concern | Monolith Reality | Microservice Benefit |
|---------|-----------------|---------------------|
| **WebSocket scaling** | All workers must handle both HTTP and WS — can't scale them independently | Chat service scales separately from REST APIs |
| **File I/O** | Large file uploads block the Python event loop, affecting chat latency | File service runs in Node.js with native streaming I/O |
| **Auth changes** | Changing password hashing or token format requires redeploying everything | Auth service deploys independently |
| **Message queries** | Heavy history queries compete with real-time message writes for DB connections | Message service has its own database and connection pool |
| **Team scaling** | Everyone works in the same codebase, merge conflicts on shared code | Each service is an independent repo/directory with clear ownership |

### Service Decomposition

We split the monolith into four services based on **bounded contexts** — each service owns a specific business capability:

| Service | Language | Port | Responsibility | Why This Boundary? |
|---------|----------|------|---------------|-------------------|
| **auth-service** | Python (FastAPI) | 8001 | Registration, login, logout, JWT issuance, token blacklist | Auth is cross-cutting — every other service depends on it but it changes independently. Argon2 hashing is CPU-intensive and benefits from isolated scaling. |
| **chat-service** | Go | 8003 | WebSocket connections, real-time message delivery, Redis pub/sub, room management | Real-time chat needs thousands of concurrent connections. Go's goroutines handle this with minimal memory (4KB per goroutine vs ~8MB per Python thread). |
| **message-service** | Python (FastAPI) | 8004 | Message persistence, history queries, replay API, Kafka consumer | Read-heavy workload (users loading history) that benefits from its own database with read replicas. Kafka consumer runs independently of the HTTP API. |
| **file-service** | Node.js (TypeScript) | 8005 | File upload, download, metadata, virus scanning hooks | I/O-bound workload. Node.js streams files without buffering entire content in memory. TypeScript gives type safety for a service that handles binary data and metadata. |

### Polyglot Stack: Why Different Languages?

This is a deliberate architectural choice, not accidental complexity. Each language was chosen because it's the **best tool for that specific workload**:

**Python (FastAPI) for auth-service and message-service:**
- FastAPI's dependency injection handles JWT validation and database sessions cleanly
- SQLAlchemy + Alembic provide mature database tooling
- Argon2 password hashing has excellent Python bindings
- Pydantic validation catches malformed requests before they hit business logic
- The team already has deep Python expertise from the monolith

**Go for chat-service:**
- Goroutines handle 10,000+ concurrent WebSocket connections with ~40MB total memory (vs ~80GB if Python spawned a thread per connection)
- Go's standard library includes production-ready HTTP and WebSocket servers
- Static binary compilation means the Docker image is ~15MB (vs ~200MB for Python)
- Garbage collection pauses are sub-millisecond — critical for real-time chat
- Built-in race detector catches concurrency bugs during testing

**Node.js/TypeScript for file-service:**
- Node.js streams handle file uploads/downloads without loading entire files into memory
- Express middleware ecosystem provides battle-tested multipart parsing (Multer)
- TypeScript catches type errors at compile time for a service that juggles file metadata, S3 paths, and Kafka events
- npm ecosystem has mature libraries for virus scanning hooks and image processing
- Non-blocking I/O naturally fits a service that's primarily waiting on disk/network

### Kong API Gateway

Kong sits in front of all services and handles cross-cutting concerns:

```
Client → Kong (port 80) → auth-service   /api/auth/*
                        → chat-service   /ws/chat/*
                        → message-service /api/messages/*
                        → file-service   /api/files/*
```

**What Kong handles:**
- **Routing**: Maps URL paths to upstream services
- **JWT validation**: Validates tokens on protected routes (offloads auth from individual services)
- **Rate limiting**: Per-consumer and per-IP rate limits
- **Request logging**: Centralized access logs across all services
- **Load balancing**: Round-robin distribution to service replicas
- **Health checks**: Automatic removal of unhealthy service instances

**Why Kong over alternatives:**

| Considered | Why Not |
|-----------|---------|
| Nginx reverse proxy | Would work for routing, but no built-in JWT validation, rate limiting, or service discovery. We'd have to bolt on Lua plugins for each feature. |
| Traefik | Good auto-discovery with Docker labels, but less mature plugin ecosystem for JWT validation and rate limiting. |
| AWS API Gateway | Vendor lock-in, pricing per request, higher latency for local development. |
| Custom gateway | Why build what already exists? Kong is battle-tested at companies handling billions of requests. |

### Inter-Service Communication

Services communicate through two channels:

**Synchronous (REST via Kong):**
- Client-facing requests routed through Kong to individual services
- Service-to-service calls for validation (e.g., chat-service validates JWT by calling auth-service)
- Used when the caller needs an immediate response

**Asynchronous (Kafka):**
- Message persistence: chat-service produces messages to Kafka, message-service consumes and persists
- File events: file-service publishes upload/delete events, other services react
- User events: auth-service publishes registration/deletion events
- Used when the caller doesn't need to wait for the result

```
chat-service  --produce-->  Kafka [chat.messages]  --consume-->  message-service
chat-service  --produce-->  Kafka [chat.private]   --consume-->  message-service
chat-service  --produce-->  Kafka [chat.events]    --consume-->  (future consumers)
file-service  --produce-->  Kafka [file.events]    --consume-->  chat-service
auth-service  --produce-->  Kafka [auth.events]    --consume-->  (future consumers)
```

### Design Patterns Used

The microservices architecture employs these patterns:

| # | Pattern | Where It's Used | Why |
|---|---------|----------------|-----|
| 1 | **Database per Service** | Each service has its own PostgreSQL schema | Loose coupling — services can change their schema without coordinating |
| 2 | **API Gateway** | Kong in front of all services | Single entry point, cross-cutting concerns (auth, rate limiting, logging) |
| 3 | **Event-Driven Architecture** | Kafka for async communication | Temporal decoupling — services don't need to be online simultaneously |
| 4 | **CQRS (Command Query Responsibility Segregation)** | chat-service writes, message-service reads | Optimized read and write paths with different data models |
| 5 | **Saga Pattern** | User deletion across services | Coordinated multi-service operations via Kafka events |
| 6 | **Circuit Breaker** | Service-to-service REST calls | Prevents cascade failures when a downstream service is down |
| 7 | **Strangler Fig** | Migration from monolith to microservices | Incremental extraction — monolith still runs alongside services |
| 8 | **Sidecar/Ambassador** | Kong routes and authenticates | Offloads cross-cutting concerns from business services |
| 9 | **Correlation ID** | X-Correlation-ID header propagated across services | Trace a single user request across all four services in logs |
| 10 | **Dead Letter Queue** | Kafka chat.dlq topic | Failed messages are preserved for investigation, not lost |
| 11 | **Health Check API** | /health and /ready per service | Kubernetes-style probes for orchestration and load balancing |
| 12 | **Consumer Group** | Kafka consumer groups per service | Multiple instances of a service share the workload |
| 13 | **Idempotent Consumer** | ON CONFLICT DO NOTHING in message persistence | Kafka at-least-once delivery + DB uniqueness = exactly-once semantics |
| 14 | **Bulkhead** | Separate connection pools per service | A connection leak in one service doesn't exhaust connections for others |
| 15 | **Externalized Configuration** | Environment variables per service | Same container image runs in dev/staging/prod with different config |

### Data Architecture (Database per Service)

Each service owns its data and exposes it only through APIs:

| Service | Database | Tables Owned | Why Separate? |
|---------|----------|-------------|---------------|
| auth-service | `chatbox_auth` | `users` | User credentials are security-critical — isolated access reduces blast radius |
| chat-service | `chatbox_chat` | `rooms`, `muted_users`, `room_state` | Room management and WebSocket state need fast access without competing with message writes |
| message-service | `chatbox_messages` | `messages`, `private_messages` | Read-heavy queries (history, replay) benefit from their own connection pool and indexes |
| file-service | `chatbox_files` | `files` (Prisma-managed) | File metadata queries don't compete with message queries |

All four databases are created automatically by `infra/docker/init/init-db.sh` inside a single PostgreSQL instance. In production, they could be split across separate PostgreSQL hosts for further isolation.

**Trade-off**: Data joins across services require API calls instead of SQL JOINs. For example, to show a message with the sender's username, the frontend calls both message-service (for the message) and auth-service (for the user info). This is slower than a monolith JOIN but keeps services decoupled.

### Trade-offs vs Monolith

Every architectural decision is a trade-off. Here's what we gained and what we gave up:

| Dimension | Monolith | Microservices |
|-----------|----------|---------------|
| **Deployment** | Single `docker compose up` | Per-service CI/CD pipelines, orchestrated deployment |
| **Debugging** | One log stream, simple stack traces | Distributed tracing with correlation IDs across 4 services |
| **Data consistency** | SQL transactions across all tables | Eventual consistency via Kafka (messages may take milliseconds to persist) |
| **Development speed** | Fast to start, slows as it grows | More setup upfront, faster iteration per service at scale |
| **Testing** | One test suite | Per-service unit tests + integration tests + contract tests |
| **Operational complexity** | Low — one process to monitor | Higher — 4 services + Kong + Kafka + multiple databases |
| **Scaling** | Scale everything together | Scale each service independently based on its bottleneck |
| **Technology flexibility** | One language (Python) | Best language per workload (Python, Go, Node.js) |
| **Team independence** | Everyone touches the same code | Teams own services end-to-end |

**When to choose the monolith**: Small team, early product, uncertain requirements, shipping speed matters more than scaling.

**When to choose microservices**: Clear bounded contexts, different scaling needs per component, multiple teams, polyglot advantages outweigh operational complexity.
