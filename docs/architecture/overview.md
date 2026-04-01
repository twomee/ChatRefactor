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

> **Feature design decisions** (how each feature works and why) have moved to [features.md](features.md).

---

## 1. System Architecture

cHATBOX separates four concerns that often get tangled in chat apps:

| Concern | What handles it | Why separate? |
|---------|----------------|---------------|
| **Real-time delivery** | Chat service (Go) + in-memory broadcast (Redis pub/sub planned for horizontal scaling) | Must be fast (sub-100ms). No disk I/O. Go handles thousands of concurrent WebSockets efficiently. |
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
- **Uniqueness constraints** — Used for Kafka idempotent writes in the message-service. The `message_id` column has a `unique=True` constraint, so when the same message arrives twice (Kafka at-least-once delivery), the application checks for duplicates and skips the insert.
- **Connection pooling** (per service) — Each service maintains its own pool of reusable connections, isolated from other services (e.g., auth-service: `pool_size=10, max_overflow=20`).
- **`pool_pre_ping=True`** — Tests each connection before using it. Prevents "connection closed" errors after database restarts.

---

### Redis

**What it does here:** Three jobs, each leveraging a different Redis capability.

#### Job 1 (Planned): WebSocket Message Relay (Pub/Sub)

> **Current state:** The chat-service currently uses an **in-memory connection manager** (`sync.RWMutex`) for broadcasting messages to WebSocket connections. Redis pub/sub is the planned solution for when the service scales to multiple instances. See `services/chat-service/internal/ws/manager.go` for the current implementation.

**The problem (when scaling horizontally):** When running multiple chat-service instances, each instance has its own set of WebSocket connections. If User A's WebSocket is on Instance 1 and User B's is on Instance 2, Instance 1 can't directly send to User B.

**The planned solution:** Redis pub/sub will act as a message bus between chat-service instances.

```
User A sends message
    → Chat-service Instance 1 receives it
    → Instance 1 publishes to Redis channel "room:5"
    → ALL instances (including Instance 2) receive from Redis
    → Instance 2 delivers to User B's WebSocket
```

**Why Redis for pub/sub (not Kafka)?** Redis pub/sub is fire-and-forget with zero latency overhead. Messages are delivered instantly to subscribers and then gone. We don't need durability here — if a message is missed because an instance crashed, the user will see it when they reconnect (loaded from the message-service database). Kafka's pub/sub adds unnecessary overhead (disk writes, consumer group coordination) for something that should be instant and ephemeral.

