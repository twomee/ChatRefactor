# Security Audit Report — March 2026

**Project:** Chatbox Microservices
**Date:** 2026-03-28
**Auditor:** Claude Code
**Methodology:** OWASP Top 10 (2021) code-level review, 6 phases

---

## Executive Summary

This audit reviewed all 5 services (Auth, Chat, Message, File, Frontend) plus infrastructure (Kong, Docker, Kafka, Redis, K8s) against the OWASP Top 10. It builds on the previous 13-step remediation (documented in `docs/operations/security-audit.md`) by performing deeper code-level analysis.

**Key findings:** 6 HIGH severity issues, all fixed. The most impactful were missing authorization checks on REST endpoints in the Chat Service, allowing any authenticated user to escalate to room admin.

---

## Findings Summary

| Severity | Count | Fixed | Deferred |
|----------|-------|-------|----------|
| CRITICAL | 0     | —     | —        |
| HIGH     | 6     | 6     | 0        |
| MEDIUM   | 14    | 11    | 3        |
| LOW      | 12    | 0     | 12       |
| INFO     | 10    | —     | —        |
| **Total**| **42**| **17**| **15**   |

---

## HIGH Findings (All Fixed)

| ID | Service | Finding | Fix |
|----|---------|---------|-----|
| AUTH-01 | Auth | Insecure SECRET_KEY allowed in prod (logs error but continues) | Now calls `sys.exit(1)` |
| CHAT-01 | Chat | AddAdmin REST endpoint missing authorization | Added room/global admin check |
| CHAT-02 | Chat | SetActive REST endpoint missing authorization | Added room/global admin check |
| CHAT-03 | Chat | RemoveAdmin REST endpoint missing authorization | Added room/global admin check |
| MSG-02 | Message | python-jose vulnerable to algorithm confusion CVEs | Migrated to PyJWT |
| FILE-01 | File | Loose MIME validation (prefix matching allows type confusion) | Changed to exact MIME matching |

---

## MEDIUM Findings

| ID | Service | Finding | Status |
|----|---------|---------|--------|
| AUTH-02 | Auth | DATABASE_URL prod guard is dead code | Fixed |
| AUTH-03 | Auth | `/docs`/`/redoc` exposed in production | Fixed |
| AUTH-04 | Auth | `/ready` leaks infrastructure error details | Fixed |
| AUTH-05 | Auth | Login timing side-channel (username enumeration) | Fixed |
| CHAT-04 | Chat | No Redis blacklist check (logged-out tokens valid) | Deferred (arch change) |
| CHAT-05 | Chat | Auto-admin promotion when room has no connected admins | Deferred (design decision) |
| CHAT-06 | Chat | WebSocket origin check fails open in production | Fixed |
| MSG-01 | Message | No room membership check on history endpoints | Deferred (needs cross-service) |
| MSG-03 | Message | `/docs`/`/redoc` exposed in production | Fixed |
| MSG-04 | Message | `/ready` leaks infrastructure error details | Fixed |
| MSG-05 | Message | Insecure SECRET_KEY allowed in production | Fixed |
| FILE-02 | File | SVG uploads allowed without content sanitization | Fixed (SVG script scanning) |
| FE-01 | Frontend | CSP connect-src allows `localhost:*` | Deferred (needs prod config) |
| FE-02 | Frontend | JSON.parse on WS messages without try/catch | Fixed |
| INFRA-01 | Infra | K8s secrets YAML with placeholder values in git | Deferred (ops change) |
| INFRA-02 | Infra | Kafka PLAINTEXT with no authentication | Deferred (P7 tech debt) |
| INFRA-03 | Infra | Redis password visible in Docker healthcheck | Fixed |

---

## Prior Audit & Remediation Log

The initial security audit (2026-03-24) and its 13-step remediation log are preserved in [initial-security-audit.md](initial-security-audit.md). That audit covered CORS, security headers, Kong admin API, file upload validation, Redis auth, WebSocket hardening, and log redaction — all of which were fixed before this deeper OWASP audit began.

---

## Phase Reports

| Phase | Service | Report |
|-------|---------|--------|
| 1 | Auth Service | [phase-1-auth-service-audit.md](phase-1-auth-service-audit.md) |
| 2 | Chat Service | [phase-2-chat-service-audit.md](phase-2-chat-service-audit.md) |
| 3 | Message Service | [phase-3-message-service-audit.md](phase-3-message-service-audit.md) |
| 4 | File Service | [phase-4-file-service-audit.md](phase-4-file-service-audit.md) |
| 5 | Frontend | [phase-5-frontend-audit.md](phase-5-frontend-audit.md) |
| 6 | Infrastructure | [phase-6-infrastructure-audit.md](phase-6-infrastructure-audit.md) |

---

## Deferred Items (Require Architectural Changes)

1. **CHAT-04: Redis blacklist propagation** — Chat/Message/File services don't check the Redis token blacklist. Fixing requires adding Redis dependency to all services or switching to short-lived tokens + refresh tokens.
2. **MSG-01: Room membership verification on history API** — Requires cross-service call or API gateway enforcement.
3. **CHAT-05: Auto-admin promotion** — Design decision about room administration policy.
4. **INFRA-02: Kafka authentication** — Requires SASL/SCRAM setup across all services.

---

## Test Results After Fixes

| Service | Tests | Result |
|---------|-------|--------|
| Auth Service | 115 | All passed |
| Chat Service | go vet | Clean compilation |
| Message Service | 170 | All passed |
| File Service | 109 | All passed |
