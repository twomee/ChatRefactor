# Load Testing & Performance Profiling

Production-grade load testing suite for cHATBOX. Verifies the platform can handle real-world traffic before going public.

## Wait, What Is Load Testing?

Imagine your chat app works perfectly when you test it alone. But what happens when **500 people** try to log in, send messages, and upload files at the same time? That's what load testing answers.

Load testing = **simulating hundreds or thousands of fake users** hitting your app simultaneously, then measuring what happens. Does it stay fast? Do requests start failing? Does the server run out of memory?

Think of it like stress-testing a bridge: you don't just walk one person across and call it safe. You simulate rush-hour traffic to find out where it breaks.

### What Is Locust?

**Locust** is the tool we use to create those fake users. It's the industry-standard load testing framework for Python (like JMeter but much simpler, and written in Python so it fits our stack).

Here's how it works:

1. **You define "users"** — Python classes that describe what a fake user does (login, send messages, browse rooms)
2. **You tell Locust how many** — "Simulate 100 users, adding 10 per second"
3. **Locust spawns them all** — Each fake user runs your defined tasks with random timing
4. **You get metrics** — Requests/sec, response times, error rates, all in real-time

Locust has two modes:
- **Web UI mode**: Opens a dashboard at http://localhost:8089 where you can watch live charts
- **Headless mode**: Runs in the terminal, outputs CSV/HTML reports (used in CI pipelines)

### What Are p50, p95, p99?

These are **percentile response times** — the most important metrics in load testing:

- **p50 (median)**: 50% of requests were faster than this. The "normal" experience.
- **p95**: 95% of requests were faster than this. What your slowest "normal" users see.
- **p99**: 99% of requests were faster than this. The worst case (excluding extreme outliers).

**Example**: If p95 = 200ms, that means 95 out of 100 users get a response in under 200ms. The other 5 might wait longer. In production, you care about p95 more than averages because averages hide slow requests.

### What Is a "Spike Test" / "Soak Test"?

- **Spike test**: Traffic goes from 10 users to 200 instantly, then drops back. Tests: "Does the server crash under sudden load? Does it recover?"
- **Soak test**: Moderate traffic (50 users) for hours. Tests: "Does memory slowly leak? Do database connections gradually pile up?"
- **Stress test**: Keep adding users until something breaks. Tests: "What's the maximum this server can handle?"

### Why Pre-Provision Users?

Our backend rate-limits registrations to 5 per minute (to prevent spam). If we tried to create 100 fake users during the test, we'd get blocked after 5. So we create all users **before** the test starts, cache their login tokens, and reuse them. That's what `UserPool` does.

## What This Suite Tests

| Area | What's Measured | Why It Matters |
|------|----------------|----------------|
| **HTTP API** | Throughput, latency (p50/p95/p99), error rate | Ensures REST endpoints stay fast under concurrent users |
| **WebSocket** | Connection time, message round-trip, broadcast fan-out | Chat must feel instant — users notice >100ms delays |
| **User Journey** | Full lifecycle: register → login → chat → logout | Validates all components work together end-to-end |
| **DB Pool** | Connection exhaustion under zero-wait pressure | Finds the breaking point (240 max DB connections across 8 workers) |
| **Spike Recovery** | Behavior during sudden 10x traffic burst | Verifies the system recovers gracefully after a spike |
| **Soak Stability** | Memory leaks, connection leaks over hours | Catches slow resource leaks that only show up in production |
| **Auth Throughput** | Argon2 hash/verify + JWT encode/decode speed | Quantifies the login throughput ceiling (~210/sec at 8 workers) |

## Prerequisites

- Backend running locally or in Docker (`docker compose up -d`)
- Python 3.10+

```bash
cd loadtests
pip install -r requirements.txt
```

## Quick Start

### Run everything (recommended first time)

```bash
# Smoke test — quick validation (10 users, 2 min)
python3 scripts/run_all.py --level smoke

# Load test — standard production simulation (100 users, 10 min)
python3 scripts/run_all.py --level load

# Stress test — find breaking points (300 users, 15 min)
python3 scripts/run_all.py --level stress
```

The orchestrator will:
1. Check server readiness
2. Pre-provision test users (avoids rate limiting)
3. Run HTTP endpoint load test
4. Run user journey test
5. Run WebSocket stress test
6. Check pass/fail criteria
7. Generate reports in `reports/`

### Run individual scenarios

