---
name: api-design
description: Guide API design decisions across the full lifecycle — endpoint design, naming, HTTP methods, status codes, error handling, pagination, filtering, versioning, rate limiting, and documentation. Framework-agnostic, works with REST, GraphQL, gRPC, or WebSocket. Use when creating endpoints, designing API contracts, discussing API structure, choosing status codes, handling API errors, or versioning APIs. Triggers on API design, endpoint, route, status code, error response, pagination, rate limiting, API versioning, REST, GraphQL, gRPC, new endpoint, API contract.
---

# API Design — Full Lifecycle Guide

## Purpose

Provide decision frameworks for designing APIs that are:
- **Consistent** — predictable patterns across all endpoints
- **Evolvable** — can change without breaking existing consumers
- **Debuggable** — errors are clear, responses are traceable
- **Documented** — contract is explicit, not implicit

This skill is **framework-agnostic** — the principles apply whether you're building REST, GraphQL, gRPC, or WebSocket APIs. Adapt to whatever technology the project uses.

## When This Skill Activates

### Auto-suggested (strongly recommended)
- **Creating new endpoints or routes** — before writing handler code
- **Designing API contracts** — discussing shape, naming, structure
- **Touching API-related files** — handlers, controllers, route definitions

### Manual invocation
- "design this API", "what status code should I use", "how should I version this"

## The API Design Process

When this skill activates, follow these steps:

### Step 1: Clarify the Contract

Before writing any handler code, answer:

1. **Who is the consumer?** (frontend, mobile, other service, third-party)
2. **What resource or action does this represent?**
3. **What are the inputs?** (path params, query params, body)
4. **What are the outputs?** (success shape, error shape)
5. **What can go wrong?** (validation, not found, unauthorized, conflict)

### Step 2: Identify the Design Area

