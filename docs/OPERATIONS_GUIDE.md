# cHATBOX Operations Guide

A complete guide for running, debugging, and troubleshooting the cHATBOX application from scratch.

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
13. [Microservices Operations](#13-microservices-operations)

---

## 1. Prerequisites

Install the following before starting:

| Tool | Version | Install |
|------|---------|---------|
| Docker | 20+ | [docs.docker.com](https://docs.docker.com/get-docker/) |
| Docker Compose | v2+ | Included with Docker Desktop |
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/) |
| npm | 9+ | Comes with Node.js |
| Git | 2.x | [git-scm.com](https://git-scm.com/) |

Verify installations:

```bash
docker --version
docker compose version
python3 --version
node --version
npm --version
git --version
```

---

## 2. Project Overview

### Architecture

```
                   +----------+
                   |  Nginx   |  (port 80, prod only)
                   |  (SPA +  |
                   |  reverse  |
                   |  proxy)   |
                   +----+-----+
                        |
            +-----------+-----------+
            |                       |
     /api/* & /ws/*           Static files
            |                 (React build)
            v
     +-----------+
     |  FastAPI  |  (port 8000)
     |  Backend  |
     +-----+-----+
           |
     +-----+-----+-----+
     |           |       |
     v           v       v
 +--------+ +-------+ +-------+
 |Postgres| | Redis | | Kafka |
 | :5432  | | :6379 | | :9092 |
 +--------+ +-------+ +-------+
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19 + Vite 8 |
| Backend | FastAPI (Python 3.11) |
| Database | PostgreSQL 16 |
| Cache/PubSub | Redis 7 |
| Message Queue | Apache Kafka (KRaft mode) |
| Reverse Proxy | Nginx 1.25 (prod) |
| ASGI Server | Uvicorn (dev) / Gunicorn + Uvicorn workers (prod) |

### Default Credentials

| What | Username | Password |
|------|----------|----------|
| Admin user | `ido` | `changeme` |
| PostgreSQL | `chatbox` | `chatbox_pass` |

---

## 3. Environment Configuration

### .env File (Project Root)

Copy the example and customize:

```bash
cp .env.example .env
```

**Full .env reference:**

```env
# App environment: dev | staging | prod
APP_ENV=dev

# Backend
SECRET_KEY=change-this-in-production-use-openssl-rand-hex-32
ADMIN_USERNAME=ido
ADMIN_PASSWORD=changeme
DATABASE_URL=postgresql://chatbox:chatbox_pass@localhost:5432/chatbox
REDIS_URL=redis://localhost:6379/0
KAFKA_BOOTSTRAP_SERVERS=localhost:29092

# CORS (comma-separated origins)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Frontend (used during Vite build)
VITE_API_BASE=http://localhost:8000
VITE_WS_BASE=ws://localhost:8000
```

### Key Differences Between Modes

| Variable | Dev (local) | Staging | Prod (Docker) |
|----------|-------------|---------|---------------|
| `APP_ENV` | `dev` | `staging` | `prod` |
| `DATABASE_URL` | `...@localhost:5432/...` | `...@localhost:5432/...` | `...@postgres:5432/...` |
| `REDIS_URL` | `redis://localhost:6379/0` | `redis://localhost:6379/0` | `redis://redis:6379/0` |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | `localhost:29092` | `kafka:9092` |
| `SECRET_KEY` | dev default | strong random | strong random |

> **Important:** In Docker Compose, the backend connects to services by their Docker service names (`postgres`, `redis`, `kafka`), not `localhost`. When running locally, use `localhost` since Docker maps ports to the host.

---

## 4. Running in Development Mode (Local)

This is the recommended setup for day-to-day development. Infrastructure runs in Docker, but backend and frontend run natively for hot-reload.

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
- **PostgreSQL** on port `5432`
- **Redis** on port `6379`
- **Kafka** on port `29092` (external listener for host access)

Verify services are healthy:

```bash
docker compose -f docker-compose.dev.yml ps
```

All services should show `healthy` status. Kafka may take 30-60 seconds to become healthy.

### Step 4: Start the Backend

```bash
cd backend

# Create a virtual environment (first time only)
python3 -m venv venv
source venv/bin/activate    # Linux/Mac
# venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Run with hot-reload
uvicorn main:app --reload --port 8000
```

On first start, the backend will:
1. Run Alembic database migrations
2. Create default rooms: `politics`, `sports`, `movies`
3. Create the admin user (from `ADMIN_USERNAME`/`ADMIN_PASSWORD`)
4. Connect to Redis and start the pub/sub subscriber
5. Connect to Kafka, create topics, and start the consumer

**Backend is ready at:** `http://localhost:8000`
**API docs (Swagger):** `http://localhost:8000/docs`

### Step 5: Start the Frontend

```bash
cd frontend

# Install dependencies (first time only)
npm install

# Run dev server with hot-reload
npm run dev
```

**Frontend is ready at:** `http://localhost:5173`

### Step 6: Verify Everything Works

1. Open `http://localhost:5173` in your browser
2. Register a new user or log in with `ido` / `changeme`
3. Join a room and send a message
4. Check health: `curl http://localhost:8000/ready`

Expected response:
```json
{"status": "ready", "database": "ok", "redis": "ok", "kafka": "ok"}
```

### Stopping Development

```bash
# Stop infrastructure
docker compose -f docker-compose.dev.yml down

# Stop backend: Ctrl+C in the terminal
# Stop frontend: Ctrl+C in the terminal
```

To **wipe all data** (database, Kafka logs):
```bash
docker compose -f docker-compose.dev.yml down -v
```

---

## 5. Running in Production Mode (Docker)

Everything runs inside Docker containers — no local Python or Node needed.

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

This builds and starts 5 containers:
1. **postgres** — Database (port 5432)
2. **redis** — Cache and pub/sub (port 6379)
3. **kafka** — Message queue (port 9092 internal)
4. **backend** — FastAPI with Gunicorn (port 8000 internal)
5. **frontend** — Nginx + React build (port 80 exposed)

### Step 3: Check Container Status

```bash
docker compose ps
```

All containers should show `healthy` or `running`. Watch the startup order:
1. postgres, redis, kafka start first
2. backend waits for all three to be healthy
3. frontend waits for backend to be healthy

### Step 4: Watch Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f kafka
```

### Step 5: Access the Application

**App:** `http://localhost` (port 80)

Nginx routes:
- `/api/*` → backend (strips `/api` prefix)
- `/ws/*` → backend (WebSocket upgrade)
- `/health`, `/ready` → backend
- Everything else → React SPA (`index.html`)

### Step 6: Verify Production Health

```bash
curl http://localhost/health
# {"status": "ok"}

curl http://localhost/ready
# {"status": "ready", "database": "ok", "redis": "ok", "kafka": "ok"}
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
# Rebuild specific service
docker compose up -d --build backend
docker compose up -d --build frontend

# Rebuild everything
docker compose up -d --build
```

---

## 6. Running in Staging Mode

Staging uses the same infrastructure as dev (Docker services + local backend/frontend) but with `APP_ENV=staging`. This enables production-like behavior (rate limiting via Redis, structured JSON logging) while still allowing hot-reload.

### Step 1: Configure for Staging

Edit `.env`:

```env
APP_ENV=staging
SECRET_KEY=<generate-a-real-key>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-password>
DATABASE_URL=postgresql://chatbox:chatbox_pass@localhost:5432/chatbox
REDIS_URL=redis://localhost:6379/0
KAFKA_BOOTSTRAP_SERVERS=localhost:29092
```

### Step 2: Start Infrastructure + Backend + Frontend

Same as development:

```bash
# Infrastructure
docker compose -f docker-compose.dev.yml up -d

# Backend
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm run dev
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
VITE_API_BASE=http://localhost:8000
VITE_WS_BASE=ws://localhost:8000
```

The frontend connects directly to the backend at `localhost:8000`.

### Local Production Preview

Build and preview the production bundle locally:

```bash
cd frontend
npm run build      # Outputs to frontend/dist/
npm run preview    # Serves build at http://localhost:4173
```

> Note: `preview` serves the static build but does NOT reverse-proxy to the backend. You'll need to adjust `VITE_API_BASE` or use Nginx.

### Docker Production

The frontend Dockerfile is a multi-stage build:

1. **Build stage:** Node 20 runs `npm ci && npm run build`
2. **Serve stage:** Nginx 1.25 serves the `dist/` folder

```bash
# Build and run with Docker Compose (includes Nginx reverse proxy)
docker compose up -d --build frontend
```

**Production environment:** Uses `frontend/.env.production`:
```env
VITE_API_BASE=/api
VITE_WS_BASE=
```

- API calls go to `/api/*` (Nginx proxies to backend)
- WebSocket auto-detects protocol based on `window.location`

---

## 8. PostgreSQL: Access and Commands

### Connecting to PostgreSQL

**From host (when running via Docker):**

```bash
# Using psql directly
psql -h localhost -U chatbox -d chatbox
# Password: chatbox_pass

# Or using Docker exec
docker compose exec postgres psql -U chatbox -d chatbox

# Dev stack variant
docker compose -f docker-compose.dev.yml exec postgres psql -U chatbox -d chatbox
```

### Essential PostgreSQL Commands

**Once inside the `psql` shell:**

```sql
-- List all tables
\dt

-- Describe a specific table (show columns, types, constraints)
\d users
\d rooms
\d messages
\d files
\d room_admins
\d muted_users

-- Show all table sizes
\dt+

-- View table data
SELECT * FROM users;
SELECT * FROM rooms;
SELECT * FROM messages ORDER BY sent_at DESC LIMIT 20;
SELECT * FROM files ORDER BY uploaded_at DESC LIMIT 10;
SELECT * FROM room_admins;
SELECT * FROM muted_users;

-- Count records in each table
SELECT 'users' AS table_name, COUNT(*) FROM users
UNION ALL SELECT 'rooms', COUNT(*) FROM rooms
UNION ALL SELECT 'messages', COUNT(*) FROM messages
UNION ALL SELECT 'files', COUNT(*) FROM files
UNION ALL SELECT 'room_admins', COUNT(*) FROM room_admins
UNION ALL SELECT 'muted_users', COUNT(*) FROM muted_users;

-- Find a specific user
SELECT id, username, is_global_admin, created_at FROM users WHERE username = 'ido';

-- See messages in a specific room
SELECT m.id, u.username, m.content, m.sent_at
FROM messages m JOIN users u ON m.sender_id = u.id
WHERE m.room_id = 1
ORDER BY m.sent_at DESC LIMIT 20;

-- See private messages between two users
SELECT m.id, s.username AS sender, r.username AS recipient, m.content, m.sent_at
FROM messages m
JOIN users u AS s ON m.sender_id = s.id
JOIN users u AS r ON m.recipient_id = r.id
WHERE m.is_private = true
ORDER BY m.sent_at DESC LIMIT 20;

-- See room admins
SELECT ra.id, u.username, r.name AS room_name, ra.appointed_at
FROM room_admins ra
JOIN users u ON ra.user_id = u.id
JOIN rooms r ON ra.room_id = r.id;

-- See muted users
SELECT mu.id, u.username, r.name AS room_name, mu.muted_at
FROM muted_users mu
JOIN users u ON mu.user_id = u.id
JOIN rooms r ON mu.room_id = r.id;

-- Check Alembic migration status
SELECT * FROM alembic_version;

-- Check active connections
SELECT pid, usename, datname, client_addr, state FROM pg_stat_activity WHERE datname = 'chatbox';

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
-- Reset a user's password (set to 'newpassword' — note: this won't work directly
-- because the app uses Argon2 hashing. Better to delete and re-register)
DELETE FROM users WHERE username = 'someuser';

-- Deactivate a room
UPDATE rooms SET is_active = false WHERE name = 'politics';

-- Clear all messages (careful!)
TRUNCATE messages CASCADE;

-- Check database size
SELECT pg_size_pretty(pg_database_size('chatbox'));
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
| Rate limiting (staging/prod) | Managed by slowapi | Auto-expiring |

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

# Describe the app's consumer group (see lag)
/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group chat-persistence

# Reset consumer group offset (to reprocess messages)
/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group chat-persistence --topic chat.messages --reset-offsets --to-earliest --execute
```

#### Cluster Health

```bash
# Check broker API versions (health check)
/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092

# Check cluster metadata
/opt/kafka/bin/kafka-metadata.sh --snapshot /tmp/kraft-combined-logs/__cluster_metadata-0/00000000000000000000.log --cluster-id MkU3OEVBNTcwNTJENDM2Qk
```

### Kafka Topics in cHATBOX

| Topic | Partitions | Retention | Purpose |
|-------|-----------|-----------|---------|
| `chat.messages` | 6 | 7 days | Room chat messages |
| `chat.private` | 3 | 7 days | Private messages |
| `chat.events` | 3 | 3 days | System events (joins, leaves) |
| `chat.dlq` | 1 | 30 days | Dead letter queue (failed messages) |

### Connection Ports

| Context | Bootstrap Server |
|---------|-----------------|
| From inside Docker network | `kafka:9092` |
| From host machine (dev) | `localhost:29092` |

> The dev compose file exposes port `29092` with an `EXTERNAL` listener for host access. The production compose file does NOT expose Kafka to the host.

---

## 11. Health Checks and Monitoring

### Backend Health Endpoints

```bash
# Liveness probe — is the process alive?
curl http://localhost:8000/health
# {"status": "ok"}

# Readiness probe — are DB, Redis, Kafka connected?
curl http://localhost:8000/ready
# {"status": "ready", "database": "ok", "redis": "ok", "kafka": "ok"}
```

In Docker production (through Nginx):
```bash
curl http://localhost/health
curl http://localhost/ready
```

### Docker Health Status

```bash
# See health status of all containers
docker compose ps

# Check a specific container's health
docker inspect --format='{{.State.Health.Status}}' chat-project-final-backend-1
```

### Logs

```bash
# All services
docker compose logs -f

# Specific service (last 100 lines, follow)
docker compose logs -f --tail=100 backend
docker compose logs -f --tail=100 postgres
docker compose logs -f --tail=100 redis
docker compose logs -f --tail=100 kafka
docker compose logs -f --tail=100 frontend
```

---

## 12. Troubleshooting

### Backend Won't Start

**"Connection refused" to PostgreSQL:**
```bash
# Check if postgres is running
docker compose -f docker-compose.dev.yml ps postgres

# Check postgres logs
docker compose -f docker-compose.dev.yml logs postgres

# Verify you can connect
psql -h localhost -U chatbox -d chatbox
```

**"Connection refused" to Redis:**
```bash
# Check if redis is running
docker compose -f docker-compose.dev.yml ps redis

# Test connection
redis-cli -h localhost -p 6379 PING
```

**Alembic migration errors:**
```bash
cd backend
source venv/bin/activate

# Check current migration version
alembic current

# See migration history
alembic history

# Re-run migrations
alembic upgrade head

# If migrations are corrupted, reset (DELETES ALL DATA)
alembic downgrade base
alembic upgrade head
```

### Kafka Issues

**"Kafka unavailable" warning on backend start:**

This is normal if Kafka hasn't finished starting yet. The backend degrades gracefully — messages are persisted synchronously to the database instead.

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
  --describe --group chat-persistence
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
- Verify the backend is running on port 8000
- Check that `VITE_API_BASE` in `frontend/.env` matches: `http://localhost:8000`
- Check the `.env` at project root has correct `CORS_ORIGINS`

**Blank page after build:**
```bash
cd frontend
# Clean and rebuild
rm -rf dist node_modules
npm install
npm run build
npm run preview
```

**WebSocket connection fails:**
- Check `VITE_WS_BASE` is `ws://localhost:8000` in dev
- In production, ensure Nginx is properly proxying `/ws/` with upgrade headers
- Check browser console for WebSocket errors

### Docker Issues

**Port already in use:**
```bash
# Find what's using the port
sudo lsof -i :5432
sudo lsof -i :6379
sudo lsof -i :8000

# Kill the process or stop the other container
docker compose down
```

**Container keeps restarting:**
```bash
# Check logs for the failing container
docker compose logs backend

# Check the health check
docker inspect --format='{{json .State.Health}}' chat-project-final-backend-1 | python3 -m json.tool
```

**Out of disk space (Docker volumes):**
```bash
# Check Docker disk usage
docker system df

# Clean unused resources
docker system prune

# Remove unused volumes (careful — this deletes data)
docker volume prune
```

**Rebuild from scratch:**
```bash
# Stop everything and remove volumes
docker compose down -v

# Remove all built images
docker compose down --rmi all

# Rebuild and start
docker compose up -d --build
```

### Database Reset

```bash
# Option 1: Drop and recreate via Docker
docker compose down -v   # Removes the pgdata volume
docker compose up -d     # Recreates everything from scratch

# Option 2: Reset via Alembic (keeps container running)
cd backend
alembic downgrade base
alembic upgrade head
# Restart backend to re-seed default data
```

### Common Checks Cheat Sheet

| What to check | Command |
|----------------|---------|
| All services running? | `docker compose ps` |
| Backend healthy? | `curl localhost:8000/ready` |
| Postgres accessible? | `psql -h localhost -U chatbox -d chatbox -c "SELECT 1"` |
| Redis accessible? | `redis-cli PING` |
| Kafka accessible? | `docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list` |
| Backend logs | `docker compose logs -f backend` |
| Consumer lag | `docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group chat-persistence` |
| DLQ messages | `docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic chat.dlq --from-beginning` |
| Active WebSocket channels | `redis-cli PUBSUB CHANNELS *` |
| Token blacklist count | `redis-cli KEYS blacklist:* \| wc -l` |

---

## 13. Microservices Operations

This section covers running and managing the microservices stack (4 services + Kong API Gateway), which is the production target architecture. The monolith sections above still apply for local development and the legacy deployment.

### Starting the Microservices Stack

```bash
# Build and start all microservices
docker compose -f docker-compose.microservices.yml up -d --build

# Or start specific services
docker compose -f docker-compose.microservices.yml up -d auth-service
docker compose -f docker-compose.microservices.yml up -d chat-service
docker compose -f docker-compose.microservices.yml up -d message-service
docker compose -f docker-compose.microservices.yml up -d file-service
```

### Stopping the Microservices Stack

```bash
# Stop all containers (data preserved in volumes)
docker compose -f docker-compose.microservices.yml down

# Stop and DELETE all data (fresh start)
docker compose -f docker-compose.microservices.yml down -v
```

### Rebuilding After Code Changes

```bash
# Rebuild a specific service
docker compose -f docker-compose.microservices.yml up -d --build auth-service
docker compose -f docker-compose.microservices.yml up -d --build chat-service
docker compose -f docker-compose.microservices.yml up -d --build message-service
docker compose -f docker-compose.microservices.yml up -d --build file-service

# Rebuild everything
docker compose -f docker-compose.microservices.yml up -d --build
```

### Per-Service Log Viewing

```bash
# All services at once
docker compose -f docker-compose.microservices.yml logs -f

# Individual service logs (last 100 lines, follow)
docker compose -f docker-compose.microservices.yml logs -f --tail=100 auth-service
docker compose -f docker-compose.microservices.yml logs -f --tail=100 chat-service
docker compose -f docker-compose.microservices.yml logs -f --tail=100 message-service
docker compose -f docker-compose.microservices.yml logs -f --tail=100 file-service

# Kong gateway logs
docker compose -f docker-compose.microservices.yml logs -f --tail=100 kong

# Infrastructure logs
docker compose -f docker-compose.microservices.yml logs -f --tail=100 kafka
docker compose -f docker-compose.microservices.yml logs -f --tail=100 redis
docker compose -f docker-compose.microservices.yml logs -f --tail=100 postgres
```

### Kong API Gateway

**Kong Admin API** (port 8001 by default):

```bash
# Check Kong status
curl http://localhost:8001/status

# List all configured services
curl http://localhost:8001/services

# List all configured routes
curl http://localhost:8001/routes

# List active plugins (JWT, rate-limiting, etc.)
curl http://localhost:8001/plugins

# Check upstream health
curl http://localhost:8001/upstreams
```

**Kong routes in cHATBOX:**

| Route | Upstream Service | Port | Protocol |
|-------|-----------------|------|----------|
| `/api/auth/*` | auth-service | 8001 | HTTP |
| `/ws/chat/*` | chat-service | 8003 | WebSocket |
| `/api/messages/*` | message-service | 8004 | HTTP |
| `/api/files/*` | file-service | 8005 | HTTP |

### Health Check URLs

Each service exposes health endpoints for monitoring and orchestration:

```bash
# Auth service
curl http://localhost:8001/health          # Direct
curl http://localhost/api/auth/health      # Through Kong

# Chat service
curl http://localhost:8003/health          # Direct
curl http://localhost/api/chat/health      # Through Kong

# Message service
curl http://localhost:8004/health          # Direct
curl http://localhost/api/messages/health  # Through Kong

# File service
curl http://localhost:8005/health          # Direct
curl http://localhost/api/files/health     # Through Kong

# Kong gateway itself
curl http://localhost:8001/status
```

**Expected responses:**

```json
// Healthy service
{"status": "ok", "service": "auth-service", "version": "1.0.0"}

// Healthy service with dependency checks (readiness)
{"status": "ready", "database": "ok", "redis": "ok", "kafka": "ok"}

// Kong status
{"database": {"reachable": true}, "server": {"connections_active": 5}}
```

### Container Status

```bash
# See health status of all microservice containers
docker compose -f docker-compose.microservices.yml ps

# Check a specific container's health
docker inspect --format='{{.State.Health.Status}}' chatbox-auth-service-1
docker inspect --format='{{.State.Health.Status}}' chatbox-chat-service-1
docker inspect --format='{{.State.Health.Status}}' chatbox-message-service-1
docker inspect --format='{{.State.Health.Status}}' chatbox-file-service-1
```

### Troubleshooting Per-Service Issues

#### Auth Service (Python/FastAPI, port 8001)

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Login returns 500 | Database connection failed | Check `docker compose logs auth-service`, verify PostgreSQL is healthy |
| JWT validation fails in other services | SECRET_KEY mismatch between services | Ensure all services share the same `SECRET_KEY` environment variable |
| Registration rate limited | Redis rate limit state | Check Redis: `redis-cli KEYS rate_limit:*` |
| Token blacklist not working | Redis connection failed | Check Redis connectivity from auth-service container |

```bash
# Check auth-service database
docker compose -f docker-compose.microservices.yml exec auth-service \
  python -c "from app.core.database import engine; print(engine.url)"

# Run auth-service migrations manually
docker compose -f docker-compose.microservices.yml exec auth-service \
  alembic upgrade head
```

#### Chat Service (Go, port 8003)

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| WebSocket connection refused | Service not running or Kong route misconfigured | Check `docker compose logs chat-service`, verify Kong routes |
| Messages not broadcasting | Redis pub/sub disconnected | Check Redis: `redis-cli PUBSUB CHANNELS *` |
| High memory usage | Too many idle WebSocket connections | Check goroutine count, verify connection cleanup |
| Messages not persisting | Kafka producer failed | Check Kafka: `docker compose logs kafka` |

```bash
# Check goroutine count (Go runtime metrics)
curl http://localhost:8003/debug/pprof/goroutine?debug=1

# Check active WebSocket connections
curl http://localhost:8003/metrics
```

#### Message Service (Python/FastAPI, port 8004)

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| History returns empty | Database has no messages yet, or Kafka consumer lagging | Check Kafka consumer lag (see Kafka section above) |
| Slow history queries | Missing indexes or large dataset | Check PostgreSQL `EXPLAIN ANALYZE` on slow queries |
| Kafka consumer stuck | Consumer group offset issue | Reset consumer group offsets (see Kafka section) |
| 500 on message replay | Database connection pool exhausted | Increase pool size in service config |

```bash
# Check message-service Kafka consumer status
docker compose -f docker-compose.microservices.yml exec kafka \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group message-persistence

# Run message-service migrations
docker compose -f docker-compose.microservices.yml exec message-service \
  alembic upgrade head
```

#### File Service (Node.js/TypeScript, port 8005)

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Upload returns 413 | File too large (exceeds Kong/Nginx limit) | Increase `client_max_body_size` in Kong config |
| Upload returns 500 | Disk full or permission error | Check disk space: `df -h`, check upload directory permissions |
| Download returns 404 | File deleted or path mismatch | Check file metadata in database, verify storage path |
| Slow uploads | Network bottleneck or disk I/O | Check disk IOPS, consider async upload processing |

```bash
# Check file-service disk usage
docker compose -f docker-compose.microservices.yml exec file-service \
  du -sh /app/uploads

# Check file-service database (Prisma)
docker compose -f docker-compose.microservices.yml exec file-service \
  npx prisma studio
```

### Microservices Common Checks Cheat Sheet

| What to Check | Command |
|----------------|---------|
| All services running? | `docker compose -f docker-compose.microservices.yml ps` |
| Kong healthy? | `curl http://localhost:8001/status` |
| Auth service healthy? | `curl http://localhost/api/auth/health` |
| Chat service healthy? | `curl http://localhost/api/chat/health` |
| Message service healthy? | `curl http://localhost/api/messages/health` |
| File service healthy? | `curl http://localhost/api/files/health` |
| All service logs | `docker compose -f docker-compose.microservices.yml logs -f` |
| Kafka consumer lag | `docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group message-persistence` |
| Redis pub/sub channels | `redis-cli PUBSUB CHANNELS *` |
| Kong routes configured? | `curl http://localhost:8001/routes` |