**Channels (planned):**
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
2. Chat-service broadcasts via in-memory manager (instant delivery to all users in the room)
3. Chat-service publishes to Kafka topic chat.messages (async, ~1ms)
4. Message-service's Kafka consumer picks up the message (background)
5. Message-service persists to its PostgreSQL database (async, no user waiting)
```

The user sees the message instantly (step 2). The database write happens whenever it happens (step 5). Even if the message-service database is down for 5 minutes, messages are buffered in Kafka and will be persisted when it comes back.

**Why Kafka over alternatives:**

| Considered | Why not |
|-----------|---------|
| RabbitMQ | Good for task queues but messages are deleted after consumption. Kafka retains messages for 7 days — you can replay them if something goes wrong. |
| Redis Streams | Could work for small scale, but doesn't have native consumer groups with the same reliability guarantees. Kafka handles backpressure better. |
| Direct DB writes | Works but couples message delivery speed to database speed. Under load, users experience lag. |
| No persistence | Messages would be ephemeral only. Users who go offline lose everything. |

**Key Kafka features we rely on:**

- **Consumer groups** (`chat-persistence`) — If we scale to multiple message-service instances, Kafka distributes partitions across them automatically.
- **At-least-once delivery** — Kafka guarantees every message will be consumed at least once. Combined with the `message_id` uniqueness constraint + application-level duplicate check in message-service, we get exactly-once semantics.
- **Dead Letter Queue** (`chat.dlq`) — Messages that fail 3 times go to a separate topic for investigation instead of being lost.
- **LZ4 compression** — Reduces network and disk usage with minimal CPU overhead.
- **KRaft mode** — Runs without ZooKeeper, simplifying our deployment to a single Kafka container.
- **Configurable retention** — 7 days for messages, 3 days for events, 7 days for DLQ (cluster-wide `KAFKA_LOG_RETENTION_HOURS: 168`). Old data is automatically cleaned up.

**Graceful degradation:** If Kafka is down, the chat-service uses the `SyncDelivery` fallback (Strategy pattern). Users don't notice — messages still get delivered in real-time via the in-memory WebSocket broadcast. However, messages sent during the outage won't be persisted to history. Persistence resumes when Kafka and the message-service reconnect.

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

> **What is message persistence?** When a user sends a chat message, it appears instantly in all connected browsers via WebSocket broadcast. But this is ephemeral — if the browser refreshes or a new user joins, those messages are gone. "Message persistence" means saving those ephemeral messages to a durable database (PostgreSQL) so they can be loaded later as conversation history. The message-service handles this by consuming messages from Kafka and writing them to its database. This is why the message-service exists separately from the chat-service — it converts ephemeral real-time events into durable history.

### 5.1 Sending a Room Message

```
Browser       Kong        Chat Service     Kafka        Message Service   PostgreSQL
  |            |               |             |               |               |
  |--WS msg-->|---forward---->|              |               |               |
  |            |               |--broadcast->|               |               |
  |            |               | (in-memory) |               |               |
  |<--all users|<-------------|              |               |               |
  |            |               |--produce--->|               |               |
  |            |               |             |--consume----->|               |
  |            |               |             |               |---INSERT----->|
  |            |               |             |               |   (async)     |
```

The chat-service (Go) handles WebSocket connections and real-time delivery via an **in-memory connection manager** (not Redis pub/sub — see [Redis Job 1](#job-1-planned-websocket-message-relay-pubsub) for the planned horizontal scaling solution). The message-service (Python) consumes from Kafka and persists to its own PostgreSQL database asynchronously.

### 5.2 Sending a Private Message

```
Browser       Kong        Chat Service     Kafka        Message Service   PostgreSQL
  |            |               |             |               |               |
  |--WS PM--->|---forward---->|              |               |               |
  |            |               |--deliver--->|               |               |
  |            |               | (to user's  |               |               |
  |            |               |  connections)|              |               |
  |<-recipient-|<-------------|              |               |               |
  |            |               |--produce--->|               |               |
  |            |               |  chat.private|              |               |
  |            |               |             |--consume----->|               |
  |            |               |             |  (resolves    |               |
  |            |               |             |  username →   |               |
  |            |               |             |  user_id via  |               |
  |            |               |             |  auth-service)|               |
  |            |               |             |               |---INSERT----->|
```

Private messages are delivered only to the recipient's WebSocket connections (all their open tabs). The message-service resolves usernames to user IDs by calling the auth-service internally before persisting.

### 5.3 User Registration (auth-service)

```
Browser       Kong        Auth Service     Kafka          PostgreSQL
  |            |               |              |               |
  |--POST---->|---/auth/------>|              |               |
  | register  | register      |              |               |
  |            |               |--hash pwd--->|               |
  |            |               | (Argon2id)   |               |
  |            |               |--INSERT user-|-------------->|
  |            |               |              |               |
  |            |               |--produce---->|               |
  |            |               | user_registered              |
  |            |               |   (auth.events)              |
  |<--201 OK--|<--------------|              |               |
```

### 5.4 User Login (auth-service)

```
Browser       Kong        Auth Service     Kafka          PostgreSQL
  |            |               |              |               |
  |--POST---->|---/auth/------>|              |               |
  | login     | login         |              |               |
  |            |               |--SELECT user-|-------------->|
  |            |               |--verify pwd--|               |
  |            |               | (Argon2id)   |               |
  |            |               |--sign JWT--->|               |
  |            |               | (user_id +   |               |
  |            |               |  username)   |               |
  |            |               |--produce---->|               |
  |            |               | user_logged_in               |
  |<--JWT-----|<--------------|              |               |