| If the question is about... | Jump to |
|-----------------------------|---------|
| URL structure, naming | [Endpoint Design](#endpoint-design) |
| HTTP method choice | [HTTP Methods](#http-methods) |
| Response codes | [Status Codes](#status-codes) |
| Error format | [Error Handling](#error-handling) |
| Lists and large datasets | [Pagination & Filtering](#pagination--filtering) |
| Breaking changes, evolution | [Versioning](#versioning) |
| Abuse prevention | [Rate Limiting](#rate-limiting) |
| Making the API discoverable | [Documentation](#documentation) |

### Step 3: Apply the Guidance

Use the relevant section below. Focus on **consistency** — a consumer should be able to guess your API's behavior after learning one endpoint.

---

## Endpoint Design

### Naming Conventions

| Principle | Good | Bad |
|-----------|------|-----|
| Use nouns, not verbs | `/users`, `/orders` | `/getUsers`, `/createOrder` |
| Plural for collections | `/users`, `/products` | `/user`, `/product` |
| Nested for relationships | `/users/{id}/orders` | `/getUserOrders` |
| Kebab-case for multi-word | `/order-items` | `/orderItems`, `/order_items` |
| No trailing slashes | `/users` | `/users/` |

### URL Structure

```
/{version}/{resource}/{id}/{sub-resource}

Examples:
GET    /v1/users                    # list users
GET    /v1/users/123                # get user 123
GET    /v1/users/123/orders         # list orders for user 123
POST   /v1/users/123/orders         # create order for user 123
```

### When to Break Nesting

Stop nesting at **two levels deep**. Beyond that, promote the sub-resource to its own top-level endpoint.

```
# Good: two levels
GET /users/123/orders

# Bad: three levels deep
GET /users/123/orders/456/items

# Better: promote to top-level with filter
GET /orders/456/items
```

---

## HTTP Methods

| Method | Meaning | Idempotent? | Request body? |
|--------|---------|-------------|---------------|
| `GET` | Read a resource | Yes | No |
| `POST` | Create a resource or trigger an action | No | Yes |
| `PUT` | Replace a resource entirely | Yes | Yes |
| `PATCH` | Partial update | No* | Yes |
| `DELETE` | Remove a resource | Yes | Rarely |

*PATCH can be made idempotent with proper design, but isn't guaranteed.

### Method Selection Decision

```
Need to read data?              → GET
Creating a new resource?        → POST
Replacing a resource entirely?  → PUT
Updating specific fields only?  → PATCH
Removing a resource?            → DELETE
Triggering an action (not CRUD)?→ POST to an action endpoint
                                  e.g., POST /orders/123/cancel
```

---

## Status Codes

### The Ones You Actually Need

| Code | When to use |
|------|-------------|
| **200** | Success — returning data |
| **201** | Created — resource was created (POST) |
| **204** | No content — success but nothing to return (DELETE) |
| **400** | Bad request — client sent invalid input |
| **401** | Unauthorized — no valid credentials |
| **403** | Forbidden — authenticated but not allowed |
| **404** | Not found — resource doesn't exist |
| **409** | Conflict — state conflict (duplicate, version mismatch) |
| **422** | Unprocessable — input is well-formed but semantically wrong |
| **429** | Too many requests — rate limited |
| **500** | Internal error — server failed unexpectedly |

### Decision Framework

```
Did the request succeed?
  ├── Yes → Did we create something? → 201
  │         Did we return data?      → 200
  │         Nothing to return?       → 204
  └── No  → Is it the client's fault?
              ├── Yes → Bad input format?     → 400
              │         Not authenticated?     → 401
              │         Not authorized?        → 403
              │         Resource not found?    → 404
              │         State conflict?        → 409
              │         Valid format, bad data?→ 422
              │         Too many requests?     → 429
              └── No  → Server error           → 500
```

### 400 vs 422

- **400**: The request is malformed — can't even parse it (missing required field, wrong JSON syntax, wrong type)
- **422**: The request is well-formed but violates business rules (email already taken, insufficient balance, date in the past)

---

## Error Handling

### Consistent Error Response Shape

Every error should return the same structure. Pick one and use it everywhere:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Human-readable description of what went wrong",
    "details": [
      {
        "field": "email",
        "reason": "Email is already registered"
      }
    ],
    "request_id": "req_abc123"
  }
}
```

### Error Design Principles

| Principle | Why |
|-----------|-----|
| Machine-readable `code` | Consumers switch on codes, not messages |
| Human-readable `message` | Developers read messages during debugging |
| Field-level `details` for validation | Frontend can show errors next to specific fields |
| `request_id` always present | Enables log correlation across services |
| Never expose internals | No stack traces, SQL errors, or internal paths in production |

### Error Code Convention

Use UPPER_SNAKE_CASE for error codes. Group by domain:

```
AUTH_TOKEN_EXPIRED
AUTH_INSUFFICIENT_PERMISSIONS
VALIDATION_FAILED
RESOURCE_NOT_FOUND
RESOURCE_ALREADY_EXISTS
RATE_LIMIT_EXCEEDED
```

---

## Pagination & Filtering

### Pagination Patterns

| Pattern | Use when | Trade-off |
|---------|----------|-----------|
| **Offset-based** (`?page=2&limit=20`) | Simple UI with page numbers | Skips items if data changes between pages |
| **Cursor-based** (`?cursor=abc&limit=20`) | Infinite scroll, real-time feeds | No random page access, more complex |
| **Keyset** (`?after_id=123&limit=20`) | Large datasets, stable ordering | Requires sortable unique field |

**Default: cursor-based** for most APIs. Offset-based only if consumers need page numbers.

### Pagination Response Shape

```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6MTIzfQ==",
    "has_more": true,
    "total_count": 1042
  }
}
```

`total_count` is optional — it's expensive on large datasets. Only include if consumers need it.

### Filtering & Sorting

```
# Filtering
GET /users?status=active&role=admin

# Sorting
GET /users?sort=created_at&order=desc

# Combining
GET /users?status=active&sort=name&order=asc&limit=20
```

Keep filter parameter names consistent with response field names.

---

## Versioning

### Versioning Strategies

| Strategy | Example | Trade-off |
|----------|---------|-----------|
| **URL path** | `/v1/users` | Explicit, easy to route, duplicates code |
| **Header** | `Accept: application/vnd.api+json;version=2` | Clean URLs, harder to test in browser |
| **Query param** | `/users?version=2` | Easy to use, pollutes query string |

**Default: URL path versioning.** It's the most explicit and debuggable.

### When to Version

| Change type | Needs new version? |
|-------------|-------------------|
| Adding a new field to response | No — additive, backwards compatible |
| Adding a new optional parameter | No — backwards compatible |
| Adding a new endpoint | No — doesn't break existing consumers |
| Removing a field from response | **Yes** — breaking change |
| Renaming a field | **Yes** — breaking change |
| Changing a field's type | **Yes** — breaking change |
| Changing error response format | **Yes** — breaking change |

### The Rule

**Additive changes are safe. Removals and renames are breaking.** When in doubt, add a new field and deprecate the old one.

---

## Rate Limiting

### Response Headers

Always include rate limit info in response headers:

```
X-RateLimit-Limit: 100        # max requests per window
X-RateLimit-Remaining: 42     # requests left in current window
X-RateLimit-Reset: 1625097600 # when the window resets (Unix timestamp)
Retry-After: 30               # seconds to wait (only on 429)
```

### Rate Limit Tiers

| Tier | Use case | Example |
|------|----------|---------|
| **Per-user** | Authenticated endpoints | 1000 req/hour per API key |
| **Per-IP** | Public/unauthenticated | 100 req/hour per IP |
| **Per-endpoint** | Expensive operations | 10 req/min for `/search` |

### 429 Response Body

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Try again in 30 seconds.",
    "retry_after": 30
  }
}
```

---

## Documentation

### What Every API Must Document

- [ ] **Authentication** — how to obtain and use credentials
- [ ] **Base URL** — per environment (dev, staging, production)
- [ ] **Endpoints** — method, path, parameters, request/response examples
- [ ] **Error format** — the consistent error shape + all error codes
- [ ] **Rate limits** — per tier, per endpoint where applicable
- [ ] **Versioning policy** — how versions work, deprecation timeline
- [ ] **Changelog** — what changed between versions

### Documentation Approaches

| Approach | Best for |
|----------|----------|
| **OpenAPI/Swagger** | REST APIs — auto-generates docs and clients |
| **GraphQL introspection** | GraphQL — built-in schema documentation |
| **Proto files** | gRPC — self-documenting via .proto definitions |
| **Hand-written** | Narrative docs, guides, getting-started |

**Combine generated + hand-written.** Auto-generated docs cover the "what", hand-written docs cover the "why" and "how to get started".

---

## Anti-Patterns to Flag

| Anti-pattern | What it looks like | Why it's bad |
|-------------|-------------------|--------------|
| **Verb endpoints** | `POST /getUser` | Confuses HTTP semantics with URL naming |
| **Inconsistent naming** | `/users` + `/get-products` + `/Order` | Consumers can't predict patterns |
| **Generic 200 for everything** | `200 { "success": false, "error": "..." }` | Breaks HTTP semantics, confuses clients and proxies |
| **Leaking internals** | Error contains SQL query or stack trace | Security risk, confusing for consumers |
| **No pagination on lists** | `GET /logs` returns 50,000 records | Memory bombs, slow responses, timeouts |
| **Breaking changes without versioning** | Renaming `user_name` to `username` in v1 | Breaks all existing consumers silently |
| **Nested URLs beyond 2 levels** | `/a/1/b/2/c/3/d` | Unreadable, hard to route, implies tight coupling |
| **Inconsistent error shapes** | Different structure per endpoint | Consumers need per-endpoint error handling |

---

## Quick Reference

```
API Design Flow:
1. Clarify the contract (consumer, resource, inputs, outputs, errors)
2. Name the endpoint (nouns, plural, kebab-case, max 2 levels deep)
3. Choose HTTP method (GET/POST/PUT/PATCH/DELETE)
4. Define status codes (use the decision tree)
5. Design error shape (consistent across all endpoints)
6. Add pagination if returning lists
7. Plan versioning strategy
8. Document everything
```
