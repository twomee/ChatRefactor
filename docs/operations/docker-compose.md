# Docker Compose Operations

> **First time?** See [Getting Started](../getting-started.md) to get cHATBOX running. This guide covers day-to-day Docker Compose operations, infrastructure commands, and troubleshooting.

---

## Table of Contents

1. [Running in Production Mode (Docker)](#1-running-in-production-mode-docker)
2. [Running in Staging Mode](#2-running-in-staging-mode)
3. [Frontend: Local and Production](#3-frontend-local-and-production)
4. [PostgreSQL: Access and Commands](#4-postgresql-access-and-commands)
5. [Redis: Access and Commands](#5-redis-access-and-commands)
6. [Kafka: Access and Commands](#6-kafka-access-and-commands)
7. [Health Checks and Monitoring](#7-health-checks-and-monitoring)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Running in Production Mode (Docker)

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
make deploy
```

This is equivalent to `docker compose build && docker compose up -d && docker compose restart kong`.

| Target | What it does |
|--------|-------------|
| `make build` | Build all Docker images |
| `make up` | Start all containers, then restart Kong to re-resolve DNS |
| `make deploy` | `build` + `up` in one command — the standard deploy workflow |
| `make down` | Stop and remove all containers |

**Why `make deploy` and not `docker compose up -d --build` directly?**

Kong caches DNS resolutions at startup. When app containers are rebuilt and get new internal IPs, Kong still routes to the old IPs (502 errors) until it is restarted. `make up` always runs `docker compose restart kong` afterwards so Kong re-resolves service names with fresh IPs. `KONG_DNS_STALE_TTL=0` is already set in `docker-compose.yml` but this only prevents serving entries after their TTL expires — it does not force re-resolution when container IPs change mid-session.

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
# Rebuild everything (recommended — also restarts Kong)
make deploy

# Rebuild a specific service only
docker compose build auth-service && docker compose up -d auth-service
docker compose build chat-service && docker compose up -d chat-service && docker compose restart kong
```

> When rebuilding services that Kong proxies (any app service), always run `docker compose restart kong` or use `make deploy` — otherwise Kong routes to the old container IP.

---

## 2. Running in Staging Mode

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

## 3. Frontend: Local and Production

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

## 4. PostgreSQL: Access and Commands

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

## 5. Redis: Access and Commands

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

## 6. Kafka: Access and Commands

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

## 7. Health Checks and Monitoring

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

## 8. Troubleshooting

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
