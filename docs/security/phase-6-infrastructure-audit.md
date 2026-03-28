# Phase 6: Infrastructure Security Audit

**Scope:** Kong API Gateway, Docker Compose, Kafka, Redis, PostgreSQL, K8s configs
**Date:** 2026-03-28
**Auditor:** Claude Code
**Scope:** OWASP Top 10 code-level review

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 3 |
| LOW      | 4 |
| INFO     | 3 |

---

## Findings

### [MEDIUM] INFRA-01: K8s secrets YAML contains placeholder values in git

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `infra/k8s/base/shared-config/secrets.yaml:10-13`
- **Description:** The Kubernetes secret manifest contains `stringData` with `CHANGE_ME` placeholder values and is committed to git. While these are not real secrets, the pattern encourages developers to replace values in-place and accidentally commit real secrets. The `generate-secrets.sh` script creates secrets dynamically, but the static YAML is still checked in.
- **Impact:** Risk of accidental secret exposure if developers edit the YAML directly instead of using `generate-secrets.sh`.
- **Evidence:**
  ```yaml
  stringData:
    POSTGRES_PASSWORD: "CHANGE_ME"
    REDIS_PASSWORD: "CHANGE_ME"
    SECRET_KEY: "CHANGE_ME"
  ```
- **Recommendation:** Use `SealedSecrets` or `ExternalSecrets` operator. At minimum, replace the YAML with a comment pointing to `generate-secrets.sh`. Add a pre-commit hook to block commits containing the secrets YAML with non-placeholder values.

---

### [MEDIUM] INFRA-02: Kafka uses PLAINTEXT protocol with no authentication

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `docker-compose.yml:36-38`
- **Description:** Kafka listeners use `PLAINTEXT` protocol with no SASL authentication. Any container on the Docker network can read from or write to any Kafka topic, including injecting forged messages into `message.created` or reading messages from the DLQ.
- **Impact:** A compromised container can forge chat messages (appearing as any user), read all chat history from Kafka topics, or inject malicious file_shared events.
- **Evidence:**
  ```yaml
  KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
  KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
  ```
- **Recommendation:** Enable SASL/SCRAM authentication. This is documented as P7 tech debt.

---

### [MEDIUM] INFRA-03: Redis password visible in Docker healthcheck

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `docker-compose.yml:25`
- **Description:** The Redis healthcheck passes the password as a CLI argument: `redis-cli -a ${REDIS_PASSWORD} ping`. This is visible in `docker inspect` output and process listings, and may appear in Docker daemon logs.
- **Impact:** Redis password exposure to anyone with Docker CLI access on the host.
- **Evidence:**
  ```yaml
  test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
  ```
- **Recommendation:** Use `REDISCLI_AUTH` environment variable instead:
  ```yaml
  test: ["CMD-SHELL", "REDISCLI_AUTH=${REDIS_PASSWORD} redis-cli ping"]
  ```

---

### [LOW] INFRA-04: CORS origins hardcoded in Kong config

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `infra/kong/kong.yml:10-12`
- **Description:** CORS origins are hardcoded to `localhost:3000` and `localhost:5173`. Kong's declarative config format (v3.0) does not support environment variable interpolation, so production deployments must manually edit this file. Documented as P1 tech debt.
- **Impact:** Production deployments require manual config modification.
- **Recommendation:** Use a templating step (envsubst, sed, or Kong's admin API in database mode) to inject production origins at deployment time.

---

### [LOW] INFRA-05: Single shared SECRET_KEY across all services

- **OWASP Category:** A02 - Cryptographic Failures
- **File:** `docker-compose.yml:122,149,174,196`
- **Description:** All four services share the same `SECRET_KEY` for JWT signing and validation. Key compromise in any service compromises all services. No key rotation mechanism exists.
- **Impact:** Lateral movement — compromising any service's memory or config exposes the JWT signing key for the entire system.
- **Recommendation:** Acceptable for current architecture (symmetric JWT). For improved security, consider asymmetric JWT (RS256) where only the auth service holds the private key and other services use the public key.

---

### [LOW] INFRA-06: Shared PostgreSQL user across all databases

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `docker-compose.yml:119,146,172,194`
- **Description:** All services connect to their respective databases using the same `chatbox` PostgreSQL user and password. A compromised service can access any other service's database.
- **Impact:** Violates database-per-service isolation. The auth service database (containing password hashes) is accessible from a compromised file service.
- **Recommendation:** Create per-service database users in `init-db.sh` with access limited to their respective databases.

---

### [LOW] INFRA-07: Docker images not pinned by digest

- **OWASP Category:** A08 - Software and Data Integrity Failures
- **File:** `docker-compose.yml:8,22,31,81`
- **Description:** Infrastructure images use tag-based references (e.g., `postgres:16-alpine`, `redis:7-alpine`) rather than digest-pinned references (e.g., `postgres:16-alpine@sha256:abc...`). A compromised registry could serve malicious images with the same tag.
- **Impact:** Supply chain attack vector. Low probability but high impact.
- **Recommendation:** Pin images by digest in production. Use Dependabot/Renovate to automate digest updates.

---

### [INFO] INFRA-08: Kong admin API correctly disabled

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `docker-compose.yml:86`
- **Description:** `KONG_ADMIN_LISTEN: "off"` prevents management API access. This is correct — Kong uses declarative config.
- **Status:** No vulnerability.

---

### [INFO] INFRA-09: Kong route allow-list correctly implemented

- **OWASP Category:** A01 - Broken Access Control
- **File:** `infra/kong/kong.yml:64-206`
- **Description:** Only public endpoints are exposed through Kong. Internal endpoints (`/auth/users/*`, `/health`, `/ready`, `/metrics`) have no Kong routes and are unreachable externally. Each route has explicit path and method restrictions.
- **Status:** No vulnerability — well-implemented allow-list approach.

---

### [INFO] INFRA-10: Docker Compose enforces required environment variables

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `docker-compose.yml:11,23,61,119-124`
- **Description:** Required secrets use `${VAR:?message}` syntax which causes Docker Compose to fail immediately if the variable is not set. This prevents deployment with missing secrets.
- **Status:** No vulnerability — correct fail-fast behavior.

---

## Positive Findings

1. **Kong admin API disabled** (`KONG_ADMIN_LISTEN: "off"`)
2. **Kong allow-list routing** — only public endpoints exposed
3. **Docker Compose fail-fast** on missing env vars (`${VAR:?msg}`)
4. **Redis authentication** enabled (`--requirepass`)
5. **Non-root containers** — all service Dockerfiles use `USER appuser`
6. **Health checks** — all services have liveness probes
7. **Rate limiting** — per-endpoint rate limits configured in Kong
8. **Security headers** — set at both Kong (global) and Nginx (frontend) levels
9. **Generate-secrets.sh** — proper dynamic secret generation for K8s
10. **Init container pattern** — database schemas created idempotently