```bash
# HTTP endpoints with Locust web UI (http://localhost:8089)
# This opens a live dashboard where you can watch the test in real time
locust -f scenarios/http_endpoints.py --host http://localhost:8000

# HTTP endpoints headless (no UI, just results — good for CI)
locust -f scenarios/http_endpoints.py --headless \
  --users 100 --spawn-rate 10 --run-time 10m \
  --host http://localhost:8000 \
  --csv reports/http_load --html reports/http_load.html

# WebSocket connections + messaging
locust -f scenarios/websocket_chat.py --headless \
  --users 50 --spawn-rate 10 --run-time 5m \
  --host ws://localhost:8000

# Full user journey (register → login → WS → chat → logout)
locust -f scenarios/user_journey.py --headless \
  --users 20 --spawn-rate 5 --run-time 5m \
  --host http://localhost:8000

# DB pool stress test (zero-wait, maximum pressure)
locust -f scenarios/http_endpoints.py DbPoolStressUser --headless \
  --users 500 --spawn-rate 50 --run-time 5m \
  --host http://localhost:8000

# Spike test (10 → 200 → 10 users)
locust -f scenarios/spike_shape.py,scenarios/http_endpoints.py --headless \
  --host http://localhost:8000

# Standalone WebSocket stress (asyncio — more efficient for high connections)
python3 scripts/ws_stress.py --connections 100 --duration 60 --rooms 3
```

### Run micro-benchmarks

These measure how fast individual operations are (password hashing, JWT creation, etc.). Useful for understanding the hard limits of your system.

```bash
# All benchmarks
pytest benchmarks/ --benchmark-only -v

# Auth benchmarks only (Argon2 + JWT speed)
pytest benchmarks/bench_auth.py --benchmark-only -v

# Save benchmark results as JSON
pytest benchmarks/ --benchmark-only --benchmark-json=reports/benchmarks.json
```

---

## Microservices Load Tests (locustfile.py)

The `locustfile.py` in the root of `loadtests/` tests all four microservices through the Kong API Gateway. Unlike the monolith scenarios above (which target `localhost:8000` directly), these tests hit Kong on port 80, which routes to the correct service.

### Running Microservices Load Tests

```bash
# All four service user classes with web UI
locust -f locustfile.py --host http://localhost

# Single service user class
locust -f locustfile.py AuthUser --host http://localhost
locust -f locustfile.py ChatUser --host http://localhost
locust -f locustfile.py FileUser --host http://localhost
locust -f locustfile.py MessageUser --host http://localhost

# Headless CI mode
locust -f locustfile.py --headless \
  --users 200 --spawn-rate 20 --run-time 10m \
  --host http://localhost \
  --csv reports/microservices --html reports/microservices.html
```

Open the Locust UI at **http://localhost:8089**, configure users and spawn rate, then start.

### User Classes

| User Class | Service | Port | Weight | What It Tests |
|------------|---------|------|--------|---------------|
| **AuthUser** | auth-service (Python) | 8001 | 3 | Registration, login, token validation, logout |
| **ChatUser** | chat-service (Go) | 8003 | 5 | WebSocket connections, message send/receive, PMs |
| **FileUser** | file-service (Node.js) | 8005 | 2 | File upload (small/medium), list, download |
| **MessageUser** | message-service (Python) | 8004 | 4 | Message history, replay, pagination, private messages |

Weights control how many virtual users of each type are spawned. ChatUser has the highest weight because real-time messaging is the primary workload.

### AuthUser Tasks

| Task | Weight | Endpoint | What It Measures |
|------|--------|----------|-----------------|
| `login` | 5 | `POST /api/auth/login` | JWT issuance latency |
| `validate_token` | 3 | `GET /api/auth/me` | Token validation throughput |
| `register` | 1 | `POST /api/auth/register` | Registration throughput |
| `logout_and_relogin` | 1 | `POST /api/auth/logout` | Token blacklist + re-auth cycle |

### ChatUser Tasks

| Task | Weight | Protocol | What It Measures |
|------|--------|----------|-----------------|
| `send_message` | 8 | WebSocket | Message round-trip latency (send -> broadcast echo) |
| `send_private_message` | 2 | WebSocket | PM delivery latency |

### FileUser Tasks

| Task | Weight | Endpoint | What It Measures |
|------|--------|----------|-----------------|
| `list_files` | 4 | `GET /api/files/` | File listing throughput |
| `upload_small_file` | 3 | `POST /api/files/upload` | Small file (2.4KB) upload throughput |
| `download_file` | 2 | `GET /api/files/{id}/download` | Download throughput |
| `upload_medium_file` | 1 | `POST /api/files/upload` | Medium file (512KB) upload throughput |

### MessageUser Tasks

| Task | Weight | Endpoint | What It Measures |
|------|--------|----------|-----------------|
| `get_room_messages` | 5 | `GET /api/messages/rooms/{id}` | Recent history query performance |
| `get_messages_since` | 3 | `GET /api/messages/rooms/{id}?since=` | Timestamp-based replay performance |
| `get_messages_paginated` | 2 | `GET /api/messages/rooms/{id}?offset=&limit=` | Pagination throughput |
| `get_private_messages` | 1 | `GET /api/messages/private` | Private message retrieval |
| `health_check` | 1 | `GET /api/messages/health` | Service health probe |

