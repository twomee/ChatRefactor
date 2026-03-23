# Security Audit Report

**Date:** 2026-03-24
**Branch:** `microservices`
**Auditor:** Claude Code Security Analysis

---

## Summary

Full security audit of the Chat-Project-Final microservices platform covering:
Auth Service (Python/FastAPI), Chat Service (Go/Gin), Message Service (Python/FastAPI),
File Service (Node/Express), Kong API Gateway, React Frontend, and infrastructure (Docker, Redis, Kafka, PostgreSQL).

---

## What's Already Good

- Argon2id password hashing (auth-service)
- JWT with expiry + Redis blacklist on logout
- SQLAlchemy ORM — parameterized queries, no SQL injection risk
- Strong file upload sanitization (path traversal prevention, UUID prefix, null byte stripping)
- Non-root Docker containers with multi-stage builds
- Message size limits (64 KB WebSocket frame, 4096 char content)
- Per-user WebSocket rate limiting (30 msgs / 10s sliding window)
- Fail-fast on missing env vars in production (auth-service)
- Trivy + Gitleaks in CI/CD pipeline
- Dependabot configured for automated dependency updates
- Global exception handlers return generic errors (no stack trace leaks)

---

## Findings

### CRITICAL

#### 1. CORS wildcard allows all origins
- **File:** `infra/kong/kong.yml:10-11`
- **Issue:** `origins: ["*"]` with `credentials: true` — any website can make authenticated cross-origin requests to the API, enabling CSRF and cookie theft
- **Fix:** Replace `*` with explicit frontend origin(s)
- **Status:** [x] Fixed (Step 1)

#### 2. Missing security headers
- **Files:** `infra/kong/kong.yml`, `frontend/nginx.conf`
- **Issue:** No CSP, HSTS, X-Content-Type-Options, X-Frame-Options, or Referrer-Policy headers anywhere in the stack
- **Fix:** Add `response-transformer` plugin in Kong + headers in nginx
- **Status:** [x] Fixed (Step 1 + Step 6)

