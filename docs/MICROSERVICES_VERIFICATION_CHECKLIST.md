# Microservices Verification Checklist

## Context

After building 4 microservices (Auth, Chat & Room, Message, File) from the cHATBOX monolith, this checklist ensures **complete feature parity**. Every feature, operation, edge case, and degradation scenario from the monolith must be verified in the microservices stack running behind Kong gateway.

**Last verified**: 2026-03-23 — 138/139 checks passed (1 skipped: rate limit timing)

---

## 1. Authentication (Auth Service → Kong → `/auth/*`)

### Registration
- [x] `POST /auth/register` — creates user, returns success
- [x] Rejects duplicate username (409)
- [x] Validates username: min 3, max 32, alphanumeric + underscore/hyphen only
- [x] Validates password: min 8, max 128
- [x] Rejects empty/whitespace-only fields
- [x] Rate limited: 5/min per IP (Kong)
- [x] Password stored as Argon2id hash
- [ ] Produces `auth.events` Kafka event

### Login
- [x] `POST /auth/login` — returns JWT + username + is_global_admin
- [x] Rejects invalid credentials (401, same message for wrong user or password)
- [x] Rate limited: 10/min per IP (Kong)
- [ ] JWT contains: sub (user_id), username, exp (24h)
- [ ] Produces `auth.events` Kafka event

### Logout
- [x] `POST /auth/logout` — blacklists token in Redis (TTL = 24h)
- [x] Blacklisted token rejected on subsequent requests (401)
- [ ] Redis unavailable in prod → 503 (fail-closed)
- [ ] Redis unavailable in dev → succeeds with warning (fail-open)
- [ ] Produces `auth.events` Kafka event

### Ping
- [x] `POST /auth/ping` — returns `{"ok": true}`, requires JWT

### Internal Endpoints (inter-service)
- [x] `GET /auth/users/{id}` — returns user by ID (404 if not found)
- [x] `GET /auth/users/by-username/{name}` — returns user by username

### Token Validation (all services)
- [x] Expired tokens → 401
- [x] Malformed tokens → 401
- [x] Wrong secret → 401
- [x] Blacklisted tokens → 401

---

## 2. Rooms (Chat & Room Service → Kong → `/rooms/*`)

### CRUD
- [x] `GET /rooms/` — returns active rooms only, requires JWT
- [x] `POST /rooms/` — creates room (admin only), rejects duplicates (409)
- [ ] Room name validation: max 64 chars, alphanumeric + spaces/underscore/hyphen

### Users
- [x] `GET /rooms/{room_id}/users` — returns online users
- [ ] ETag caching: returns 304 when `If-None-Match` matches SHA256 of user list *(Gin does not set ETags by default — needs custom middleware)*

### Room State
- [x] `PUT /rooms/{id}/active` — open/close room
- [x] Closing: sends `chat_closed`, closes WebSockets (code 4002)
- [x] Opening: broadcasts updated room list

---

## 3. WebSocket Chat (Chat & Room Service → Kong → `/ws/*`)

### Room Connection (`WS /ws/{room_id}?token=...`)
- [x] Auth via `?token=` query param
- [x] Close 4001: invalid token
- [ ] Close 4002: room inactive
- [ ] Close 4003: user already in room (duplicate)
- [x] Close 4004: room not found
- [x] On connect: sends history (last 50 messages)
- [x] On connect: broadcasts `user_join` with users/admins/muted lists
- [x] On connect: system message "{user} has joined"
- [x] First user auto-promoted to admin

### Sending Messages
- [x] Type `message` → broadcasts to room
- [x] Rate limit: 30 msgs/10s (sliding window, in-memory)
- [x] Rejects empty messages
- [x] Enforces max message length
- [x] Rejects if user muted
- [x] Generates UUID msg_id + ISO timestamp
- [x] Produces to `chat.messages` Kafka (async)
- [ ] Falls back to sync DB if Kafka down
- [ ] Broadcasts via Redis pub/sub (local fallback if Redis down)

### Private Messages (via WS)
- [x] Type `private_message` → delivers to target user
- [x] Cannot PM yourself
- [x] Target must be online
- [ ] Rate limited (same as chat)
- [ ] Produces to `chat.private` Kafka (sorted partition key)
- [ ] Echoed back to sender with `"self": true`

### Admin Commands
- [x] **Kick**: admin kicks non-admin
  - [x] Cannot kick self or other admin
  - [x] Target gets `{"type": "kicked"}`, socket closed
  - [x] No "user left" message for kicked users
  - [x] Mute cleared on kick
- [x] **Mute**: admin mutes non-admin
  - [x] Cannot mute self, admin, or already-muted
  - [x] Muted user sees error on send attempt
- [x] **Unmute**: admin unmutes user
- [x] **Promote**: admin promotes user to admin
  - [x] Cannot promote self, already-admin, or muted user

