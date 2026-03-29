# Phase 5: Frontend Security Audit

**Service:** Frontend (React 19, Vite 8, Nginx)
**Date:** 2026-03-28
**Auditor:** Claude Code
**Scope:** OWASP Top 10 code-level review

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 2 |
| LOW      | 3 |
| INFO     | 2 |

---

## Findings

### [MEDIUM] FE-01: CSP connect-src allows all localhost ports

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `frontend/nginx.conf:6`
- **Description:** The Content-Security-Policy `connect-src` directive allows `http://localhost:*` and `ws://localhost:*`. In production, this should restrict connections to the actual API and WebSocket hostnames.
- **Impact:** In misconfigured production environments using localhost URLs, any local service can be contacted from the frontend. In proper production (behind a domain), this is dead configuration but still bad practice.
- **Evidence:**
  ```nginx
  connect-src 'self' http://localhost:* ws://localhost:*
  ```
- **Recommendation:** Use environment-specific nginx configs. Production should use the actual domain. Consider templating nginx.conf with `envsubst` at Docker build time.

---

### [MEDIUM] FE-02: JSON.parse on WebSocket messages without error handling

- **OWASP Category:** A04 - Insecure Design
- **File:** `frontend/src/hooks/useMultiRoomChat.js:247,363`
- **Description:** `JSON.parse(event.data)` is called on WebSocket messages without try/catch. A malformed message from a compromised or buggy server would throw an uncaught exception, crashing the message handler.
- **Impact:** Denial of service — a single malformed WebSocket message can crash the chat UI.
- **Evidence:**
  ```javascript
  ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);  // throws on malformed JSON
      handleMessageRef.current(msg, roomId);
  };
  ```
- **Recommendation:** Wrap in try/catch and silently drop malformed messages.

---

### [LOW] FE-03: Token stored in sessionStorage

- **OWASP Category:** A02 - Cryptographic Failures
- **File:** `frontend/src/context/AuthContext.jsx:11,27`
- **Description:** The JWT token is stored in `sessionStorage`. While better than localStorage (cleared on tab close), it is accessible to any JavaScript on the same origin. Mitigated by strong CSP (`script-src 'self'`) and no unsafe DOM manipulation.
- **Recommendation:** Acceptable for current threat model. For higher security, consider httpOnly cookies.

---

### [LOW] FE-04: Token in WebSocket URL

- **OWASP Category:** A02 - Cryptographic Failures
- **File:** `frontend/src/hooks/useMultiRoomChat.js:235,354`
- **Description:** WebSocket connections include the JWT in the query string. This is a known limitation — browsers don't support custom headers for WS upgrade. The token appears in server access logs.
- **Recommendation:** Standard approach for WebSocket auth. Ensure server-side logs redact query parameters.

---

### [LOW] FE-05: Client-side admin guard only

- **OWASP Category:** A01 - Broken Access Control
- **File:** `frontend/src/layouts/AdminGuard.jsx:6-9`
- **Description:** Admin page guarded by checking `user?.is_global_admin` from sessionStorage, which can be manipulated. No actual privilege escalation — all admin operations validated server-side.
- **Recommendation:** Acceptable. Server-side authorization is the real guard.

---

### [INFO] FE-06: No XSS via message rendering confirmed

- **OWASP Category:** A03 - Injection
- **File:** `frontend/src/` (all components)
- **Description:** Zero usage of unsafe DOM manipulation patterns. All chat messages rendered via React JSX which auto-escapes HTML entities.
- **Status:** No vulnerability.

---

### [INFO] FE-07: Joined rooms in localStorage leak across sessions

- **OWASP Category:** A04 - Insecure Design
- **File:** `frontend/src/utils/storage.js:3-6`
- **Description:** Joined room IDs stored in localStorage keyed by username. Another user on the same browser can see which rooms the previous user joined. No authentication data exposed.
- **Recommendation:** Low priority. Consider clearing localStorage on logout.

---

## Positive Findings

1. **No XSS vectors** — zero unsafe DOM manipulation patterns in codebase
2. **React auto-escaping** — all user content rendered safely via JSX
3. **CSP script-src 'self'** — blocks inline scripts
4. **HSTS header** — Strict-Transport-Security with 2-year max-age, includeSubDomains, preload
5. **Security headers** — X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy all set
6. **Token in sessionStorage** (not localStorage) — cleared on tab close
7. **Axios interceptor** — Authorization header automatically attached to all API calls
8. **Message deduplication** — prevents duplicate message rendering
9. **Exponential backoff** — WebSocket reconnection uses jittered exponential backoff
10. **Server-side admin verification** — AdminGuard is UX-only; real authorization is server-side
