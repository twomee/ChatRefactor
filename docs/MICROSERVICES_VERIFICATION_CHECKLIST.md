# Microservices Verification Checklist

## Context

After building 4 microservices (Auth, Chat & Room, Message, File) from the cHATBOX monolith, this checklist ensures **complete feature parity**. Every feature, operation, edge case, and degradation scenario from the monolith must be verified in the microservices stack running behind Kong gateway.

---

## 1. Authentication (Auth Service → Kong → `/auth/*`)

### Registration
- [ ] `POST /auth/register` — creates user, returns success
- [ ] Rejects duplicate username (409)
- [ ] Validates username: min 3, max 32, alphanumeric + underscore/hyphen only
- [ ] Validates password: min 8, max 128
- [ ] Rejects empty/whitespace-only fields
- [ ] Rate limited: 5/min per IP (Kong)
- [ ] Password stored as Argon2id hash
- [ ] Produces `auth.events` Kafka event

### Login
- [ ] `POST /auth/login` — returns JWT + username + is_global_admin
- [ ] Rejects invalid credentials (401, same message for wrong user or password)
- [ ] Rate limited: 10/min per IP (Kong)
- [ ] JWT contains: sub (user_id), username, exp (24h)
- [ ] Produces `auth.events` Kafka event

### Logout
- [ ] `POST /auth/logout` — blacklists token in Redis (TTL = 24h)
- [ ] Blacklisted token rejected on subsequent requests (401)
- [ ] Redis unavailable in prod → 503 (fail-closed)
- [ ] Redis unavailable in dev → succeeds with warning (fail-open)
- [ ] Produces `auth.events` Kafka event

### Ping
- [ ] `POST /auth/ping` — returns `{"ok": true}`, requires JWT

### Internal Endpoints (inter-service)
- [ ] `GET /auth/users/{id}` — returns user by ID (404 if not found)
- [ ] `GET /auth/users/by-username/{name}` — returns user by username

### Token Validation (all services)
- [ ] Expired tokens → 401
- [ ] Malformed tokens → 401
- [ ] Wrong secret → 401
- [ ] Blacklisted tokens → 401

---

## 2. Rooms (Chat & Room Service → Kong → `/rooms/*`)

### CRUD
- [ ] `GET /rooms/` — returns active rooms only, requires JWT
- [ ] `POST /rooms/` — creates room (admin only), rejects duplicates (409)
- [ ] Room name validation: max 64 chars, alphanumeric + spaces/underscore/hyphen

### Users
- [ ] `GET /rooms/{room_id}/users` — returns online users
- [ ] ETag caching: returns 304 when `If-None-Match` matches SHA256 of user list

### Room State
- [ ] `PUT /rooms/{id}/active` — open/close room
- [ ] Closing: sends `chat_closed`, closes WebSockets (code 4002)
- [ ] Opening: broadcasts updated room list

---

## 3. WebSocket Chat (Chat & Room Service → Kong → `/ws/*`)

### Room Connection (`WS /ws/{room_id}?token=...`)
- [ ] Auth via `?token=` query param
- [ ] Close 4001: invalid token
- [ ] Close 4002: room inactive
- [ ] Close 4003: user already in room (duplicate)
- [ ] Close 4004: room not found
- [ ] On connect: sends history (last 50 messages)
- [ ] On connect: broadcasts `user_join` with users/admins/muted lists
- [ ] On connect: system message "{user} has joined"
- [ ] First user auto-promoted to admin

### Sending Messages
- [ ] Type `message` → broadcasts to room
- [ ] Rate limit: 30 msgs/10s (sliding window, in-memory)
- [ ] Rejects empty messages
- [ ] Enforces max message length
- [ ] Rejects if user muted
- [ ] Generates UUID msg_id + ISO timestamp
- [ ] Produces to `chat.messages` Kafka (async)
- [ ] Falls back to sync DB if Kafka down
- [ ] Broadcasts via Redis pub/sub (local fallback if Redis down)

### Private Messages (via WS)
- [ ] Type `private_message` → delivers to target user
- [ ] Cannot PM yourself
- [ ] Target must be online
- [ ] Rate limited (same as chat)
- [ ] Produces to `chat.private` Kafka (sorted partition key)
- [ ] Echoed back to sender with `"self": true`

### Admin Commands
- [ ] **Kick**: admin kicks non-admin
  - [ ] Cannot kick self or other admin
  - [ ] Target gets `{"type": "kicked"}`, socket closed
  - [ ] No "user left" message for kicked users
  - [ ] Mute cleared on kick
