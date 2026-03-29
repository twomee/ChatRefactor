# Phase 1: Auth Service Security Audit

**Service:** Auth Service (Python/FastAPI, port 8001)
**Date:** 2026-03-28
**Auditor:** Claude Code
**Scope:** OWASP Top 10 code-level review

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 4 |
| LOW      | 2 |
| INFO     | 3 |

---

## Findings

### [HIGH] AUTH-01: Insecure SECRET_KEY allowed in production

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `services/auth-service/app/main.py:54-65`
- **Description:** When SECRET_KEY contains the default value `"change-this-in-production"`, the startup check logs an error but does NOT exit the process. The service continues running with a publicly known signing key (the default is committed in `.env.example`).
- **Root cause:** `config.py:37-38` validates that SECRET_KEY is non-empty in prod (via `_require_env`), but the main.py insecure-default check only logs — it doesn't call `sys.exit(1)`.
- **Impact:** If production is deployed with the `.env.example` default, any attacker who reads the public repo can forge valid JWT tokens for any user, including admin accounts.
- **Evidence:**
  ```python
  # main.py:54-65 — logs error but continues
  if SECRET_KEY and "change-this-in-production" in SECRET_KEY:
      if APP_ENV in ("staging", "prod"):
          logger.error("INSECURE_SECRET_KEY", ...)  # no sys.exit!
  ```
- **Recommendation:** Exit the process in staging/prod if the SECRET_KEY contains the default value. Same for ADMIN_PASSWORD.

---

### [MEDIUM] AUTH-02: DATABASE_URL production guard is dead code

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `services/auth-service/app/core/config.py:39-48`
- **Description:** `os.getenv("DATABASE_URL", "postgresql://chatbox:chatbox_pass@localhost:5432/chatbox_auth")` always returns a non-empty string (the hardcoded default). The subsequent guard `if not DATABASE_URL and APP_ENV == "prod": sys.exit(1)` never triggers because DATABASE_URL is never falsy.
- **Impact:** In production without the DATABASE_URL env var, the service silently uses hardcoded credentials pointing to localhost (which would fail to connect in Docker, but the fail-fast intent is defeated).
- **Evidence:**
  ```python
  DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://chatbox:chatbox_pass@localhost:5432/chatbox_auth")
  if not DATABASE_URL and APP_ENV == "prod":  # DEAD CODE — DATABASE_URL is always truthy
      sys.exit(1)
  ```
- **Recommendation:** Use `_require_env("DATABASE_URL")` for consistency, or remove the default from `os.getenv`.

---

### [MEDIUM] AUTH-03: FastAPI docs endpoints exposed in production

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `services/auth-service/app/main.py:124`
- **Description:** FastAPI's interactive API documentation (`/docs` and `/redoc`) is enabled by default and not disabled in production. These endpoints expose the full API schema including all endpoints, parameter types, and response models.
- **Impact:** Attackers can discover the full API surface, parameter names, and data types without any authentication. The internal endpoints (`/auth/users/{id}`) are also documented even though Kong blocks them externally.
- **Evidence:**
  ```python
  app = FastAPI(title="cHATBOX Auth Service", version="1.0.0", lifespan=lifespan)
  # No docs_url=None or redoc_url=None in production
  ```
- **Recommendation:** Disable docs in non-dev environments: `docs_url="/docs" if APP_ENV == "dev" else None`.

---

### [MEDIUM] AUTH-04: Readiness endpoint leaks infrastructure error details

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `services/auth-service/app/main.py:162-172`
- **Description:** The `/ready` endpoint returns raw exception strings when database or Redis checks fail: `checks["database"] = str(e)`. These error messages can contain hostnames, port numbers, connection string fragments, and library-specific details.
- **Impact:** Information disclosure helps attackers fingerprint the database type, version, hostname, and network topology.
- **Evidence:**
  ```python
  except Exception as e:
      checks["database"] = str(e)  # Leaks "could not connect to server: Connection refused... Is the server running on host "postgres" (172.18.0.2) and accepting..."
  ```
- **Recommendation:** Return a generic error string: `checks["database"] = "unavailable"`.

---

### [MEDIUM] AUTH-05: Login timing side-channel enables username enumeration

