# Remaining Work — Chat Project

Tracks everything left after the Codex review + PR #144 fixes.
Pick up any item at any time — each section is self-contained.

---

## 1. Security — Deferred Items

These were documented in the security audit but require architectural changes.
They are the highest-value items for making the project interview-ready.

### CHAT-04 — Redis blacklist not enforced by chat-service WebSocket

**What:** When a user logs out, the auth-service blacklists their JWT in Redis.
The file-service and message-service now check that blacklist — but the
**chat-service WebSocket** does not. A logged-out token can still open a
WebSocket connection.

**Where:** `services/chat-service/internal/ws/hub.go` (WebSocket upgrade)
and `services/chat-service/internal/middleware/auth.go` (`CheckBlacklist`
is exported but not called on every message, only at connect time).

**Fix approach:**
- At WebSocket upgrade (`ServeWS`), call `CheckBlacklist` against Redis
  before accepting the connection.
- Optionally re-check on a ticker (e.g., every 60s) while the socket is
  open, so a mid-session logout takes effect without waiting for a reconnect.

**Effort:** Medium (1–2 hours)

---

### MSG-01 — Message search/history has no room membership enforcement

**What:** Any authenticated user can call `GET /messages/rooms/{room_id}/history`
or `GET /messages/search?q=...` and read messages from rooms they never joined.
This is currently documented as a known trade-off.

**Where:** `services/message-service/app/routers/messages.py`

**Fix approach (two options):**

Option A — Kong-level enforcement: add a Kong request transformer plugin or
Lua plugin that calls the chat-service to verify membership before proxying
the request. No code change to message-service.

Option B — Service-to-service call: message-service calls the chat-service
`GET /rooms/{room_id}/members` before returning history. Simple but adds
latency and coupling.

Option B is faster to implement for a portfolio project. Option A is the
production-grade approach.

**Effort:** Medium (2–3 hours)

---

### CHAT-05 — Auto-admin promotion when room has no connected admins

**What:** When the last connected admin leaves a room, the chat-service
auto-promotes another user to room admin. This is a design decision with
security implications (privilege escalation without explicit grant).

**Where:** `services/chat-service/internal/ws/hub.go` or room manager logic.

**Fix approach:** Either document it explicitly as an intentional feature, or
change the behavior so a room without a connected admin simply has no active
admin (read-only moderation until an admin reconnects).

**Effort:** Low (design decision first, then 1 hour to implement)

---

### FE-01 — CSP `connect-src` allows `localhost:*` in production

**What:** The frontend's Content-Security-Policy allows connections to any
localhost port. Fine for development, exposes localhost services in production.

**Where:** `frontend/nginx.conf` or wherever CSP headers are set.

**Fix approach:** Split into two configs — dev (`connect-src localhost:*`) and
prod (`connect-src 'self' wss://your-domain.com`). Use build arg or env var
to switch.

**Effort:** Low (30 minutes)

---

### INFRA-01 — K8s secrets YAML with placeholder values committed to git

**What:** `infra/k8s/` contains secret manifests with `CHANGE_ME` placeholder
values. Pattern encourages developers to edit-in-place and accidentally commit
real secrets.

**Where:** `infra/k8s/base/*/` secret YAML files.

**Fix approach:** Replace static secret YAMLs with a README pointing to
`generate-secrets.sh`. Add a pre-commit hook (gitleaks or a simple grep) that
blocks committing any file in `infra/k8s/` that contains non-placeholder
secret values.

**Effort:** Low (1 hour)

---

### INFRA-02 — Kafka uses PLAINTEXT (no authentication)

**What:** All Kafka producers and consumers connect without SASL/SCRAM.
Messages on the Kafka bus are unauthenticated and unencrypted.

**Where:** `docker-compose.yml` Kafka config, all service Kafka client configs.

**Fix approach:** Enable SASL/SCRAM-SHA-256 on the Kafka broker, update all
service Kafka client configs, and add credentials to `.env`. This is significant
config work across all 4 services.

**Effort:** High (4–6 hours). Lowest priority — acceptable for a portfolio
project if documented.

---

## 2. Features — Half-Baked or Missing

### Email service is a placeholder

**What:** The `forgot-password` endpoint generates a reset token and saves it
to the database but never sends an email. The email service is stubbed out.

**Where:** `services/auth-service/app/services/` (email service file).

**Fix approach:**
- Add `python-sendgrid` or `resend` (simpler API) to auth-service deps.
- Implement the email send in the email service stub.
- Wire `SENDGRID_API_KEY` (or equivalent) into the env config.
- For a portfolio project, Resend has a generous free tier and a simple Python SDK.

**Effort:** Medium (2–3 hours)

---

### Redis pub/sub for WebSocket horizontal scaling

**What:** The chat-service fan-out is in-memory only. Two chat-service instances
cannot share room state — all users in a room must connect to the same instance.

**Where:** `services/chat-service/internal/ws/manager.go`

**Fix approach:**
- When a message arrives, publish to `chat.room.<room_id>` Redis channel.
- Each instance subscribes to the channels for rooms it has active connections.
- Replace direct `broadcastToRoom()` with publish + subscribe loop.

This is already architecturally designed for in the docs. The code structure
in `manager.go` makes it a clean addition rather than a rewrite.

**Effort:** High (4–6 hours). Nice-to-have for a portfolio project — the current
in-memory approach works fine for a single instance and is already documented.

---

## 3. Frontend — Toast / Notification System

**What:** All in-app alerts (kicked from room, room closed, errors) use the
browser's unstyled `globalThis.alert()`. There is no "you are muted" feedback.

A full implementation plan already exists — see the active plan file in
`.claude/plans/parallel-enchanting-quilt.md`.

**Summary of what to build:**
- `frontend/src/context/ToastContext.jsx` — provider + `useToast()` hook
- `frontend/src/components/common/Toast.jsx` — liquid glass toast stack
- Wrap `<App>` in `<ToastProvider>` in `main.jsx`
- Replace `globalThis.alert()` calls in `useMultiRoomChat.js`
- Add "muted" banner above `MessageInput` in `ChatPage.jsx`
- Add CSS to `App.css`

**Effort:** Medium (3–4 hours). High impact for demo/interview purposes.

---

## 4. Infrastructure — Minor Gaps

### Auth-service deployment.yaml has uncommitted changes

The git status at session start showed `infra/k8s/base/auth-service/deployment.yaml`
as modified but not staged. Review and commit or discard.

---

## Priority Order (suggested)

| Priority | Item | Why |
|----------|------|-----|
| 1 | Toast system (frontend) | Most visible in a demo |
| 2 | Email service | Forgot-password is broken end-to-end |
| 3 | CHAT-04 (blacklist on WebSocket) | Closes the last auth bypass |
| 4 | MSG-01 (room membership) | Real data isolation gap |
| 5 | FE-01 (CSP localhost) | Quick win, looks professional |
| 6 | INFRA-01 (K8s secrets) | Pre-commit hook is a good practice signal |
| 7 | CHAT-05 (auto-admin) | Design decision more than a bug |
| 8 | Redis pub/sub | Only matters at scale |
| 9 | INFRA-02 (Kafka auth) | Lowest priority, acceptable as documented debt |