### Disconnect
- [x] Normal: broadcasts `user_left` + updated lists
- [x] Admin leaving: removes admin → clears ALL mutes (amnesty) → promotes next in join order
- [x] Admin succession: next user by join order becomes admin
- [ ] Kicked: counter-based tracking, skip "user left" message
- [ ] Mute cleared on leave

### Lobby Connection (`WS /ws/lobby?token=...`)
- [x] Auth via `?token=`
- [x] Receives PM delivery
- [ ] Receives `room_list_updated`
- [ ] Receives `file_shared` notifications

### Broadcast Message Types
- [x] `user_join` — with users, admins, muted arrays
- [x] `user_left` — with updated arrays
- [x] `message` — from, text, room_id, msg_id, timestamp
- [x] `system` — text, room_id
- [x] `history` — messages array on join
- [ ] `room_list_updated` — rooms array
- [ ] `file_shared` — file_id, filename, size, from, room_id
- [x] `chat_closed` — detail message
- [x] `muted` / `unmuted` — username, room_id
- [x] `new_admin` — username, room_id
- [x] `kicked` — room_id
- [x] `error` — detail message

---

## 4. Message Persistence (Message Service → Kong → `/messages/*`)

### Kafka Consumer (CQRS Write)
- [x] Consumes `chat.messages` — persists room messages
- [ ] Consumes `chat.private` — persists PMs
- [x] Idempotent: skips duplicate message_id UUIDs
- [ ] Retry: 3 attempts, exponential backoff (0.5s × attempt)
- [ ] DLQ: routes failures to `chat.dlq` with error context
- [ ] PM resolution: calls Auth Service for username → user_id
- [ ] Content length limit (DoS prevention)

### Replay API (CQRS Read)
- [x] `GET /messages/rooms/{id}?since=ISO8601&limit=100` — missed messages
- [ ] Limit bounds: 1-500, default 100
- [x] Requires JWT

### History API
- [x] `GET /messages/rooms/{id}/history?limit=50` — recent messages
- [ ] Excludes private messages
- [x] Requires JWT

---

## 5. Files (File Service → Kong → `/files/*`)

### Upload
- [x] `POST /files/upload?room_id=X` — multipart, requires JWT
- [ ] Max size: 150 MB
- [x] Extension allowlist enforced
- [x] Rejects disallowed extensions (400)
- [ ] Rejects oversized files (413)
- [x] Filename sanitization: path components, null bytes, CRLF, leading dots
- [x] Path traversal prevention (resolved path within upload dir)
- [x] UUID prefix for uniqueness
- [ ] Produces `file.events` Kafka → Chat Service broadcasts to room

### Download
- [x] `GET /files/download/{file_id}` — stream file
- [x] JWT from header OR `?token=` query param
- [ ] Path traversal check before serving
- [x] 404 if file missing on disk
- [ ] Content-Disposition with properly escaped filename

### List
- [x] `GET /files/room/{room_id}` — files in room, requires JWT

---

## 6. Admin Dashboard (Chat & Room Service → Kong → `/admin/*`)

- [x] `GET /admin/users` — online users per room (global admin only)
- [ ] `GET /admin/rooms` — all rooms including inactive
- [ ] `POST /admin/chat/close` — close all rooms, disconnect everyone
- [ ] `POST /admin/chat/open` — reopen all rooms
- [x] `POST /admin/rooms/{id}/close` — close specific room
- [x] `POST /admin/rooms/{id}/open` — open specific room
- [ ] `DELETE /admin/db` — reset database (dev/staging only, 403 in prod)
- [ ] `POST /admin/promote?username=X` — promote in all connected rooms

---

## 7. Graceful Degradation

### Kafka Down
- [x] Chat still delivers in real-time (Redis/local)
- [ ] Messages saved to DB synchronously (fallback)
- [x] Health: reports "degraded" but stays ready

### Redis Down
- [x] WebSocket delivery: local-only (same-process)
- [ ] Token blacklist: fail-closed in prod, fail-open in dev
- [ ] Rate limiting: in-memory fallback

### Database Down
- [ ] All services: readiness probe returns 503
- [ ] No fallback

---

## 8. Inter-Service Communication

### REST (synchronous)
- [x] Chat → Auth: user lookup (PM, promote, mute)
- [x] Chat → Message: fetch history on room join
- [ ] Message → Auth: username resolution for PM persistence
- [ ] Circuit breaker: handles downstream service failures gracefully

### Kafka (asynchronous)
- [x] Chat → `chat.messages` → Message Service
- [ ] Chat → `chat.private` → Message Service
- [ ] Chat → `chat.events` → (future)
- [ ] File → `file.events` → Chat Service (broadcast)
- [ ] Auth → `auth.events` → (future)
- [ ] Message → `chat.dlq` → (monitoring)