- [ ] **Mute**: admin mutes non-admin
  - [ ] Cannot mute self, admin, or already-muted
  - [ ] Muted user sees error on send attempt
- [ ] **Unmute**: admin unmutes user
- [ ] **Promote**: admin promotes user to admin
  - [ ] Cannot promote self, already-admin, or muted user

### Disconnect
- [ ] Normal: broadcasts `user_left` + updated lists
- [ ] Admin leaving: removes admin → clears ALL mutes (amnesty) → promotes next in join order
- [ ] Admin succession: next user by join order becomes admin
- [ ] Kicked: counter-based tracking, skip "user left" message
- [ ] Mute cleared on leave

### Lobby Connection (`WS /ws/lobby?token=...`)
- [ ] Auth via `?token=`
- [ ] Receives PM delivery
- [ ] Receives `room_list_updated`
- [ ] Receives `file_shared` notifications

### Broadcast Message Types
- [ ] `user_join` — with users, admins, muted arrays
- [ ] `user_left` — with updated arrays
- [ ] `message` — from, text, room_id, msg_id, timestamp
- [ ] `system` — text, room_id
- [ ] `history` — messages array on join
- [ ] `room_list_updated` — rooms array
- [ ] `file_shared` — file_id, filename, size, from, room_id
- [ ] `chat_closed` — detail message
- [ ] `muted` / `unmuted` — username, room_id
- [ ] `new_admin` — username, room_id
- [ ] `kicked` — room_id
- [ ] `error` — detail message

---

## 4. Message Persistence (Message Service → Kong → `/messages/*`)

### Kafka Consumer (CQRS Write)
- [ ] Consumes `chat.messages` — persists room messages
- [ ] Consumes `chat.private` — persists PMs
- [ ] Idempotent: skips duplicate message_id UUIDs
- [ ] Retry: 3 attempts, exponential backoff (0.5s × attempt)
- [ ] DLQ: routes failures to `chat.dlq` with error context
- [ ] PM resolution: calls Auth Service for username → user_id
- [ ] Content length limit (DoS prevention)

### Replay API (CQRS Read)
- [ ] `GET /messages/rooms/{id}?since=ISO8601&limit=100` — missed messages
- [ ] Limit bounds: 1-500, default 100
- [ ] Requires JWT

### History API
- [ ] `GET /messages/rooms/{id}/history?limit=50` — recent messages
- [ ] Excludes private messages
- [ ] Requires JWT

---

## 5. Files (File Service → Kong → `/files/*`)

### Upload
- [ ] `POST /files/upload?room_id=X` — multipart, requires JWT
- [ ] Max size: 150 MB
- [ ] Extension allowlist enforced
- [ ] Rejects disallowed extensions (400)
- [ ] Rejects oversized files (413)
- [ ] Filename sanitization: path components, null bytes, CRLF, leading dots
- [ ] Path traversal prevention (resolved path within upload dir)
- [ ] UUID prefix for uniqueness
- [ ] Produces `file.events` Kafka → Chat Service broadcasts to room

### Download
- [ ] `GET /files/download/{file_id}` — stream file
- [ ] JWT from header OR `?token=` query param
- [ ] Path traversal check before serving
- [ ] 404 if file missing on disk
- [ ] Content-Disposition with properly escaped filename

### List
- [ ] `GET /files/room/{room_id}` — files in room, requires JWT

---

## 6. Admin Dashboard (Chat & Room Service → Kong → `/admin/*`)

- [ ] `GET /admin/users` — online users per room (global admin only)
- [ ] `GET /admin/rooms` — all rooms including inactive
- [ ] `POST /admin/chat/close` — close all rooms, disconnect everyone
- [ ] `POST /admin/chat/open` — reopen all rooms
- [ ] `POST /admin/rooms/{id}/close` — close specific room
- [ ] `POST /admin/rooms/{id}/open` — open specific room
- [ ] `DELETE /admin/db` — reset database (dev/staging only, 403 in prod)
- [ ] `POST /admin/promote?username=X` — promote in all connected rooms

---

## 7. Graceful Degradation

### Kafka Down
- [ ] Chat still delivers in real-time (Redis/local)
- [ ] Messages saved to DB synchronously (fallback)
- [ ] Health: reports "degraded" but stays ready