- **OWASP Category:** A04 - Insecure Design
- **File:** `services/auth-service/app/services/auth_service.py:60-64`
- **Description:** When a username doesn't exist, the login flow skips the Argon2id `verify_password` call. Argon2id is deliberately slow (~100ms with default parameters), creating a measurable timing difference between "user not found" (~1ms) and "wrong password" (~100ms).
- **Impact:** An attacker can enumerate valid usernames by measuring response times to the `/auth/login` endpoint. Kong rate limiting (10/min) slows this but doesn't prevent it over time.
- **Evidence:**
  ```python
  user = user_dal.get_by_username(db, body.username)
  if not user or not verify_password(body.password, user.password_hash):
      # If user is None, verify_password is never called (short-circuit eval)
  ```
- **Recommendation:** Always run a dummy `verify_password` against a pre-computed hash when the user doesn't exist, to equalize response timing.

---

### [LOW] AUTH-06: 24-hour token expiry with no refresh mechanism

- **OWASP Category:** A02 - Cryptographic Failures
- **File:** `services/auth-service/app/core/config.py:54`
- **Description:** Access tokens are valid for 24 hours with no refresh token mechanism. A stolen token remains valid until natural expiry, even after logout (other services don't check the Redis blacklist).
- **Impact:** Long token lifetime increases the window of opportunity for token theft exploitation.
- **Recommendation:** Consider shorter token expiry (e.g., 1 hour) with a refresh token mechanism, or propagate blacklist checks to all services.

---

### [LOW] AUTH-07: Account enumeration via registration 409 response

- **OWASP Category:** A04 - Insecure Design
- **File:** `services/auth-service/app/services/auth_service.py:37-39`
- **Description:** Registration returns HTTP 409 with "Username already taken" when a duplicate username is submitted. This confirms the existence of valid usernames.
- **Impact:** Attacker can enumerate valid usernames via the registration endpoint. Mitigated by Kong rate limiting (5/min on `/auth/register`).
- **Recommendation:** Consider returning a generic success message ("If the username is available, an account has been created") to avoid confirming username existence. Trade-off: worse UX for legitimate users.

---

### [INFO] AUTH-08: Failed login logging lacks client IP address

- **OWASP Category:** A09 - Security Logging and Monitoring Failures
- **File:** `services/auth-service/app/services/auth_service.py:62`
- **Description:** Failed login events are logged with `username` but not the client's IP address. For brute-force detection and incident response, the source IP is essential.
- **Recommendation:** Pass the `Request` object to the service layer and log `request.client.host`.

---

### [INFO] AUTH-09: Internal user lookup endpoints have no authentication

- **OWASP Category:** A01 - Broken Access Control
- **File:** `services/auth-service/app/routers/auth.py:64-79`
- **Description:** `/auth/users/{user_id}` and `/auth/users/by-username/{username}` have no authentication. Kong blocks external access (no routes defined), so they're only reachable from the Docker network.
- **Impact:** Any compromised service on the Docker network can enumerate all users. This is acceptable for inter-service communication but worth documenting.
- **Recommendation:** Consider adding a shared internal API key header for service-to-service calls.

---

### [INFO] AUTH-10: No `iat` claim in JWT tokens

- **OWASP Category:** A02 - Cryptographic Failures
- **File:** `services/auth-service/app/core/security.py:44-50`
- **Description:** JWT tokens contain `sub`, `username`, and `exp` claims but no `iat` (issued at). This makes it harder to audit token usage patterns or implement token rotation policies.
- **Recommendation:** Add `payload["iat"] = datetime.now(timezone.utc)` to `create_access_token`.

---

## Positive Findings

These security controls are correctly implemented:

1. **Argon2id password hashing** (`security.py:26`) with default parameters exceeding OWASP minimums (64 MiB memory, 3 iterations)
2. **JWT algorithm pinning** (`security.py:65`) uses `algorithms=[ALGORITHM]` list form, preventing algorithm confusion
3. **Redis blacklist** with fail-closed behavior in production (`security.py:74`)
4. **Username input validation** (`schemas/auth.py:28-44`) with strict regex `^[a-zA-Z0-9_-]+$`
5. **Password length bounds** (`schemas/auth.py:46-57`) with max 128 chars preventing Argon2 DoS
6. **SQLAlchemy ORM parameterized queries** in `user_dal.py` — no raw SQL
7. **Non-root Docker container** (`Dockerfile:5,28`)
8. **Global exception handler** (`main.py:193-202`) returns generic error, logs details server-side
9. **Structured log redaction** (`logging.py:16-25`) for password, token, secret, authorization keys
10. **Kong blocks internal endpoints** — `/auth/users/*` has no Kong route
11. **Logout returns 503 in prod** when Redis is down (`auth_service.py:103-107`) — prevents silent blacklist failure