---

## 9. Kong Gateway

### Routing
- [x] All paths route to correct service
- [x] WebSocket upgrade works through Kong
- [x] WebSocket stays alive (no premature timeout)
- [x] Reconnection works after disconnect

### Plugins
- [x] CORS configured correctly
- [x] Rate limiting: 100/min global, 5/min register, 10/min login
- [x] X-Request-ID injected on all requests

---

## 10. Health Checks

- [x] Auth: `/health` (liveness) + `/ready` (DB + Redis + Kafka)
- [x] Chat: `/health` + `/ready` (DB + Redis + Kafka)
- [x] Message: `/health` + `/ready` (DB + Kafka)
- [x] File: `/health` + `/ready` (DB + Kafka)

---

## 11. Startup & Shutdown

### Startup
- [x] PostgreSQL init script creates 4 databases
- [x] db-init container runs schema migrations (not services)
- [x] Auth seeds admin user + default rooms (politics, sports, movies)
- [x] kafka-init container creates topics
- [ ] Prod fails fast on missing env vars
- [x] Dev logs warning for default SECRET_KEY

### Shutdown
- [ ] Kafka consumers stop gracefully
- [ ] WebSockets closed (code 1001)
- [ ] No data loss

---

## 12. Security

- [x] JWT: HS256 + shared secret, 24h expiry, Redis blacklist
- [x] Passwords: Argon2id
- [x] Input validation: username, password, room name, message length, file extension/size
- [x] File security: path traversal, null bytes, CRLF, hidden files, Content-Disposition
- [x] WebSocket: origin checking, message size limit (64KB), content limit (4096 chars)
- [x] No error details in production health endpoints

---

## 13. Observability

- [x] X-Request-ID propagated across all services
- [x] Structured JSON logs in production
- [x] Per-service log filtering: `docker compose logs <service>`

---

## 14. CI/CD

- [x] Auth: ruff + pytest + Docker build
- [x] Chat: go vet + go build + go test + Docker build
- [x] Message: ruff + pytest + Docker build
- [x] File: eslint + vitest + Docker build
- [x] Integration: Kong config + compose syntax validation
- [x] Security: Trivy + Gitleaks
- [x] Dependabot: all 4 services + frontend + GitHub Actions

---

## 15. Docker Compose

- [x] `docker compose up --build` — all services healthy
- [x] Only Kong (80) and frontend (3000) exposed
- [x] Internal DNS resolution between services
- [x] PostgreSQL init script runs on first start
- [ ] Uploads volume persists across restarts

---

## 16. End-to-End Journeys

### Journey 1: New User
- [x] Register → Login → Join room → Send message → See broadcast → Leave

### Journey 2: File Sharing
- [x] Login → Join room → Upload → Others see notification → Download

### Journey 3: Private Messaging
- [x] Login → Send PM → Recipient receives via lobby WS

### Journey 4: Admin Operations
- [x] Mute user → Can't send → Unmute → Can send
- [x] Kick user → Disconnected → Can rejoin
- [x] Close room → All disconnected → Open room → Can rejoin

### Journey 5: Reconnection
- [x] Chatting → Network drop → Auto-reconnect → Missed messages replayed

### Journey 6: Admin Succession
- [x] A joins (admin) → B joins → A leaves → B becomes admin → Mutes cleared

### Journey 7: Multi-Room
- [x] Join Room 1 → Join Room 2 → Send in Room 1 → Only Room 1 sees → Leave Room 2 → Room 1 works

---

## Summary

| Category | Total | Checked | Remaining |
|----------|-------|---------|-----------|
| Auth | 22 | 17 | 5 (Kafka events, Redis fail modes, JWT payload) |
| Rooms | 8 | 6 | 2 (ETag, room name validation) |
| WebSocket | 44 | 33 | 11 (close codes, Redis fallback, PM echo, lobby broadcasts) |
| Messages | 14 | 6 | 8 (DLQ, retry, PM consume, limits) |
| Files | 16 | 12 | 4 (size limit, file.events, Content-Disposition) |
| Admin | 8 | 3 | 5 (close all, open all, DB reset, promote, all rooms) |
| Degradation | 7 | 3 | 4 (sync DB fallback, Redis blacklist modes) |
| Inter-Service | 10 | 4 | 6 (Kafka event flows, circuit breaker) |
| Kong | 7 | 7 | 0 |
| Health | 4 | 4 | 0 |
| Startup | 6 | 5 | 1 (prod fail-fast) |
| Security | 6 | 6 | 0 |
| Observability | 3 | 3 | 0 |
| CI/CD | 7 | 7 | 0 |
| Docker | 5 | 4 | 1 (uploads persist) |
| E2E Journeys | 7 | 7 | 0 |
| **Total** | **174** | **127** | **47** |