```

### 5.5 User Logout (auth-service)

```
Browser       Kong        Auth Service     Redis
  |            |               |             |
  |--POST---->|---/auth/------>|              |
  | logout    | logout        |              |
  |            |               |--SET-------->|
  |            |               | blacklist:   |
  |            |               | <token> "1"  |
  |            |               | EX 86400     |
  |<--200 OK--|<--------------|              |
```

The token is added to the Redis blacklist with a TTL matching the token's remaining lifetime. After the TTL expires, both the Redis entry and the JWT itself are expired — no cleanup needed.

### 5.6 File Upload (file-service)

```
Browser       Kong        File Service     PostgreSQL   Kafka        Chat Service
  |            |               |               |          |               |
  |--POST---->|---/files/----->|               |          |               |
  | multipart | upload        |               |          |               |
  |            |               |--validate--->|          |               |
  |            |               | (type, MIME, |          |               |
  |            |               |  size)       |          |               |
  |            |               |--save to disk|          |               |
  |            |               | ./uploads/   |          |               |
  |            |               |--INSERT----->|          |               |
  |            |               | metadata     |          |               |
  |            |               |--produce---->|          |               |
  |            |               | file_uploaded |          |               |
  |            |               |              | file.events|              |
  |            |               |              |          |--consume----->|
  |            |               |              |          | broadcast     |
  |            |               |              |          | to lobby+room |
  |<--file ID-|<--------------|              |          |               |
```

File binary data is saved to the local filesystem (`./uploads/` with UUID-prefixed filenames). File metadata (name, size, sender, room) is saved to PostgreSQL via Prisma. The Kafka event notifies the chat-service to broadcast a "file shared" notification to the lobby and room. In production, file storage would move to object storage (S3, MinIO).

### 5.7 File Download (file-service)

```
Browser       Kong        File Service     PostgreSQL   Disk
  |            |               |               |          |
  |--GET----->|---/files/----->|               |          |
  | download  | download/:id  |               |          |
  |            |               |--SELECT------>|          |
  |            |               | metadata      |          |
  |            |               |--stream file--|--------->|
  |            |               | (no buffering)|         |
  |<--file----|<--------------|               |          |
```

Files are streamed directly from disk to the client without loading the entire file into memory — Node.js streams handle this naturally.

### 5.8 Loading Room History (message-service)

```
Browser       Kong        Message Service   PostgreSQL
  |            |               |               |
  |--GET----->|---/messages--->|               |
  | /rooms/5  | /rooms/5/     |               |
  | /history  | history?      |               |
  |            | limit=50     |               |
  |            |               |--SELECT------>|
  |            |               | last 50 msgs  |
  |            |               | ORDER BY      |
  |            |               | sent_at DESC  |
  |<--JSON----|<---messages---|               |
