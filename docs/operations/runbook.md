# cHATBOX Operations Guide

A complete guide for running, debugging, and troubleshooting the cHATBOX microservices application.

> **Architecture note:** cHATBOX uses a **microservices architecture** with 4 backend services (Auth, Chat, Message, File) behind a Kong API Gateway. The original monolith is preserved at `v1/backend/` for reference only. This guide covers the microservices stack.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Project Overview](#2-project-overview)
3. [Environment Configuration](#3-environment-configuration)
4. [Running in Development Mode (Local)](#4-running-in-development-mode-local)
5. [Running in Production Mode (Docker)](#5-running-in-production-mode-docker)
6. [Running in Staging Mode](#6-running-in-staging-mode)
7. [Frontend: Local and Production](#7-frontend-local-and-production)
8. [PostgreSQL: Access and Commands](#8-postgresql-access-and-commands)
9. [Redis: Access and Commands](#9-redis-access-and-commands)
10. [Kafka: Access and Commands](#10-kafka-access-and-commands)
11. [Health Checks and Monitoring](#11-health-checks-and-monitoring)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

Install the following before starting:

| Tool | Version | Install | Used By |
|------|---------|---------|---------|
| Docker | 20+ | [docs.docker.com](https://docs.docker.com/get-docker/) | All services |
| Docker Compose | v2+ | Included with Docker Desktop | Orchestration |
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) | Auth & Message services |
| Go | 1.22+ | [go.dev](https://go.dev/dl/) | Chat service |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/) | File service & frontend |
| npm | 9+ | Comes with Node.js | File service & frontend |
| Git | 2.x | [git-scm.com](https://git-scm.com/) | Version control |

> **Docker-only deployment:** If you only need to run via Docker (production), only Docker, Docker Compose, and Git are required. Python, Go, and Node.js are only needed for local development.

Verify installations:

```bash
docker --version
docker compose version
python3 --version
go version
node --version
npm --version
git --version
```

---

## 2. Project Overview

### Architecture

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

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19 + Vite 8 |
| API Gateway | Kong 3.6 (declarative, dbless) |
| Auth Service | Python 3.11, FastAPI, Argon2id, JWT |
| Chat Service | Go 1.22, gorilla/websocket, Redis pub/sub |
| Message Service | Python 3.11, FastAPI, SQLAlchemy, Alembic |
| File Service | Node.js 20, TypeScript, Express, Multer, Prisma |
| Database | PostgreSQL 16 (4 databases, one per service) |
| Cache/PubSub | Redis 7 |
| Message Queue | Apache Kafka (KRaft mode) |
| Reverse Proxy | Nginx 1.25 (frontend SPA routing) |
| Containerization | Docker + Docker Compose |

### Default Credentials

| What | Username | Password |
|------|----------|----------|
| Admin user | `ido` | `changeme` |
| PostgreSQL | `chatbox` | `chatbox_pass` |

### Databases

Each service has its own PostgreSQL database, created automatically by `infra/docker/init/init-db.sh`:

| Service | Database | Key Tables |
|---------|----------|-----------|
| Auth Service | `chatbox_auth` | `users`, `token_blacklist` |
| Chat Service | `chatbox_chat` | `rooms`, `muted_users`, `room_state` |
| Message Service | `chatbox_messages` | `messages`, `private_messages` |
| File Service | `chatbox_files` | `files` (Prisma managed) |

---

## 3. Environment Configuration

### .env File (Project Root)

Copy the example and customize:

```bash
cp .env.example .env
```

**Key .env variables:**

```env
# App environment: dev | staging | prod
APP_ENV=dev

# Shared across all services
SECRET_KEY=change-this-in-production-use-openssl-rand-hex-32
ADMIN_USERNAME=ido
ADMIN_PASSWORD=changeme

# PostgreSQL (used by init-db.sh to create per-service databases)
POSTGRES_USER=chatbox
POSTGRES_PASSWORD=chatbox_pass

# Infrastructure
REDIS_URL=redis://localhost:6379/0
KAFKA_BOOTSTRAP_SERVERS=localhost:29092

# CORS (comma-separated origins)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Frontend (used during Vite build)
VITE_API_BASE=/api
VITE_WS_BASE=
```

### Key Differences Between Modes

| Variable | Dev (local services) | Prod (Docker) |
|----------|---------------------|---------------|
| `APP_ENV` | `dev` | `prod` |
| Database host | `localhost:5432` | `postgres:5432` |
| `REDIS_URL` | `redis://localhost:6379/0` | `redis://redis:6379/0` |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | `kafka:9092` |
| `SECRET_KEY` | dev default | strong random |
| `VITE_API_BASE` | `http://localhost:8001` (or per-service ports) | `/api` (Kong routes) |

> **Important:** In Docker Compose, services connect by Docker service names (`postgres`, `redis`, `kafka`), not `localhost`. When running services locally, use `localhost` since Docker maps ports to the host.

---

## 4. Running in Development Mode (Local)

This is the recommended setup for day-to-day development. Infrastructure runs in Docker, but services and frontend run natively for hot-reload.

### Step 1: Clone the Repository

```bash
git clone <repo-url> Chat-Project-Final
cd Chat-Project-Final
```

### Step 2: Set Up Environment Variables

```bash
cp .env.example .env
# Edit .env if needed — defaults work for local dev
```

### Step 3: Start Infrastructure Services

```bash
docker compose -f docker-compose.dev.yml up -d
```

This starts:
- **PostgreSQL** on port `5432` (with 4 databases auto-created)
- **Redis** on port `6379`
- **Kafka** on port `29092` (external listener for host access)

Verify services are healthy:

```bash
docker compose -f docker-compose.dev.yml ps
```

All services should show `healthy` status. Kafka may take 30-60 seconds to become healthy.

### Step 4: Start the Microservices

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

On first start, each service will:
1. Run database migrations (Alembic for Python services, Prisma for file-service)
2. Connect to Redis and Kafka
3. Auth service seeds the admin user and default rooms

**Services ready at:**
- Auth: `http://localhost:8001` (Swagger: `http://localhost:8001/docs`)
- Chat: `http://localhost:8003`
- Message: `http://localhost:8004` (Swagger: `http://localhost:8004/docs`)
- File: `http://localhost:8005`

### Step 5: Start the Frontend

```bash
cd frontend
npm install     # First time only
npm run dev
```

**Frontend is ready at:** `http://localhost:5173`

> **Note:** In local dev without Kong, update `frontend/.env` to point to the correct service ports for API calls.

### Step 6: Verify Everything Works

1. Open `http://localhost:5173` in your browser
2. Register a new user or log in with `ido` / `changeme`
3. Join a room and send a message
4. Check health endpoints:

```bash
curl http://localhost:8001/health    # Auth service
curl http://localhost:8003/health    # Chat service
curl http://localhost:8004/health    # Message service
curl http://localhost:8005/health    # File service
```

### Stopping Development

```bash
# Stop infrastructure
docker compose -f docker-compose.dev.yml down

# Stop each service: Ctrl+C in their respective terminals
# Stop frontend: Ctrl+C in the terminal
```

To **wipe all data** (all databases, Kafka logs):
```bash
docker compose -f docker-compose.dev.yml down -v
```

---

## 5. Running in Production Mode (Docker)

Everything runs inside Docker containers — no local Python, Go, or Node needed.

### Step 1: Configure Production Environment

```bash
cp .env.example .env
```

Edit `.env` for production:

```env
APP_ENV=prod
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-password>
POSTGRES_PASSWORD=<strong-password>
```

> **Generate a secure SECRET_KEY:**
> ```bash
> openssl rand -hex 32
> ```

### Step 2: Build and Start All Services

```bash
docker compose up -d --build
```

This builds and starts the following containers:

**Infrastructure:**
1. **postgres** — PostgreSQL 16 (4 per-service databases)
2. **redis** — Redis 7 (pub/sub, token blacklist, rate limiting)
3. **kafka** — Apache Kafka KRaft (async messaging)

**Init containers** (run once and exit):
4. **db-init** — Creates databases, runs migrations
5. **kafka-init** — Creates Kafka topics

**Application services:**
6. **kong** — API Gateway (port 80, routes all traffic)
7. **auth-service** — Python/FastAPI (port 8001 internal)
8. **chat-service** — Go/WebSocket (port 8003 internal)
9. **message-service** — Python/FastAPI (port 8004 internal)
10. **file-service** — Node.js/Express (port 8005 internal)
11. **frontend** — Nginx + React build (port 3000, served through Kong)

### Step 3: Check Container Status

```bash
docker compose ps
```

All containers should show `healthy` or `running`. Watch the startup order:
1. postgres, redis, kafka start first
2. db-init and kafka-init run migrations and topic creation
3. Services start after infrastructure is healthy
4. Kong and frontend start last

### Step 4: Watch Logs

```bash
# All services
docker compose logs -f

# Individual services
docker compose logs -f auth-service
docker compose logs -f chat-service
docker compose logs -f message-service
docker compose logs -f file-service
docker compose logs -f kong
docker compose logs -f frontend
```

### Step 5: Access the Application

**App:** `http://localhost` (port 80, through Kong)

Kong routes:
- `/api/auth/*` → auth-service
- `/ws/chat/*` → chat-service (WebSocket upgrade)
- `/api/messages/*` → message-service
- `/api/files/*` → file-service
- Everything else → frontend (React SPA)

### Step 6: Verify Production Health

```bash
# Per-service health checks through Kong
curl http://localhost/api/auth/health
curl http://localhost/api/chat/health
curl http://localhost/api/messages/health
curl http://localhost/api/files/health
```

### Stopping Production

```bash
# Stop all containers (data preserved in volumes)
docker compose down

# Stop and DELETE all data (fresh start)
docker compose down -v
```

### Rebuilding After Code Changes

```bash
# Rebuild a specific service
docker compose up -d --build auth-service
docker compose up -d --build chat-service
docker compose up -d --build message-service
docker compose up -d --build file-service

# Rebuild everything
docker compose up -d --build
```

---

## 6. Running in Staging Mode

Staging uses the same infrastructure as dev (Docker infra + local services) but with `APP_ENV=staging`. This enables production-like behavior (rate limiting via Redis, structured JSON logging) while still allowing hot-reload.

### Step 1: Configure for Staging

Edit `.env`:

```env
APP_ENV=staging
SECRET_KEY=<generate-a-real-key>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-password>
REDIS_URL=redis://localhost:6379/0
KAFKA_BOOTSTRAP_SERVERS=localhost:29092
```

### Step 2: Start Infrastructure + Services + Frontend

Same as development (see Section 4), but with `APP_ENV=staging` set in your `.env`.

```bash
# Infrastructure
docker compose -f docker-compose.dev.yml up -d

# Start each service in its own terminal (same as Section 4, Step 4)
# Start frontend (same as Section 4, Step 5)
```

### What Changes in Staging vs Dev

| Behavior | Dev | Staging |
|----------|-----|---------|
| Rate limiting storage | In-memory | Redis |
| Logging format | Pretty console | Structured JSON |
| Error detail in responses | Verbose | Limited |

---

## 7. Frontend: Local and Production

### Local Development

```bash
cd frontend
npm install     # First time only
npm run dev     # Starts Vite dev server at http://localhost:5173
```

**Environment:** Uses `frontend/.env`:
```env
VITE_API_BASE=http://localhost:8001
VITE_WS_BASE=ws://localhost:8003
```

> **Note:** In local dev without Kong, the frontend must point directly to individual service ports. Adjust `VITE_API_BASE` depending on which service you're hitting (auth: 8001, messages: 8004, files: 8005).

### Local Production Preview

Build and preview the production bundle locally:

```bash
cd frontend
npm run build      # Outputs to frontend/dist/
npm run preview    # Serves build at http://localhost:4173
```

> Note: `preview` serves the static build but does NOT proxy to services. You need Kong or Nginx running for API routes to work.

### Docker Production

The frontend Dockerfile is a multi-stage build:

1. **Build stage:** Node 20 runs `npm ci && npm run build`
2. **Serve stage:** Nginx 1.25 serves the `dist/` folder

```bash
# Build and run with Docker Compose (includes Kong gateway)
docker compose up -d --build frontend
```

**Production environment:** Uses `frontend/.env.production`:
```env
VITE_API_BASE=/api
VITE_WS_BASE=
```

- API calls go to `/api/*` — Kong routes them to the correct microservice
- WebSocket connections go to `/ws/*` — Kong upgrades and routes to chat-service
- WebSocket auto-detects protocol based on `window.location`

---

## 8. PostgreSQL: Access and Commands

### Per-Service Databases

Each microservice has its own database:

| Database | Service | Connect Command |
|----------|---------|----------------|
| `chatbox_auth` | Auth Service | `psql -h localhost -U chatbox -d chatbox_auth` |
| `chatbox_chat` | Chat Service | `psql -h localhost -U chatbox -d chatbox_chat` |
| `chatbox_messages` | Message Service | `psql -h localhost -U chatbox -d chatbox_messages` |
| `chatbox_files` | File Service | `psql -h localhost -U chatbox -d chatbox_files` |

### Connecting to PostgreSQL

**From host (when running via Docker):**

```bash
# Connect to a specific service database
psql -h localhost -U chatbox -d chatbox_auth
# Password: chatbox_pass

# Or using Docker exec
docker compose exec postgres psql -U chatbox -d chatbox_auth

# Dev stack variant
docker compose -f docker-compose.dev.yml exec postgres psql -U chatbox -d chatbox_auth

# List all databases
docker compose exec postgres psql -U chatbox -c "\l"
```

### Essential PostgreSQL Commands

> **Important:** With database-per-service, you must connect to the correct database for each query. Tables like `users` live in `chatbox_auth`, `rooms` in `chatbox_chat`, `messages` in `chatbox_messages`, etc. Cross-database JOINs are not possible.

**Auth database (`chatbox_auth`):**

```sql
-- Connect: psql -h localhost -U chatbox -d chatbox_auth

\dt                          -- List tables (users, etc.)
SELECT * FROM users;
SELECT id, username, is_global_admin, created_at FROM users WHERE username = 'ido';
SELECT * FROM alembic_version;
```

**Chat database (`chatbox_chat`):**

```sql
-- Connect: psql -h localhost -U chatbox -d chatbox_chat

\dt                          -- List tables (rooms, muted_users, room_state)
SELECT * FROM rooms;
SELECT * FROM muted_users;
```

**Messages database (`chatbox_messages`):**

```sql
-- Connect: psql -h localhost -U chatbox -d chatbox_messages

\dt                          -- List tables (messages, private_messages)
SELECT * FROM messages ORDER BY sent_at DESC LIMIT 20;
SELECT * FROM private_messages ORDER BY sent_at DESC LIMIT 20;
SELECT * FROM alembic_version;
```

**Files database (`chatbox_files`):**

```sql
-- Connect: psql -h localhost -U chatbox -d chatbox_files

\dt                          -- List tables (files, _prisma_migrations)
SELECT * FROM files ORDER BY uploaded_at DESC LIMIT 10;
```

**Cross-database checks:**

```sql
-- Check active connections across all databases
SELECT pid, usename, datname, client_addr, state FROM pg_stat_activity
WHERE datname LIKE 'chatbox_%';

-- Check sizes of all service databases
SELECT datname, pg_size_pretty(pg_database_size(datname))
FROM pg_database WHERE datname LIKE 'chatbox_%';
```

```
-- Exit psql
\q
```

### Useful psql Meta-Commands

```
\l          -- List all databases
\dt         -- List all tables
\d <table>  -- Describe table structure
\di         -- List all indexes
\du         -- List all roles/users
\conninfo   -- Show current connection info
\timing     -- Toggle query timing display
\x          -- Toggle expanded output mode
\q          -- Quit
```

### Database Maintenance

```sql
-- Reset a user's password (connect to chatbox_auth first)
-- Note: Argon2 hashing means you can't SET a plain password. Delete and re-register instead.
DELETE FROM users WHERE username = 'someuser';

-- Deactivate a room (connect to chatbox_chat first)
UPDATE rooms SET is_active = false WHERE name = 'politics';

-- Clear all messages (connect to chatbox_messages first — careful!)
TRUNCATE messages CASCADE;

-- Check individual database sizes
SELECT pg_size_pretty(pg_database_size('chatbox_auth'));
SELECT pg_size_pretty(pg_database_size('chatbox_messages'));
```

---

## 9. Redis: Access and Commands

### Connecting to Redis

```bash
# From host
redis-cli -h localhost -p 6379

# Using Docker exec
docker compose exec redis redis-cli

# Dev stack
docker compose -f docker-compose.dev.yml exec redis redis-cli
```

### Essential Redis Commands

**Once inside the `redis-cli` shell:**

```bash
# Test connection
PING
# Expected: PONG

# See all keys
KEYS *

# Check blacklisted tokens (logout tokens)
KEYS blacklist:*

# Check a specific blacklisted token
GET blacklist:<token-value>

# See TTL of a blacklisted token (seconds remaining)
TTL blacklist:<token-value>

# Check how many keys exist
DBSIZE

# Monitor real-time commands (useful for debugging pub/sub)
MONITOR

# Check Redis server info
INFO

# Check memory usage
INFO memory

# Check connected clients
INFO clients
CLIENT LIST

# Check pub/sub channels currently active
PUBSUB CHANNELS *

# Check number of subscribers on a channel
PUBSUB NUMSUB room:1
PUBSUB NUMSUB lobby

# Subscribe to a channel (for debugging — blocks the terminal)
SUBSCRIBE room:1
SUBSCRIBE lobby
SUBSCRIBE user:1

# Subscribe to all room channels
PSUBSCRIBE room:*

# Publish a test message to a channel
PUBLISH room:1 '{"type": "test", "content": "hello"}'

# Delete a specific key
DEL blacklist:<token-value>

# Flush the entire database (careful!)
FLUSHDB

# Exit redis-cli
QUIT
```

### Redis Usage in cHATBOX

| Purpose | Key Pattern | TTL |
|---------|------------|-----|
| Token blacklist (logout) | `blacklist:<jwt-token>` | 24 hours |
| Pub/Sub: Room messages | Channel `room:<room_id>` | N/A (pub/sub) |
| Pub/Sub: Lobby updates | Channel `lobby` | N/A (pub/sub) |
| Pub/Sub: User-targeted | Channel `user:<user_id>` | N/A (pub/sub) |
| Rate limiting (Kong) | Managed by Kong rate-limiting plugin | Auto-expiring |

---

## 10. Kafka: Access and Commands

### Connecting to Kafka

Kafka runs in KRaft mode (no ZooKeeper). The CLI tools are inside the container.

```bash
# Enter the Kafka container shell
docker compose exec kafka bash

# Dev stack
docker compose -f docker-compose.dev.yml exec kafka bash
```

> Once inside, Kafka CLI tools are at `/opt/kafka/bin/`.

### Essential Kafka Commands

**All commands below are run inside the Kafka container.**

#### Topic Management

```bash
# List all topics
/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

# Describe a topic (partitions, replicas, retention)
/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic chat.messages
/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic chat.private
/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic chat.events
/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic chat.dlq

# Create a topic manually (normally auto-created on startup)
/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create \
  --topic chat.messages --partitions 6 --replication-factor 1

# Delete a topic
/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic chat.dlq
```

#### Consuming Messages (Reading)

```bash
# Read messages from a topic (from beginning)
/opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic chat.messages --from-beginning

# Read only new messages (real-time tail)
/opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic chat.messages

# Read from chat.private topic
/opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic chat.private --from-beginning

# Read from Dead Letter Queue
/opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic chat.dlq --from-beginning

# Read with key and timestamp
/opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic chat.messages --from-beginning \
  --property print.key=true --property print.timestamp=true

# Read last N messages
/opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic chat.messages --max-messages 10 --from-beginning
```

#### Producing Messages (Writing — for testing)

```bash
# Send a test message to a topic
/opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 \
  --topic chat.messages
# Then type JSON messages, one per line:
# {"sender_id": 1, "room_id": 1, "content": "test message", "message_id": "test-123"}
# Press Ctrl+C to stop
```

#### Consumer Groups

```bash
# List consumer groups
/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list

# Describe the message-service consumer group (see lag)
/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group message-persistence

# Reset consumer group offset (to reprocess messages)
/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group message-persistence --topic chat.messages --reset-offsets --to-earliest --execute
```

#### Cluster Health

```bash
# Check broker API versions (health check)
/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092

# Check cluster metadata
/opt/kafka/bin/kafka-metadata.sh --snapshot /tmp/kraft-combined-logs/__cluster_metadata-0/00000000000000000000.log --cluster-id MkU3OEVBNTcwNTJENDM2Qk
```

### Kafka Topics in cHATBOX

| Topic | Partitions | Retention | Producer | Consumer | Purpose |
|-------|-----------|-----------|----------|----------|---------|
| `chat.messages` | 6 | 7 days | Chat Service | Message Service | Room chat messages |
| `chat.private` | 3 | 7 days | Chat Service | Message Service | Private messages |
| `chat.events` | 3 | 3 days | Chat Service | — (future) | System events (joins, leaves) |
| `file.events` | 3 | 3 days | File Service | Chat Service | File upload notifications |
| `auth.events` | 3 | 3 days | Auth Service | — (future) | User registration/login events |
| `chat.dlq` | 1 | 30 days | Any (on failure) | — (monitoring) | Dead letter queue |

### Connection Ports

| Context | Bootstrap Server |
|---------|-----------------|
| From inside Docker network | `kafka:9092` |
| From host machine (dev) | `localhost:29092` |

> The dev compose file exposes port `29092` with an `EXTERNAL` listener for host access. The production compose file does NOT expose Kafka to the host.

---

## 11. Health Checks and Monitoring

### Per-Service Health Endpoints

Each service exposes `/health` (liveness) and `/ready` (readiness) endpoints.

**Through Kong (production):**
```bash
curl http://localhost/api/auth/health
curl http://localhost/api/chat/health
curl http://localhost/api/messages/health
curl http://localhost/api/files/health
```

**Direct access (development):**
```bash
curl http://localhost:8001/health     # Auth service
curl http://localhost:8003/health     # Chat service
curl http://localhost:8004/health     # Message service
curl http://localhost:8005/health     # File service
```

**Expected responses:**
```json
{"status": "ok", "service": "auth-service", "version": "1.0.0"}
{"status": "ready", "database": "ok", "redis": "ok", "kafka": "ok"}
```

### Docker Health Status

```bash
# See health status of all containers
docker compose ps

# Check specific service health
docker inspect --format='{{.State.Health.Status}}' chatbox-auth-service-1
docker inspect --format='{{.State.Health.Status}}' chatbox-chat-service-1
docker inspect --format='{{.State.Health.Status}}' chatbox-message-service-1
docker inspect --format='{{.State.Health.Status}}' chatbox-file-service-1
```

### Logs

```bash
# All services
docker compose logs -f

# Individual service (last 100 lines, follow)
docker compose logs -f --tail=100 auth-service
docker compose logs -f --tail=100 chat-service
docker compose logs -f --tail=100 message-service
docker compose logs -f --tail=100 file-service
docker compose logs -f --tail=100 kong
docker compose logs -f --tail=100 postgres
docker compose logs -f --tail=100 redis
docker compose logs -f --tail=100 kafka
```

---

## 12. Troubleshooting

### Service Won't Start

**"Connection refused" to PostgreSQL:**
```bash
# Check if postgres is running
docker compose -f docker-compose.dev.yml ps postgres

# Check postgres logs
docker compose -f docker-compose.dev.yml logs postgres

# Verify you can connect to a service database
psql -h localhost -U chatbox -d chatbox_auth
```

**"Connection refused" to Redis:**
```bash
# Check if redis is running
docker compose -f docker-compose.dev.yml ps redis

# Test connection
redis-cli -h localhost -p 6379 PING
```

**Alembic migration errors (auth-service or message-service):**
```bash
cd services/auth-service    # or services/message-service
source venv/bin/activate

# Check current migration version
alembic current

# See migration history
alembic history

# Re-run migrations
alembic upgrade head

# If migrations are corrupted, reset (DELETES ALL DATA in that service DB)
alembic downgrade base
alembic upgrade head
```

**Prisma migration errors (file-service):**
```bash
cd services/file-service
npx prisma migrate deploy
```

### Per-Service Troubleshooting

#### Auth Service (Python/FastAPI, port 8001)

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Login returns 500 | Database connection failed | Check `docker compose logs auth-service`, verify PostgreSQL is healthy |
| JWT validation fails in other services | SECRET_KEY mismatch between services | Ensure all services share the same `SECRET_KEY` environment variable |
| Registration rate limited | Kong rate limit | Check Kong config in `infra/kong/kong.yml` |
| Token blacklist not working | Redis connection failed | Check Redis connectivity from auth-service |

#### Chat Service (Go, port 8003)

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| WebSocket connection refused | Service not running or Kong route misconfigured | Check `docker compose logs chat-service`, verify Kong routes |
| Messages not broadcasting | Redis pub/sub disconnected | Check Redis: `redis-cli PUBSUB CHANNELS *` |
| Messages not persisting | Kafka producer failed | Check Kafka: `docker compose logs kafka` |
| High memory usage | Too many idle WebSocket connections | Check active connections via metrics endpoint |

#### Message Service (Python/FastAPI, port 8004)

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| History returns empty | Kafka consumer lagging | Check consumer lag (see Kafka section) |
| Kafka consumer stuck | Consumer group offset issue | Reset consumer group offsets |
| 500 on message replay | Database connection pool exhausted | Check service logs, increase pool size |

#### File Service (Node.js/TypeScript, port 8005)

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Upload returns 413 | File too large (exceeds Kong limit) | Increase `client_max_body_size` in Kong config |
| Upload returns 500 | Disk full or permission error | Check disk space: `df -h`, check upload directory |
| Download returns 404 | File deleted or path mismatch | Check file metadata in database |

### Kafka Issues

**"Kafka unavailable" warning on service start:**

This is normal if Kafka hasn't finished starting yet. Services degrade gracefully — the chat service falls back to synchronous delivery.

```bash
# Check if Kafka is healthy (may take 30-60 seconds)
docker compose -f docker-compose.dev.yml ps kafka

# Check Kafka logs
docker compose -f docker-compose.dev.yml logs kafka

# Verify Kafka is responding
docker compose -f docker-compose.dev.yml exec kafka \
  /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092
```

**Consumer lag (messages not being persisted):**
```bash
docker compose exec kafka \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group message-persistence
```

Look at the `LAG` column. If lag keeps growing, the consumer may be stuck.

**Messages in Dead Letter Queue:**
```bash
docker compose exec kafka \
  /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic chat.dlq --from-beginning
```

### Frontend Issues

**"Network Error" or CORS errors in browser console:**
- In Docker: verify Kong is routing correctly — `curl http://localhost/api/auth/health`
- In local dev: verify `VITE_API_BASE` in `frontend/.env` points to the correct service port
- Check the `.env` at project root has correct `CORS_ORIGINS`

**Blank page after build:**
```bash
cd frontend
rm -rf dist node_modules
npm install
npm run build
npm run preview
```

**WebSocket connection fails:**
- In Docker: check Kong WebSocket route — `curl http://localhost:8001/routes`
- In local dev: check `VITE_WS_BASE` is `ws://localhost:8003`
- Check browser console for WebSocket errors

### Docker Issues

**Port already in use:**
```bash
# Find what's using the port
sudo lsof -i :5432
sudo lsof -i :6379
sudo lsof -i :8001

# Kill the process or stop the other container
docker compose down
```

**Container keeps restarting:**
```bash
# Check logs for the failing container
docker compose logs auth-service
docker compose logs chat-service

# Check the health check
docker inspect --format='{{json .State.Health}}' chatbox-auth-service-1 | python3 -m json.tool
```

**Out of disk space (Docker volumes):**
```bash
docker system df
docker system prune
docker volume prune    # careful — this deletes data
```

**Rebuild from scratch:**
```bash
docker compose down -v
docker compose down --rmi all
docker compose up -d --build
```

### Database Reset

```bash
# Option 1: Drop and recreate via Docker (all services)
docker compose down -v   # Removes the pgdata volume
docker compose up -d     # Recreates everything from scratch

# Option 2: Reset a specific service's DB via Alembic
cd services/auth-service
alembic downgrade base
alembic upgrade head
# Restart the service to re-seed default data
```

### Common Checks Cheat Sheet

| What to check | Command |
|----------------|---------|
| All services running? | `docker compose ps` |
| Auth service healthy? | `curl localhost/api/auth/health` |
| Chat service healthy? | `curl localhost/api/chat/health` |
| Message service healthy? | `curl localhost/api/messages/health` |
| File service healthy? | `curl localhost/api/files/health` |
| Kong healthy? | `curl localhost:8001/status` |
| Postgres accessible? | `psql -h localhost -U chatbox -d chatbox_auth -c "SELECT 1"` |
| Redis accessible? | `redis-cli PING` |
| Kafka accessible? | `docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list` |
| Consumer lag | `docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group message-persistence` |
| DLQ messages | `docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic chat.dlq --from-beginning` |
| Active WebSocket channels | `redis-cli PUBSUB CHANNELS *` |
| Token blacklist count | `redis-cli KEYS blacklist:* \| wc -l` |
| Kong routes | `curl localhost:8001/routes` |