### Redis Down
- [ ] WebSocket delivery: local-only (same-process)
- [ ] Token blacklist: fail-closed in prod, fail-open in dev
- [ ] Rate limiting: in-memory fallback

### Database Down
- [ ] All services: readiness probe returns 503
- [ ] No fallback

---

## 8. Inter-Service Communication

### REST (synchronous)
- [ ] Chat → Auth: user lookup (PM, promote, mute)
- [ ] Chat → Message: fetch history on room join
- [ ] Message → Auth: username resolution for PM persistence
- [ ] Circuit breaker: handles downstream service failures gracefully

### Kafka (asynchronous)
- [ ] Chat → `chat.messages` → Message Service
- [ ] Chat → `chat.private` → Message Service
- [ ] Chat → `chat.events` → (future)
- [ ] File → `file.events` → Chat Service (broadcast)
- [ ] Auth → `auth.events` → (future)
- [ ] Message → `chat.dlq` → (monitoring)

---

## 9. Kong Gateway

### Routing
- [ ] All paths route to correct service
- [ ] WebSocket upgrade works through Kong
- [ ] WebSocket stays alive (no premature timeout)
- [ ] Reconnection works after disconnect

### Plugins
- [ ] CORS configured correctly
- [ ] Rate limiting: 100/min global, 5/min register, 10/min login
- [ ] X-Request-ID injected on all requests

---

## 10. Health Checks

- [ ] Auth: `/health` (liveness) + `/ready` (DB + Redis + Kafka)
- [ ] Chat: `/health` + `/ready` (DB + Redis + Kafka)
- [ ] Message: `/health` + `/ready` (DB + Kafka)
- [ ] File: `/health` + `/ready` (DB + Kafka)

---

## 11. Startup & Shutdown

### Startup
- [ ] PostgreSQL init script creates 4 databases
- [ ] Each service runs own migrations
- [ ] Auth seeds admin user + default rooms (politics, sports, movies)
- [ ] Kafka topics auto-created
- [ ] Prod fails fast on missing env vars
- [ ] Dev logs warning for default SECRET_KEY

### Shutdown
- [ ] Kafka consumers stop gracefully
- [ ] WebSockets closed (code 1001)
- [ ] No data loss

---

## 12. Security

- [ ] JWT: HS256 + shared secret, 24h expiry, Redis blacklist
- [ ] Passwords: Argon2id
- [ ] Input validation: username, password, room name, message length, file extension/size
- [ ] File security: path traversal, null bytes, CRLF, hidden files, Content-Disposition
- [ ] WebSocket: origin checking, message size limit (64KB), content limit (4096 chars)
- [ ] No error details in production health endpoints

---

## 13. Observability

- [ ] X-Request-ID propagated across all services
- [ ] Structured JSON logs in production
- [ ] Per-service log filtering: `docker compose logs <service>`

---

## 14. CI/CD

- [ ] Auth: ruff + pytest + Docker build
- [ ] Chat: go vet + go build + go test + Docker build
- [ ] Message: ruff + pytest + Docker build
- [ ] File: eslint + vitest + Docker build
- [ ] Integration: Kong config + compose syntax validation
- [ ] Security: Trivy + Gitleaks
- [ ] Dependabot: all 4 services + frontend + GitHub Actions

---

## 15. Docker Compose

- [ ] `docker compose up --build` — all services healthy
- [ ] Only Kong (80) and frontend (3000) exposed
- [ ] Internal DNS resolution between services
- [ ] PostgreSQL init script runs on first start
- [ ] Uploads volume persists across restarts

---

## 16. End-to-End Journeys

### Journey 1: New User
- [ ] Register → Login → Join room → Send message → See broadcast → Leave

### Journey 2: File Sharing
- [ ] Login → Join room → Upload → Others see notification → Download

### Journey 3: Private Messaging
- [ ] Login → Send PM → Recipient receives via lobby WS

### Journey 4: Admin Operations
- [ ] Mute user → Can't send → Unmute → Can send
- [ ] Kick user → Disconnected → Can rejoin
- [ ] Close room → All disconnected → Open room → Can rejoin

### Journey 5: Reconnection
- [ ] Chatting → Network drop → Auto-reconnect → Missed messages replayed

### Journey 6: Admin Succession
- [ ] A joins (admin) → B joins → A leaves → B becomes admin → Mutes cleared

### Journey 7: Multi-Room
- [ ] Join Room 1 → Join Room 2 → Send in Room 1 → Only Room 1 sees → Leave Room 2 → Room 1 works