### Microservices Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_URL` | `http://localhost` | Kong API Gateway URL |
| `WS_GATEWAY_URL` | `ws://localhost` | WebSocket gateway URL |
| `ADMIN_USERNAME` | `ido` | Admin user for seeding |
| `ADMIN_PASSWORD` | `changeme` | Admin password |
| `LOADTEST_USER_PREFIX` | `lt_user` | Prefix for generated usernames |
| `LOADTEST_USER_PASSWORD` | `LoadTest_Pass_123!` | Password for generated users |

### Expected Baselines

These baselines assume a local Docker Compose deployment with default resources:

| Metric | Target | Critical Threshold |
|--------|--------|--------------------|
| Auth login p95 | < 200ms | < 500ms |
| Auth register p95 | < 300ms | < 800ms |
| WS connect p95 | < 500ms | < 2000ms |
| WS message round-trip p95 | < 100ms | < 500ms |
| File upload (small) p95 | < 500ms | < 2000ms |
| File download p95 | < 200ms | < 1000ms |
| Message history p95 | < 150ms | < 500ms |
| Message replay p95 | < 200ms | < 800ms |
| Error rate | < 1% | < 5% |

### Recommended Load Profiles

| Profile | Users | Spawn Rate | Duration | Purpose |
|---------|-------|------------|----------|---------|
| Smoke | 10 | 2/s | 2m | Verify endpoints work |
| Load | 100 | 10/s | 10m | Normal production load |
| Stress | 500 | 50/s | 15m | Find breaking points |
| Spike | 50 -> 500 -> 50 | burst | 10m | Test auto-scaling / recovery |

---

## How Each Scenario Works

### `http_endpoints.py` — REST API Load Test

Simulates users browsing the app: listing rooms, checking who's online, loading message history. Each fake user grabs a pre-provisioned JWT token and fires weighted requests:

- List rooms (most frequent — weight 5)
- Check room users (weight 3)
- Load message history (weight 3)
- Health check (weight 1)
- Readiness check (weight 1)

Also includes `DbPoolStressUser` — an aggressive variant with zero wait time that hammers the database to find the connection pool ceiling.

### `websocket_chat.py` — WebSocket Chat Load Test

Simulates users connected to chat rooms sending messages. Each fake user:

1. Connects via WebSocket with JWT auth
2. Joins a random room
3. Sends chat messages and waits for the broadcast echo
4. Sends occasional private messages
5. Measures round-trip time (how long from sending to receiving your own message back)

This is the most important test for a chat app — it validates the real-time path: WebSocket → Redis pub/sub → broadcast.

### `user_journey.py` — Full Lifecycle Test

Each fake user goes through the complete flow a real person would:

1. Register a new account
2. Login and get a JWT token
3. List available rooms
4. Connect to a room via WebSocket
5. Send 3 chat messages (with human-like pauses)
6. Disconnect from the room
7. Logout

This catches integration bugs that only appear when the full stack works together.

### `spike_shape.py` — Traffic Pattern Shapes

Controls _how many_ users are active over time:

- **SpikeShape**: 10 users → suddenly 200 → hold → drop back to 10. Answers: "Does the server survive a traffic burst?"
- **SoakShape**: 50 users for 2 hours straight. Answers: "Are there memory leaks?"
- **SteppedShape**: Gradually increases (50 → 100 → 150 → 200 → 300). Answers: "At what user count does performance degrade?"

### `ws_stress.py` — Standalone WebSocket Stress

A standalone script (not Locust) that uses Python's asyncio to open many concurrent WebSocket connections. More efficient than Locust for raw connection count testing — one event loop can handle thousands of connections vs Locust's thread-per-user model.

## Test Levels

| Level | HTTP Users | WS Connections | Duration | When to Use |
|-------|-----------|----------------|----------|-------------|
| **smoke** | 10 | 20 | 2 min | CI pipeline, quick regression check |
| **load** | 100 | 100 | 10 min | Pre-release validation |
| **stress** | 300 | 300 | 15 min | Capacity planning, find breaking points |

## Pass/Fail Criteria

The `check_criteria.py` script verifies these thresholds (you can customize them):

| Metric | Smoke | Load/Stress |
|--------|-------|-------------|
| Error rate | < 1% | < 1% |
| p95 response time | < 500ms | < 200ms |
| p99 response time | < 1000ms | < 500ms |
| No endpoint at 100% failure | Required | Required |

```bash
# Check results against thresholds
python3 scripts/check_criteria.py --stats reports/http_stats.csv

# Use stricter thresholds
python3 scripts/check_criteria.py --stats reports/http_stats.csv --max-p95 100
```

