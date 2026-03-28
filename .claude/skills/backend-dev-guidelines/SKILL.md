---
name: backend-dev-guidelines
description: Backend development guidelines covering project structure, layering, error handling, validation, logging, middleware, database access, configuration, health checks, graceful shutdown, and Docker. Agnostic principles with Go and Python/FastAPI examples. Use when writing backend code, creating handlers, services, repositories, middleware, or working on backend services. Triggers on handler, service layer, repository, middleware, backend, server, controller, database query, config management, health check, graceful shutdown, logging pattern, validation layer, dependency injection.
---

# Backend Development Guidelines

## Purpose

Provide implementation-level guidance for writing backend services that are:
- **Layered** — clear separation between transport, business logic, and data access
- **Testable** — every layer can be tested in isolation
- **Observable** — structured logging, health checks, metrics-ready
- **Resilient** — graceful shutdown, proper error propagation, config validation

**Framework-agnostic principles**, with concrete examples in Go and Python/FastAPI. See reference files for full code examples:
- [GO_EXAMPLES.md](GO_EXAMPLES.md) — Go patterns
- [PYTHON_EXAMPLES.md](PYTHON_EXAMPLES.md) — Python/FastAPI patterns

### Relationship to Other Skills

| Skill | Scope | When to use instead |
|-------|-------|---------------------|
| **architecture** | System-level: service boundaries, data ownership, communication | "Should this be a separate service?" |
| **api-design** | Contract-level: endpoints, status codes, error shapes, versioning | "What should this endpoint return?" |
| **backend-dev-guidelines** (this) | Implementation-level: how to structure and write the code | "How do I implement this handler?" |

---

## Project Structure

### The Layered Layout

Every backend service should follow this structure, regardless of language:

```
service-name/
├── cmd/ or app/           # Entrypoint — wiring, startup, shutdown
├── handler/ or routes/    # Transport layer — HTTP/gRPC/WebSocket handlers
├── service/ or services/  # Business logic — use cases, orchestration
├── repository/ or repos/  # Data access — database queries, external API clients
├── model/ or models/      # Domain types — entities, value objects, DTOs
├── middleware/             # Cross-cutting — auth, logging, rate limiting
├── config/                # Configuration — env loading, validation
├── pkg/ or utils/         # Shared utilities — only truly reusable code
└── tests/                 # Test files (or colocated with source)
```

### The Rules

1. **Handlers never contain business logic.** They parse input, call a service, format output.
2. **Services never know about HTTP.** No `request` objects, no status codes, no headers.
3. **Repositories are the only layer that talks to the database.** Services call repositories, never the DB directly.
4. **Dependencies flow inward.** Handler → Service → Repository. Never the reverse.
5. **Each layer defines its own interfaces.** The service layer defines what it needs from a repository, not the other way around.

---

## Dependency Injection

### The Principle

Construct dependencies at the top (entrypoint), pass them down. Never create dependencies inside the layer that uses them.

```
Entrypoint (main/app)
  └── creates Repository (with DB connection)
      └── creates Service (with Repository)
          └── creates Handler (with Service)
              └── registers routes
```

### Why This Matters

- **Testability** — swap real DB for a mock in tests by injecting a different repository
- **Flexibility** — change from Postgres to MySQL by swapping one implementation
- **Clarity** — every dependency is explicit, visible in the constructor

### Anti-pattern: Hidden Dependencies

```
# BAD — service creates its own database connection
class UserService:
    def __init__(self):
        self.db = Database.connect("postgres://...")  # hidden, untestable

# GOOD — database connection injected
class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo  # explicit, testable
```

---

## Error Handling

### The Principle

Errors should propagate up the call stack with context added at each layer. The handler is the only layer that translates errors into HTTP responses.

### Error Flow

```
Repository: returns domain errors (NotFound, Conflict, DBError)
     ↓
Service: catches, adds context, may translate or wrap
     ↓
Handler: maps domain errors → HTTP status codes + response body
```

### Rules

| Rule | Why |
|------|-----|
| Never silently swallow errors | Hidden failures become debugging nightmares |
| Add context when wrapping | "failed to create user" is better than just passing the raw DB error |
| Use domain-specific error types | `UserNotFoundError` is clearer than a generic `NotFoundError` |
| Log at the boundary, not at every layer | One log entry per error, at the handler, with full context |
| Never expose internal errors to clients | No stack traces, no SQL, no file paths |

---

## Validation

### Two Layers of Validation

| Layer | What it validates | Examples |
|-------|-------------------|---------|
| **Transport (handler)** | Shape and format | Required fields present, correct types, valid JSON |
| **Business (service)** | Rules and constraints | Email not already taken, balance sufficient, date not in past |

### Rules

- **Validate early, fail fast.** Check input at the handler before calling the service.
- **Return all validation errors at once.** Don't make the client fix one error, resubmit, fix the next.
- **Keep validation logic in the service layer for business rules.** The handler validates format, the service validates meaning.

---

## Logging

### Structured Logging

Every log entry should be a structured object (JSON), not a free-form string.

```
# BAD
logger.info(f"User {user_id} created by {admin_id}")

# GOOD
logger.info("user_created", user_id=user_id, created_by=admin_id)
```