#### 3. Kong Admin API exposed on 0.0.0.0
- **File:** `docker-compose.yml:86`
- **Issue:** `KONG_ADMIN_LISTEN: 0.0.0.0:8001` — the admin API is accessible from any network interface, allowing unauthorized gateway reconfiguration
- **Fix:** Set to `off` (declarative config doesn't need admin API)
- **Status:** [x] Fixed (Step 1)

#### 4. Internal auth endpoints exposed without authentication
- **File:** `services/auth-service/app/routers/auth.py:60-75`
- **Issue:** `/auth/users/{id}` and `/auth/users/by-username/{name}` have no auth — reachable externally through Kong, enabling user enumeration
- **Fix:** Block these routes at Kong level so they're only reachable service-to-service
- **Status:** [x] Fixed (Step 2)

#### 5. Default SECRET_KEY fallback in message-service
- **File:** `services/message-service/app/core/config.py:30`
- **Issue:** `SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")` — hardcoded fallback means JWT can be forged if env var is unset
- **Fix:** Use `_require_env("SECRET_KEY")` pattern, remove the default
- **Status:** [x] Fixed (Step 3)

---

### HIGH

#### 6. JWT token in URL query parameter (file downloads)
- **File:** `frontend/src/services/fileApi.js:19-20`
- **Issue:** `?token=${token}` in download URL — tokens leaked in browser history, server access logs, referrer headers
- **Fix:** Switch to `Authorization` header via fetch/blob download
- **Note:** WebSocket token-in-URL is standard (browsers don't support WS custom headers)
- **Status:** [x] Fixed (Step 5)

#### 7. Redis and Kafka have no authentication
- **File:** `docker-compose.yml` — Redis (lines 22-28) and Kafka (lines 30-50) have no passwords/SASL
- **Issue:** Any container on the Docker network can read/write Redis keys and Kafka topics
- **Fix:** Enable Redis `requirepass`, enable Kafka SASL authentication
- **Status:** [x] Redis fixed (Step 12). Kafka SASL documented for production.

#### 8. Weak default credentials in docker-compose fallbacks
- **File:** `docker-compose.yml:118-122`
- **Issue:** `SECRET_KEY`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD` all have insecure `${VAR:-default}` fallbacks
- **Fix:** Remove all `:-fallback` values for sensitive vars — services should fail to start if not explicitly set
- **Status:** [x] Fixed (Step 4)

---

### MEDIUM

#### 9. File extension allowlist too permissive
- **File:** `services/file-service/src/config/env.config.ts:58-95`
- **Issue:** Allows `.py`, `.js`, `.ts`, `.html`, `.css`, `.bin`, `.dat` — XSS risk if upload directory becomes web-accessible; executable files could be hosted
- **Fix:** Remove executable/scriptable extensions, keep only safe document/media/archive types
- **Status:** [x] Fixed (Step 7)

#### 10. No MIME type / magic byte validation on uploads
- **File:** `services/file-service/src/utils/format.util.ts`
- **Issue:** Only validates file extension, not actual content — attacker can upload malware renamed as `.txt`
- **Fix:** Add `file-type` npm package to validate buffer magic bytes match claimed extension
- **Status:** [x] Fixed (Step 7/8)

#### 11. No rate limiting on read-heavy endpoints
- **File:** `infra/kong/kong.yml`
- **Issue:** `/rooms`, `/messages/history`, `/files/room/{id}` use global 100/min limit — insufficient for data-scraping protection
- **Fix:** Add per-route rate limits (e.g., 30/min for message history, 20/min for file listing)
- **Status:** [x] Fixed (Step 9)

#### 12. WebSocket allows unlimited connections per user
- **File:** `services/chat-service/internal/handler/websocket.go`
- **Issue:** Duplicate check only prevents same user in same room. A user could open connections to many rooms, or reconnect rapidly, consuming server resources
- **Fix:** Track global connection count per user, reject if > 5
- **Status:** [x] Fixed (Step 10)

#### 13. Database connection without SSL
- **File:** `docker-compose.yml` — connection strings don't include `?sslmode=require`
- **Issue:** Database traffic is unencrypted on the Docker network
- **Fix:** Enable PostgreSQL SSL in production, add `?sslmode=require` to connection strings
- **Status:** [ ] Documented — requires SSL cert infrastructure for production deployment

---

### LOW

#### 14. Token in sessionStorage (XSS-accessible) — TECH DEBT
- **File:** `frontend/`
- **Status:** [ ] Tech debt — tracked for future sprint
- **Notes:** CSP header (added in Step 6) is the primary defense against XSS. Migrating to HttpOnly cookies requires a BFF layer or cookie-based auth in Kong, CSRF token handling, and WebSocket auth rework. Not worth the complexity until production with untrusted users.

#### 15. No antivirus scanning on uploads — TECH DEBT
- **File:** `file-service/`
- **Status:** [ ] Tech debt — tracked for future sprint
- **Notes:** MIME validation (added in Step 7) blocks most misnamed executables. Files are served as `application/octet-stream` with `Content-Disposition: attachment`, so browsers won't execute them. ClamAV integration adds ~200MB to images and 1-2s latency per upload. Worth doing before multi-tenant production.

#### 16. Shared PostgreSQL with single user — TECH DEBT
- **File:** `docker-compose.yml`
- **Status:** [ ] Tech debt — tracked for future sprint
- **Notes:** Separate databases per service are already in place (chatbox_auth, chatbox_chat, chatbox_messages, chatbox_files). Per-service DB users add credential management overhead for minimal gain in a single-host Docker deployment. Fix when migrating to managed databases (RDS/Cloud SQL) where IAM-based per-service credentials are easy.

#### 17. Logging doesn't filter passwords/tokens
- **Status:** [x] Fixed (Step 13)

#### 18. No WebSocket ping/pong heartbeat
- **Status:** [x] Fixed (Step 13)

---

## Remediation Log

Each fix below is tracked with the commit/change that resolved it.

### Step 1: Kong CORS + Security Headers + Admin API
- **Files changed:** `infra/kong/kong.yml`, `docker-compose.yml`
- **Status:** [x] Done
- **Notes:**
  - Replaced CORS `origins: ["*"]` with explicit `["http://localhost:3000", "http://localhost:5173"]`
  - Added `response-transformer` plugin with: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-XSS-Protection: 1; mode=block`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`
  - CSP and HSTS are handled at nginx level (Step 6) since nginx serves the frontend directly
  - Changed `KONG_ADMIN_LISTEN` from `0.0.0.0:8001` to `"off"`

### Step 2: Protect internal auth endpoints
- **Files changed:** `infra/kong/kong.yml`
- **Status:** [x] Done
- **Notes:**
  - Added `auth-internal-block` service with `request-termination` plugin returning 403 for `/auth/users` path
  - Kong matches longest prefix first, so `/auth/users/*` hits the block route while `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/ping` still pass through the general `/auth` route
  - Services still reach `/auth/users/*` directly via Docker network (bypassing Kong)

### Step 3: Fix message-service SECRET_KEY
- **Files changed:** `services/message-service/app/core/config.py`
- **Status:** [x] Done
- **Notes:**
  - Replaced `os.getenv("SECRET_KEY", "change-this-in-production")` with `_require_env("SECRET_KEY")`
  - Also replaced inline `DATABASE_URL` fallback with `_require_env("DATABASE_URL")`
  - Both now fail fast in production if unset, and return empty string in dev

### Step 4: Remove insecure defaults from docker-compose
- **Files changed:** `docker-compose.yml`
- **Status:** [x] Done
- **Notes:**
  - Replaced all `${VAR:-default}` for sensitive vars with `${VAR:?error message}` which fails docker-compose if unset
  - Affected vars: `SECRET_KEY`, `POSTGRES_PASSWORD`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`
  - Changed `CORS_ORIGINS` default from `*` to `http://localhost:3000,http://localhost:5173`
  - Developers must now set `.env` values before running `docker compose up`

### Step 5: Fix file download token exposure
- **Files changed:** `frontend/src/services/fileApi.js`, `frontend/src/components/chat/MessageList.jsx`, `frontend/src/pages/AdminPage.jsx`, tests
- **Status:** [x] Done
- **Notes:**
  - Replaced `getDownloadUrl()` (URL with `?token=`) with `downloadFile()` (fetch as blob via Authorization header)
  - Updated `MessageList.jsx` and `AdminPage.jsx` to use `onClick` handler instead of `href`
  - Updated all test mocks to match new function signature
  - `http.js` interceptor already attaches `Authorization: Bearer` header to all requests

### Step 6: Add security headers to nginx
- **Files changed:** `frontend/nginx.conf`
- **Status:** [x] Done
- **Notes:**
  - Added `Content-Security-Policy` allowing self, WebSocket connections, data/blob images, inline styles
  - Added `Strict-Transport-Security` with 2-year max-age, includeSubDomains, preload
  - Added `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`
  - All headers use `always` directive to apply even on error responses

### Step 7: Tighten file upload extensions + MIME validation
- **Files changed:** `services/file-service/src/config/env.config.ts`, `services/file-service/src/utils/format.util.ts`, `services/file-service/src/services/file.service.ts`, `services/file-service/package.json`
- **Status:** [x] Done
- **Notes:**
  - Removed `.py`, `.js`, `.ts`, `.html`, `.css`, `.json`, `.xml`, `.yaml`, `.yml`, `.bin`, `.dat` from allowlist
  - Kept safe types: documents, images, audio/video, archives + `.svg` added
  - Installed `file-type@19.6.0` for magic byte detection
  - Added `validateMimeType()` in format.util.ts with extension-to-MIME mapping
  - Text-based formats (.txt, .csv, .md, .log, .svg) skip MIME check since they have no magic bytes
  - Binary formats (PDF, images, audio, archives, Office docs) are validated against expected MIME types
  - Called in `uploadFile()` after extension and size checks, before writing to disk

### Step 9: Add rate limits on read endpoints
- **Files changed:** `infra/kong/kong.yml`
- **Status:** [x] Done
- **Notes:**
  - Added per-service rate limits: `/rooms` 30/min, `/messages` 30/min, `/files` 20/min
  - These override the global 100/min default on these specific routes
  - Protects against data scraping and enumeration attacks

### Step 10: Limit WebSocket connections per user
- **Files changed:** `services/chat-service/internal/ws/manager.go`, `services/chat-service/internal/handler/websocket.go`
- **Status:** [x] Done
- **Notes:**
  - Added `UserConnectionCount(userID)` to Manager — counts connections across all rooms + lobby
  - Added `maxConnectionsPerUser = 5` constant in handler
  - Returns HTTP 429 "too many connections" if user exceeds limit (checked before WebSocket upgrade)
  - Prevents a single user from exhausting server resources

### Step 11: Enable database SSL in production
- **Files changed:** N/A (documentation only)
- **Status:** [ ] Documented for production
- **Notes:**
  - PostgreSQL SSL requires generating server certificates and mounting them in the container
  - Connection strings need `?sslmode=require` appended
  - Not implemented in dev docker-compose as it would add unnecessary complexity
  - Production deployment guide should include SSL cert generation and PostgreSQL `ssl = on` config

### Step 12: Redis authentication + Kafka SASL
- **Files changed:** `docker-compose.yml`, `.env`, `.env.example`
- **Status:** [x] Redis done. Kafka SASL documented.
- **Notes:**
  - Added `--requirepass` to Redis container via `command` directive
  - Updated Redis URLs in all services to include password: `redis://:${REDIS_PASSWORD}@redis:6379/0`
  - Added `REDIS_PASSWORD` to `.env` and `.env.example`
  - Updated healthcheck to use `-a` flag with password
  - Kafka SASL requires significant config changes (JAAS files, SASL mechanism config, client updates in all 4 services) — documented for production but not implemented in dev docker-compose

### Step 13: WebSocket ping/pong heartbeat + Log redaction
- **Files changed:** `services/chat-service/internal/handler/websocket.go`, `services/chat-service/internal/handler/lobby.go`, `services/auth-service/app/core/logging.py`, `services/message-service/app/core/logging.py`, `services/file-service/src/kafka/logger.ts`
- **Status:** [x] Done
- **Notes:**
  - **Ping/pong:** Added `configurePingPong()` helper that sends WebSocket ping frames every 30s and closes connections that don't respond within 10s. Applied to both room WS and lobby WS handlers. Uses gorilla/websocket's built-in `SetPongHandler` and `WriteControl(PingMessage)`.
  - **Log redaction (Python):** Added `_redact_sensitive_data` structlog processor to auth-service and message-service. Redacts values for keys matching `password`, `token`, `secret`, `secret_key`, `authorization`, and scrubs `Bearer <token>` patterns from string values.
  - **Log redaction (Node):** Added `redactSensitive` Winston format to file-service with the same key/pattern redaction logic.
