# Phase 2: Chat Service Security Audit

**Service:** Chat Service (Go/Gin, port 8003)
**Date:** 2026-03-28
**Auditor:** Claude Code
**Scope:** OWASP Top 10 code-level review

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 3 |
| MEDIUM   | 3 |
| LOW      | 1 |
| INFO     | 2 |

---

## Findings

### [HIGH] CHAT-01: Missing authorization on AddAdmin REST endpoint

- **OWASP Category:** A01 - Broken Access Control
- **File:** `services/chat-service/internal/handler/room.go:163-185`
- **Description:** `AddAdmin` (POST `/rooms/:id/admins`) has NO authorization check. Any authenticated user can appoint themselves or anyone else as a room admin via the REST API. Compare with the WebSocket `handlePromote` in `ws_admin.go:217-275` which correctly verifies `IsAdmin` before promoting.
- **Impact:** Any authenticated user can escalate to room admin, gaining ability to kick, mute, and promote other users.
- **Evidence:**
  ```go
  func (h *RoomHandler) AddAdmin(c *gin.Context) {
      // NO authorization check — jumps straight to store.AddAdmin
      admin, err := h.store.AddAdmin(c.Request.Context(), roomID, req.UserID)
  ```
- **Recommendation:** Add room admin or global admin check before `store.AddAdmin`, matching the pattern used in `MuteUser`.

---

### [HIGH] CHAT-02: Missing authorization on SetActive REST endpoint

- **OWASP Category:** A01 - Broken Access Control
- **File:** `services/chat-service/internal/handler/room.go:130-159`
- **Description:** `SetActive` (PUT `/rooms/:id/active`) has NO authorization check. Any authenticated user can toggle any room's active status. Compare with the admin handler's `CloseRoom`/`OpenRoom` in `admin.go:199-266` which correctly calls `requireGlobalAdmin`.
- **Impact:** Any authenticated user can deactivate any room, effectively performing a denial of service by kicking all connected users from a room.
- **Evidence:**
  ```go
  func (h *RoomHandler) SetActive(c *gin.Context) {
      // NO admin check — any authenticated user can deactivate any room
      if err := h.store.SetActive(c.Request.Context(), roomID, req.IsActive); err != nil {
  ```
- **Recommendation:** Add room admin or global admin check before `store.SetActive`.

---

### [HIGH] CHAT-03: Missing authorization on RemoveAdmin REST endpoint

- **OWASP Category:** A01 - Broken Access Control
- **File:** `services/chat-service/internal/handler/room.go:187-211`
- **Description:** `RemoveAdmin` (DELETE `/rooms/:id/admins/:userId`) has NO authorization check. Any authenticated user can demote any room admin.
- **Impact:** An attacker can remove all room admins, leaving the room unmoderated, then join to trigger auto-promotion (CHAT-05).
- **Evidence:**
  ```go
  func (h *RoomHandler) RemoveAdmin(c *gin.Context) {
      // NO authorization check
      if err := h.store.RemoveAdmin(c.Request.Context(), roomID, userID); err != nil {
  ```
- **Recommendation:** Add room admin or global admin check before `store.RemoveAdmin`.

---

### [MEDIUM] CHAT-04: No Redis blacklist check for JWT validation

- **OWASP Category:** A07 - Identification and Authentication Failures
- **File:** `services/chat-service/internal/middleware/auth.go`
- **Description:** JWT validation checks signature and expiry but does NOT check the Redis token blacklist. A user who logged out via `/auth/logout` (token blacklisted in Redis) can still send messages and call REST APIs on the chat service for up to 24 hours.
- **Impact:** Logged-out user tokens remain valid for all chat operations until natural JWT expiry.
- **Recommendation:** Add Redis blacklist check to `parseToken` or the `JWTAuth` middleware. Fail-closed in production, fail-open in dev.

---

### [MEDIUM] CHAT-05: Auto-admin promotion when room has no connected admins

- **OWASP Category:** A04 - Insecure Design
- **File:** `services/chat-service/internal/handler/websocket.go:228-245`
- **Description:** When no admin is connected to a room, the first user to join is auto-promoted to admin AND all previous admin records are cleared. An attacker can: (1) wait for all admins to disconnect, (2) join the room, (3) become admin, (4) kick/mute all legitimate users.
- **Impact:** Unauthorized privilege escalation to room admin by timing.
- **Evidence:**
  ```go
  if !hasConnectedAdmin {
      for _, a := range admins {
          _ = h.store.RemoveAdmin(ctx, roomID, a.UserID)  // clears ALL admins
      }
      _, _ = h.store.AddAdmin(ctx, roomID, userID)  // promotes first joiner
  }
  ```
- **Recommendation:** Only auto-promote if the room has ZERO admin records in the database (not just zero connected admins). Preserve existing admin records even when they're offline.

---

### [MEDIUM] CHAT-06: WebSocket origin check fails open in production

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `services/chat-service/internal/handler/websocket.go:79-81`
- **Description:** In production, if the `ALLOWED_ORIGINS` environment variable is not set, `checkOrigin` returns `true` for all origins. This should fail-closed (deny all) when not configured.
- **Impact:** Cross-site WebSocket hijacking if production deployment omits ALLOWED_ORIGINS.
- **Evidence:**
  ```go
  allowed := os.Getenv("ALLOWED_ORIGINS")
  if allowed == "" {
      return true // FAILS OPEN — should fail closed
  }
  ```
- **Recommendation:** Return `false` when `ALLOWED_ORIGINS` is empty in production mode, and log a warning on startup.

---

### [LOW] CHAT-07: Metrics endpoint exposed without authentication

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `services/chat-service/cmd/server/main.go`
- **Description:** The `/metrics` Prometheus endpoint is accessible without authentication. While Kong doesn't expose it externally, any container on the Docker network can scrape it.
- **Impact:** Information disclosure of internal metrics (connection counts, error rates, latencies) to other containers on the network.
- **Recommendation:** Acceptable in current architecture (Kong blocks external access). In K8s, ensure NetworkPolicy restricts access to the monitoring namespace.

---

### [INFO] CHAT-08: Auth client correctly uses url.PathEscape (SSRF mitigated)

- **OWASP Category:** A10 - SSRF
- **File:** `services/chat-service/internal/client/auth.go:82`
- **Description:** The `GetUserByUsername` method uses `url.PathEscape(username)` to encode the username in the URL path. Path traversal characters like `../` are properly encoded.
- **Status:** No vulnerability — SSRF risk is mitigated.

---

### [INFO] CHAT-09: JWT algorithm correctly pinned to HMAC

- **OWASP Category:** A02 - Cryptographic Failures
- **File:** `services/chat-service/internal/middleware/auth.go:69`
- **Description:** `t.Method.(*jwt.SigningMethodHMAC)` correctly rejects non-HMAC signing methods, preventing algorithm confusion attacks.
- **Status:** No vulnerability.

---

## Positive Findings

1. **WebSocket message size limit** (64KB) prevents memory exhaustion
2. **Per-user connection limit** (5 max) prevents resource exhaustion
3. **Ping/pong heartbeat** with read deadline detects dead connections
4. **Per-user message rate limiting** (30/10s window) prevents spam
5. **Message content length limit** (4096 chars) prevents oversized payloads
6. **Circuit breaker** on auth service client prevents cascading failures
7. **Admin actions** (kick, mute, unmute, promote) correctly check `IsAdmin` via WebSocket
8. **ResetDatabase** requires global admin AND non-prod APP_ENV
9. **Room name regex** `^[a-zA-Z0-9 _-]+$` prevents injection via room names
10. **User existence check** during WS upgrade prevents ghost connections from deleted users