### What to Log

| Event | Level | Fields |
|-------|-------|--------|
| Request received | INFO | method, path, request_id |
| Request completed | INFO | method, path, status, duration_ms, request_id |
| Business event | INFO | event name, relevant IDs |
| Validation failure | WARN | field, reason, request_id |
| Unexpected error | ERROR | error message, stack (server-side only), request_id |
| External call | DEBUG | service, method, duration_ms |

### Rules

- **Always include `request_id`** — enables tracing a request across logs
- **Log at boundaries** — when entering/leaving the service, not inside every function
- **Never log sensitive data** — passwords, tokens, PII, credit cards
- **Use consistent field names** — `user_id` everywhere, not sometimes `userId` or `uid`

---

## Middleware

### Common Middleware Stack

Apply in this order (outermost to innermost):

```
1. Recovery/Panic handler  — catch panics, return 500
2. Request ID              — generate/extract request ID
3. Logging                 — log request/response
4. CORS                    — cross-origin headers
5. Authentication          — validate token, set user context
6. Authorization           — check permissions
7. Rate limiting           — throttle requests
8. Your handler            — actual business logic
```

### Rules

- **Middleware should be single-purpose.** One middleware, one concern.
- **Middleware should not contain business logic.** Auth checks are OK, business rules are not.
- **Order matters.** Recovery must be first (catches panics from everything below). Auth before authorization.

---

## Database Access

### Repository Pattern

The repository is the only place that knows about the database. It exposes domain-friendly methods, hides SQL/ORM details.

### Rules

| Rule | Why |
|------|-----|
| One repository per domain entity | `UserRepository`, `OrderRepository` — not a god repository |
| Methods return domain types | Return `User`, not `sql.Row` or ORM model |
| Transactions belong in the service layer | The service decides what's atomic, the repo executes |
| Never build SQL with string concatenation | Always use parameterized queries — SQL injection is real |
| Close connections/cursors | Leaked connections exhaust the pool |

---

## Configuration

### The Principle

Configuration comes from the environment. The app loads it once at startup, validates it, and passes it down.

### Rules

| Rule | Why |
|------|-----|
| Load from environment variables | Standard across all deployment platforms |
| Validate at startup, fail fast | Missing DB_URL at startup is better than at first request |
| Never hardcode secrets | Use `.env` for local, secrets manager for production |
| Provide `.env.example` | New developers know what to configure |
| Use typed config structs | `config.DatabaseURL` is safer than `os.Getenv("DB_URL")` everywhere |

---

## Health Checks

### Every Service Needs Two Endpoints

| Endpoint | Purpose | What it checks |
|----------|---------|----------------|
| `GET /healthz` or `GET /health` | **Liveness** — is the process running? | Returns 200 if the server can respond |
| `GET /readyz` or `GET /ready` | **Readiness** — can it serve traffic? | Checks DB connection, dependent services |

### Rules

- **Liveness is cheap** — no DB calls, no external checks, just 200 OK
- **Readiness checks dependencies** — DB ping, cache ping, downstream service health
- **Never put auth on health endpoints** — load balancers and orchestrators need unauthenticated access
- **Return structured response** — `{ "status": "ok", "checks": { "db": "ok", "cache": "ok" } }`

---

## Graceful Shutdown

### The Principle

When the process receives a termination signal (SIGTERM/SIGINT), it should:

1. **Stop accepting new requests** — close the listener
2. **Finish in-flight requests** — wait for active handlers to complete
3. **Close resources** — database connections, message consumers, file handles
4. **Exit cleanly** — with exit code 0

### Rules

- **Set a shutdown timeout** — don't wait forever for stuck requests (30s is common)
- **Close resources in reverse order** — handlers first, then services, then DB
- **Log the shutdown** — "shutting down", "shutdown complete" with duration

---

## Docker

### Dockerfile Guidelines

| Guideline | Why |
|-----------|-----|
| Use multi-stage builds | Smaller images, no build tools in production |
| Run as non-root user | Security — container escape is less dangerous |
| Pin base image versions | Reproducible builds |
| Include health check | Docker/k8s can monitor without external probes |
| Upgrade system packages | `apk upgrade` or `apt-get upgrade` — patch CVEs |
| Copy dependency files first | Leverage Docker layer caching |

---

## Quick Reference

```
Backend Development Checklist:
1. Structure: handler → service → repository (dependencies flow inward)
2. DI: construct at top, inject down, never create inside
3. Errors: propagate up with context, translate at handler only
4. Validation: format at handler, business rules at service
5. Logging: structured, with request_id, at boundaries only
6. Middleware: single-purpose, correct order, no business logic
7. Database: repository pattern, parameterized queries, domain types
8. Config: env vars, validate at startup, typed structs
9. Health: /healthz (liveness) + /readyz (readiness)
10. Shutdown: stop accepting → drain → close resources → exit
11. Docker: multi-stage, non-root, pinned versions, health check
```

See [GO_EXAMPLES.md](GO_EXAMPLES.md) and [PYTHON_EXAMPLES.md](PYTHON_EXAMPLES.md) for concrete code.