Exit code 0 = PASS, 1 = FAIL. This makes it easy to use in CI pipelines.

## Docker Distributed Mode

If your local machine isn't powerful enough to simulate hundreds of users, run Locust in distributed mode (1 master + 4 workers):

```bash
docker compose -f docker-compose.yml -f loadtests/docker-compose.loadtest.yml up
```

Then open http://localhost:8089 for the Locust dashboard. The master coordinates the test and the workers generate the actual traffic.

## Directory Structure

```
loadtests/
  locustfile.py                  # Microservices load test (4 user classes via Kong)
  config.py                      # Settings (API base, user count, rooms)
  requirements.txt               # Python dependencies

  utils/
    user_pool.py                 # Pre-provisions users, caches JWT tokens
    ws_client.py                 # Async WebSocket client for cHATBOX protocol

  scenarios/                     # Locust test files (monolith-era scenarios)
    http_endpoints.py            # REST API load test (ChatHttpUser, DbPoolStressUser)
    websocket_chat.py            # WebSocket connections + messaging
    user_journey.py              # Full register → chat → logout lifecycle
    spike_shape.py               # Spike, Soak, and Stepped load shapes

  scripts/                       # Standalone scripts and tools
    run_all.py                   # Orchestrator — runs all scenarios in sequence
    ws_stress.py                 # Standalone asyncio WebSocket stress test
    check_criteria.py            # CI gate — pass/fail based on thresholds

  benchmarks/                    # Micro-benchmarks (pytest-benchmark)
    bench_auth.py                # Argon2 + JWT speed benchmarks
    bench_serialization.py       # JSON encode/decode for WS messages

  config/environments/           # Environment-specific settings
    local.env                    # Settings for local Docker development
    ci.env                       # Settings for CI pipelines

  reports/                       # Generated reports (.csv, .html, .json)
  Dockerfile.locust              # Locust container for distributed mode
  docker-compose.loadtest.yml    # Adds Locust to the Docker stack
```

## Configuration

Settings are loaded from environment variables or `.env` files:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOADTEST_API_BASE` | `http://localhost:8000` | Backend HTTP base URL |
| `LOADTEST_WS_BASE` | `ws://localhost:8000` | Backend WebSocket base URL |
| `LOADTEST_NUM_USERS` | `200` | Number of fake users to create |
| `LOADTEST_ROOMS` | `politics,sports,movies` | Chat rooms to use in tests |
| `ADMIN_USERNAME` | `ido` | Admin user for room creation |
| `ADMIN_PASSWORD` | `changeme` | Admin password |

Use environment files for different setups:
```bash
LOADTEST_ENV_FILE=config/environments/local.env python3 scripts/run_all.py --level smoke
```

## How Rate Limiting Is Handled

The backend rate-limits registration (5/min) and login (10/min) per IP. Load tests bypass this by:

1. **Pre-provisioning**: All fake users are created once **before** tests start via `UserPool`
2. **Token caching**: JWT tokens are cached in memory and reused throughout the entire test run
3. **Dev mode**: Rate limiting is disabled when `APP_ENV=dev` (see `backend/middleware/rate_limit.py`)

For staging/production testing, provision users before enabling rate limits, or add a load-test-specific exemption.

## Understanding the Results

### Locust Web UI (http://localhost:8089)

When running with `locust -f ...` (without `--headless`), open the dashboard to see:
- Real-time requests/sec and response times
- Error rate trends
- Response time distribution charts

This is the easiest way to explore — you can adjust user count live while watching the impact.

### Generated Reports

After a run, check `reports/` for:
- `*_stats.csv` — Per-endpoint statistics (request count, response times, error rate)
- `*_stats_history.csv` — Time-series data (for graphing trends over the test duration)
- `*.html` — Self-contained HTML report with charts (open in browser)
- `*_criteria.json` — Machine-readable pass/fail result for CI
- `ws_stress_*.json` — WebSocket stress test metrics

### What to Do When Something Fails

| Symptom | Likely Cause | What to Check |
|---------|-------------|----------------|
| **p95 > 200ms** | Database is slow under load | DB connection pool settings, slow queries, missing indexes |
| **WS round-trip > 100ms** | Message relay is bottlenecked | Redis pub/sub health, Kafka consumer lag |
| **Error rate > 1%** | Server is overwhelmed | Connection pool exhaustion, worker timeouts, Gunicorn worker count |
| **WS connect fails > 5%** | Too many concurrent connections | Gunicorn worker capacity, OS file descriptor limits |
| **Memory grows over time** | Memory leak | WebSocket connection cleanup in `infrastructure/websocket.py`, unclosed DB sessions |
| **p95 spikes then recovers** | Garbage collection pauses | Normal in Python — verify it recovers within seconds |