```

The frontend calls this endpoint when a user joins a room to load conversation history. A separate replay endpoint (`GET /messages/rooms/{room_id}?since=<timestamp>`) is used when a user reconnects after a disconnect to catch up on missed messages.

### 5.9 Internal Architecture Map

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        INTERNAL ARCHITECTURE MAP                            │
│                    (Everything runs inside Docker network)                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────┐     ┌───────────────────────────────────────────────────────┐  │
│  │ Browser │────>│  Kong API Gateway (port 80)                          │  │
│  └─────────┘     │  - JWT validation on protected routes                │  │
│       ▲          │  - Rate limiting (uses Redis for shared counters)     │  │
│       │          │  - Request logging, CORS, security headers           │  │
│       │          └──┬─────────┬──────────┬──────────┬────────────────────┘  │
│       │             │         │          │          │                        │
│       │         /auth/*    /ws/*    /messages/*  /files/*                    │
│       │             │         │          │          │                        │
│       │             ▼         ▼          ▼          ▼                        │
│       │     ┌────────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐           │
│       │     │ auth-svc   │ │ chat-svc │ │ msg-svc │ │ file-svc │           │
│       │     │ Python     │ │ Go       │ │ Python  │ │ Node.js  │           │
│       │     │ :8001      │ │ :8003    │ │ :8004   │ │ :8005    │           │
│       │     └──┬───┬─────┘ └┬──┬──┬──┘ └┬──┬──┬──┘ └┬──┬──┬──┘           │
│       │        │   │        │  │  │      │  │  │      │  │  │              │
│       │        │   │        │  │  │      │  │  │      │  │  │              │
│  ┌────┴────────┼───┼────────┼──┼──┼──────┼──┼──┼──────┼──┼──┼───────┐      │
│  │   SERVICE-TO-SERVICE REST (direct Docker network, NOT via Kong)   │      │
│  │                                                                   │      │
│  │  chat-svc ──GET /auth/users/{id}──────────> auth-svc             │      │
│  │  msg-svc ──GET /auth/users/by-username/{name}──> auth-svc        │      │
│  │            ⚡ circuit breaker (5 fails → 30s cooldown)            │      │
│  │  file-svc ──local JWT verify (shared SECRET_KEY)──> NO call      │      │
│  │                                                                   │      │
│  │  Note: /auth/users/* has NO Kong route — unreachable externally  │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │   REDIS (port 6379)                                               │      │
│  │                                                                   │      │
│  │  auth-svc ──SET blacklist:<token> "1" EX 86400──> Token blacklist│      │
│  │  auth-svc ──GET blacklist:<token>──> Check on every auth request │      │
│  │  Kong ──rate limiting counters──> Shared across all instances     │      │
│  │  chat-svc ──(planned) pub/sub channels──> NOT YET IMPLEMENTED    │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │   KAFKA (port 9092, KRaft mode — no ZooKeeper)                    │      │
│  │                                                                   │      │
│  │  Producers:                        Consumers:              Then:  │      │
│  │  chat-svc ──chat.messages────────> msg-svc ──INSERT──> PostgreSQL│      │
│  │  chat-svc ──chat.private─────────> msg-svc ──INSERT──> PostgreSQL│      │
│  │             (group: chat-persistence)   (idempotent: unique check+skip)│      │
│  │  chat-svc ──chat.events──────────> (future consumers)            │      │
│  │  file-svc ──file.events──────────> chat-svc ──broadcast──> lobby │      │
│  │  auth-svc ──auth.events──────────> (future consumers)            │      │
│  │  msg-svc ──chat.dlq──────────────> (investigation, 7-day TTL)    │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │   POSTGRESQL (port 5432, single instance, 4 databases)            │      │
│  │                                                                   │      │
│  │  auth-svc ──> chatbox_auth     (users table)                     │      │
│  │  chat-svc ──> chatbox_chat     (rooms, muted_users, room_state)  │      │
│  │  msg-svc  ──> chatbox_messages (messages, private_messages)      │      │
│  │  file-svc ──> chatbox_files    (files — Prisma managed)          │      │
│  │                                                                   │      │
│  │  auth-svc: pool_size=10, max_overflow=20 (bulkhead pattern)     │      │
│  │  msg-svc: SQLAlchemy defaults. file-svc: Prisma-managed pool   │      │
│  │  No cross-database JOINs — data shared only via APIs             │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │   FILESYSTEM                                                      │      │
│  │                                                                   │      │
│  │  file-svc ──> ./uploads/ (UUID-prefixed filenames)               │      │
│  │  (In production: replace with S3/MinIO object storage)           │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │   NGINX (port 3000, inside frontend container)                    │      │
│  │                                                                   │      │
│  │  Serves React SPA build (JS, CSS, images)                        │      │
│  │  SPA routing: try_files $uri /index.html                         │      │
│  │  Gzip compression, security headers                              │      │
│  │  NOT used for API routing (that's Kong's job)                    │      │
│  └───────────────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.10 Graceful Degradation

**Graceful Degradation** means the system continues to work in a reduced capacity when a component fails, rather than crashing entirely.

| Component Down | What Breaks | What Still Works |
|---------------|-------------|-----------------|
| **Kafka** | Messages NOT saved to history. Users who join later won't see messages sent during outage. | Real-time WebSocket broadcast still works. Users currently in the room see messages normally. |
| **Redis** | Token revocation fails (production: logout returns 503). Rate limits fall back to per-instance local counters. | All other functionality works. JWT validation is stateless (doesn't need Redis). |
| **PostgreSQL** | New data can't be persisted. Room creation fails. | Messages already in Kafka are buffered until DB recovers. |
| **Auth-service** | New logins fail. Username lookups fail (message-service circuit breaker opens). | Existing JWT tokens remain valid. WebSocket connections stay open. |
| **Message-service** | History API unavailable. Messages buffer in Kafka (7-day retention). | Real-time chat works. Kafka retains messages until service recovers. |

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
| **chat-service** | Go | 8003 | WebSocket connections, real-time message delivery, in-memory broadcast (Redis pub/sub planned for horizontal scaling), room management | Real-time chat needs thousands of concurrent connections. Go's goroutines handle this with minimal memory (4KB per goroutine vs ~8MB per Python thread). |
| **message-service** | Python (FastAPI) | 8004 | Message persistence, history queries, replay API, Kafka consumer | Read-heavy workload (users loading history) that benefits from its own database with read replicas. Kafka consumer runs independently of the HTTP API. |
| **file-service** | Node.js (TypeScript) | 8005 | File upload, download, metadata, virus scanning hooks | I/O-bound workload. Node.js streams files without buffering entire content in memory. TypeScript gives type safety for a service that handles binary data and metadata. |

### Service Responsibilities (Detailed)

#### auth-service (Python/FastAPI, port 8001)

- **Registration:** Validates input (username uniqueness, password strength), hashes password with Argon2id, creates user record in `chatbox_auth` database, produces `user_registered` event to Kafka (`auth.events` topic)
- **Login:** Verifies credentials against Argon2 hash, issues JWT token containing `user_id`, `username`, and expiration timestamp. Produces `user_logged_in` event to Kafka
- **Logout:** Adds token to Redis blacklist with TTL matching the token's remaining lifetime (`SET blacklist:<token> "1" EX 86400`). Produces `user_logged_out` event to Kafka
- **Token blacklist check:** On every authenticated request, checks Redis if the token was revoked. In production, if Redis is down → rejects the request with 503 (fail-closed for security). In development → allows the request (fail-open for convenience)
- **Internal user lookup:** Provides `GET /auth/users/{user_id}` and `GET /auth/users/by-username/{username}` endpoints. These are NOT exposed through Kong — only other services can call them directly over the Docker network. Used by:
  - **message-service** — to resolve usernames to user IDs when persisting private messages from Kafka
  - **chat-service** — to validate that a user exists before room operations

#### chat-service (Go, port 8003)

- **WebSocket management:** Accepts WebSocket connections via Kong (`/ws` route with upgrade), maintains all active connections in an in-memory manager (`sync.RWMutex`), handles one goroutine per connection for reading and one for writing
- **Room operations:** Create room, close room, join room, leave room. All room state stored in its own PostgreSQL database (`chatbox_chat`). Includes admin succession logic when room creator leaves
- **Real-time broadcast:** When a message arrives via WebSocket, broadcasts to all connections in the same room via the in-memory manager (not via Redis pub/sub — see [Redis Job 1](#job-1-planned-websocket-message-relay-pubsub) for the planned horizontal scaling solution)
- **Admin operations:** Kick user from room, mute/unmute user, promote user to admin
- **Rate limiting:** Sliding window rate limiter — 30 messages per 10 seconds per user per room, enforced in-memory
- **Kafka production:** Produces messages, private messages, and events to Kafka topics (`chat.messages`, `chat.private`, `chat.events`). Fire-and-forget — if Kafka is down, real-time delivery still works but messages won't be persisted to history
- **Kafka consumption:** Consumes `file.events` from file-service (consumer group: `chat-file-events`) and broadcasts file-shared notifications to lobby and rooms
- **Graceful degradation:** Uses the Strategy pattern for delivery — `KafkaDelivery` in normal mode, `SyncDelivery` (no-op fallback) when Kafka is unavailable. WebSocket broadcast always works regardless of Kafka state. See `services/chat-service/internal/delivery/` for the implementation

#### message-service (Python/FastAPI, port 8004)

- **Message persistence (Kafka consumer):** Runs a background Kafka consumer (consumer group: `chat-persistence`) that reads from `chat.messages` and `chat.private` topics. Persists each message to PostgreSQL (`chatbox_messages` database) with idempotent writes — the `message_id` column has a `unique=True` constraint, and the consumer checks for an existing record before inserting (skips duplicates instead of crashing). This is why messages appear in history — without this service, messages would be ephemeral (visible only in real-time, lost on page refresh)
- **Room history API:** `GET /messages/rooms/{room_id}/history?limit=50` — returns the last 50 messages for a room, ordered oldest-first. Called by the frontend when a user joins a room to load conversation history
- **Message replay API:** `GET /messages/rooms/{room_id}?since=<ISO_timestamp>&limit=100` — returns messages sent after a specific timestamp. Used when a user reconnects after a disconnect to catch up on missed messages
- **Private message history:** Similar to room history but filtered by sender/recipient pair
- **Dead letter queue:** Messages that fail persistence after 3 retries are routed to `chat.dlq` topic (7-day retention, same as cluster default) for investigation instead of being lost
- **Circuit breaker:** Service-to-service calls to auth-service (for username → user_id resolution in private messages) are protected by a circuit breaker. After 5 consecutive failures → circuit opens for 30 seconds → prevents cascading failure if auth-service is down. See `services/message-service/app/infrastructure/auth_client.py`

#### file-service (Node.js/TypeScript, port 8005)

- **File upload:** Accepts multipart file uploads via Multer middleware. Validates file type (50+ allowed extensions), MIME type (magic byte verification to prevent spoofing), and size (max 150MB). Stores file on local filesystem (`./uploads/`) with UUID prefix to prevent name collisions (`${UUID}_${sanitized_filename}`)
- **File metadata storage:** Saves metadata (original name, stored path, file size, sender ID, room ID, upload timestamp) to PostgreSQL (`chatbox_files` database) via Prisma ORM
- **File download:** Streams file from disk to client without buffering entire file in memory (Node.js streams). Sets safe `Content-Disposition` headers (RFC 5987 encoding) to prevent XSS
- **Kafka production:** Produces `file_uploaded` events to `file.events` topic after successful upload. Contains file_id, filename, size, uploader username, and room_id. Chat-service consumes these events to broadcast "file shared" notifications to the lobby and room. Kafka failure does NOT fail the upload — the file is saved, just the real-time notification doesn't reach the lobby
- **Where data lives:** File binary data → local filesystem (`./uploads/`). File metadata → PostgreSQL (`chatbox_files`). In production, file storage would move to object storage (S3, MinIO) but the architecture supports this via path abstraction

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

| # | Pattern | What It Does | Where It's Used | Why |
|---|---------|-------------|----------------|-----|
| 1 | **Database per Service** | Each service owns its own database. No service can read/write another service's database directly — only through APIs. Prevents schema changes in one service from breaking others. | Each service has its own PostgreSQL database (`chatbox_auth`, `chatbox_chat`, `chatbox_messages`, `chatbox_files`) | Loose coupling — services can change their schema without coordinating |
| 2 | **API Gateway** | A single entry point that sits in front of all services. Handles cross-cutting concerns (auth, rate limiting, logging, routing) so services don't duplicate this logic. | Kong routes all external requests on port 80 | Single entry point, consistent auth/rate-limiting across all services |
| 3 | **Event-Driven Architecture** | Services communicate by producing and consuming events (messages) through a broker. Producers don't know who consumes their events. Enables temporal decoupling — services don't need to be online simultaneously. | Kafka for async communication between all services | Services can evolve independently, no tight coupling |
| 4 | **CQRS (Command Query Responsibility Segregation)** | Separates the write model from the read model. The service that accepts data (commands) is different from the service that serves queries. Allows each side to be optimized independently. | Chat-service writes messages to Kafka, message-service consumes from Kafka and serves history via REST | Chat-service optimized for speed (Go), message-service optimized for queries (Python + SQLAlchemy) |
| 5 | **Saga Pattern** | Coordinates a multi-service transaction through a sequence of events. If one step fails, compensating events are published to undo previous steps. Used instead of distributed transactions (2PC). | User deletion: auth-service publishes `user_deleted` → other services clean up their data | No distributed transactions needed across services |
| 6 | **Circuit Breaker** | Tracks failures in service-to-service calls. After N consecutive failures, "opens" the circuit and immediately returns errors for a cooldown period instead of sending doomed requests. After cooldown, allows one probe request to test recovery. | Message-service → auth-service REST calls (5 failures → 30s cooldown). See `services/message-service/app/infrastructure/auth_client.py` | Prevents cascading failures when auth-service is down |
| 7 | **Strangler Fig** | Incrementally migrates from a legacy system by routing traffic to the new system piece by piece, until the old system can be removed. Named after strangler fig trees that grow around and eventually replace their host tree. | Migration from Python monolith (`v1/backend/`) to microservices | Incremental migration — no big-bang rewrite |
| 8 | **Correlation ID** | A unique identifier (UUID) injected at the API gateway and propagated through every service in the request chain. Every log line includes this ID, making it possible to trace a single user request across all services. | Kong injects `X-Request-ID` → all services propagate it in logs via structlog (Python) or Gin context (Go) | Distributed debugging across 4 services |
| 9 | **Dead Letter Queue** | A separate queue/topic where messages that failed processing after multiple retries are stored for later investigation. Prevents poison messages (malformed, too large, schema mismatch) from blocking the main processing pipeline. | Kafka `chat.dlq` topic — messages that fail 3 times. 7-day retention (cluster default) for investigation | Failed messages preserved, not lost |
| 10 | **Health Check API** | Each service exposes endpoints that report whether it's alive (`/health`) and ready to handle traffic (`/ready`). Used by orchestrators (Docker, Kubernetes) to automatically restart unhealthy services or remove them from load balancers. | `/health` and `/ready` endpoints per service. `/ready` checks DB, Redis, and Kafka connectivity | Automatic failure detection and recovery |
| 11 | **Competing Consumers** | Multiple instances of a service consume from the same queue/topic, where the broker ensures each message is delivered to only ONE instance. Enables horizontal scaling of consumers without duplicating work. Implemented via Kafka consumer groups. | `chat-persistence` consumer group in message-service, `chat-file-events` group in chat-service | Scale message processing by adding more instances |
| 12 | **Idempotent Consumer** | The consumer can safely process the same message multiple times without side effects. Achieved by using a unique message ID + database uniqueness constraint. Before inserting, the consumer checks if the `message_id` already exists — if so, it skips the insert. Necessary because Kafka guarantees at-least-once delivery (not exactly-once). | Message-service uses `message_id` UUID with a `unique=True` constraint in PostgreSQL | Kafka retries + DB uniqueness = exactly-once semantics |
| 13 | **Bulkhead** | Isolates resources (connection pools, thread pools, memory) between components so that a failure or resource exhaustion in one doesn't affect others. Named after watertight compartments in ships that prevent one breach from sinking the vessel. | Separate PostgreSQL databases per service, each with its own connection pool (auth-service: `pool_size=10, max_overflow=20`; other services: framework defaults) | Connection leak in one service doesn't exhaust connections for others |
| 14 | **Externalized Configuration** | All environment-specific values (DB URLs, API keys, ports, feature flags) are loaded from environment variables, never hardcoded. The same container image runs in dev/staging/prod with different config. Principle #3 of the Twelve-Factor App methodology. | `.env` files per service, `docker-compose` environment blocks | Same image, different environments |

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

---

*Feature design decisions (Phase 1, 2, 3) are documented in [features.md](features.md).*
