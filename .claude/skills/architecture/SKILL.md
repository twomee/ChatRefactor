---
name: architecture
description: Guide architectural decisions across system design, code structure, and infrastructure. Use when designing service boundaries, choosing communication patterns, structuring modules, planning deployments, creating new services or modules, refactoring boundaries, or asking where logic belongs. Triggers on architecture, system design, service boundary, microservice, monolith, data flow, module structure, folder structure, layering, dependency direction, deployment, scaling, new service, new module, separate service, where does this belong, how should I structure.
---

# Architecture — Design Decisions Guide

## Purpose

Provide a structured framework for making architectural decisions at any level:
- **System design** — service boundaries, data flow, communication patterns
- **Code architecture** — module structure, layering, dependency direction
- **Infrastructure** — deployment topology, scaling strategy, observability

This skill is **framework-agnostic** — it teaches principles and decision frameworks, not specific stack choices. Adapt the output to whatever technology the project uses.

## When This Skill Activates

### Auto-suggested (strongly recommended)
- **Starting a new project or service** — before any code is written
- **Making structural changes** — new service, new module, refactoring boundaries
- **Architecture questions** — "should this be separate?", "where does this belong?"

### Manual invocation
- "architecture review", "design this system", "how should I structure this"

## The Architecture Decision Process

When this skill activates, follow these steps in order:

### Step 1: Clarify the Problem

Before designing anything, answer:

1. **What problem are we solving?** (not "what do we want to build")
2. **Who are the consumers?** (users, other services, both)
3. **What are the constraints?** (team size, timeline, existing infra, budget)
4. **What are the quality attributes?** (latency, throughput, availability, consistency)

### Step 2: Identify the Decision Type

| If the question is about... | Use this framework |
|-----------------------------|--------------------|
| Service boundaries | [System Design](#system-design) |
| Where code should live | [Code Architecture](#code-architecture) |
| How to deploy/scale | [Infrastructure](#infrastructure) |
| Cross-cutting (spans multiple) | Start with System Design, then drill down |

### Step 3: Apply the Framework

Use the relevant section below. Each framework produces:
- A **recommendation** with rationale
- **Alternatives considered** with trade-offs
- A **diagram** (mermaid) showing the design

### Step 4: Document the Decision

Generate an ADR (Architecture Decision Record). See [ADR_TEMPLATE.md](ADR_TEMPLATE.md) for the full template.

---

## System Design

### Service Boundary Decision

Ask these questions to determine if something should be its own service:

```
1. Does it have its own data? (own database/store)
2. Can it be deployed independently?
3. Does a different team own it (or will they)?
4. Does it have different scaling requirements?
5. Does it have a different failure domain?
```

**Score: 4-5 yes → separate service. 2-3 → maybe. 0-1 → keep together.**

### Communication Patterns

| Pattern | Use when | Trade-off |
|---------|----------|-----------|
| **Sync (HTTP/gRPC)** | Need immediate response, simple request/reply | Tight coupling, cascade failures |
| **Async (message queue)** | Fire-and-forget, eventual consistency OK | Complexity, harder to debug |
| **Event-driven** | Multiple consumers, decoupled reactions | Event schema evolution, ordering |
| **Saga/choreography** | Distributed transactions across services | Compensation logic, eventual consistency |

### Data Ownership

**Rule: One service owns one dataset.** If two services need the same data:

1. **Preferred** — Service A owns it, Service B calls A's API
2. **Acceptable** — Event-driven replication (A publishes, B subscribes and caches)
3. **Avoid** — Shared database (creates hidden coupling)

### Diagram: System Design

Always produce a mermaid diagram showing:
- Services and their boundaries
- Data stores and ownership
- Communication patterns (sync vs async)
- External dependencies

```
graph LR
    A[Service A] -->|sync: HTTP| B[Service B]
    A -->|async: event| Q[(Message Queue)]
    Q --> C[Service C]
    A --- DB_A[(DB A)]
    B --- DB_B[(DB B)]
```

---

## Code Architecture

### Layering Principles

Regardless of framework, code should flow in one direction:

```
  Entrypoint (HTTP handler, CLI, event consumer)
       ↓
  Application Layer (use cases, orchestration)
       ↓
  Domain Layer (business logic, rules, entities)
       ↓
  Infrastructure Layer (database, external APIs, file system)
```

**The dependency rule:** Inner layers never import from outer layers. Domain doesn't know about HTTP. Application doesn't know about the database driver.

### Where Does This Logic Belong?

| If the logic... | It belongs in... |
|-----------------|------------------|
| Parses HTTP requests, formats responses | **Entrypoint** (handler/controller) |
| Orchestrates multiple steps, calls multiple services | **Application** (use case/service) |
| Enforces business rules, validates domain invariants | **Domain** (entity/value object) |
| Talks to database, external API, file system | **Infrastructure** (repository/client/adapter) |
| Is reused across multiple layers | **Shared utility** (but be cautious — most "shared" code shouldn't be) |

### Module Boundary Decision

Ask these questions when deciding whether to create a new module/package:

```
1. Does it have a clear, single responsibility?
2. Can you describe its API in one sentence?
3. Does it have different change reasons than its neighbors?
4. Would extracting it reduce coupling or improve testability?
```

**3-4 yes → extract. 1-2 → probably keep together. 0 → definitely keep together.**

### Dependency Direction

```
  ┌─────────────┐
  │   Handler    │ ──→ depends on ──→ ┌──────────┐
  └─────────────┘                      │ Service  │
                                       └──────────┘
                                            │
                                     depends on (interface)
                                            │
                                            ▼
                                    ┌──────────────┐
                                    │  Repository   │ (interface)
                                    └──────────────┘
                                            ▲
                                    implements │
                                    ┌──────────────────┐
                                    │ PostgresRepository │ (concrete)
                                    └──────────────────┘
```

**Key insight:** The service depends on a Repository *interface*, not a concrete implementation. This is dependency inversion — the inner layer defines the contract, the outer layer implements it.

---

## Infrastructure

### Deployment Topology Decision

| Topology | Use when | Trade-off |
|----------|----------|-----------|
| **Single process** | Early stage, small team, simple domain | Fast iteration, limited scale |
| **Modular monolith** | Medium complexity, one team, shared DB OK | Good boundaries + simple deploy |
| **Microservices** | Multiple teams, independent scaling needs | Operational complexity |
| **Serverless** | Event-driven, spiky traffic, no ops team | Cold starts, vendor lock-in |

**Start simple, split when you have evidence.** Premature microservices is a common and expensive mistake.

### Scaling Strategy

| Strategy | Solves | Doesn't solve |
|----------|--------|---------------|
| **Horizontal scaling** (more instances) | Throughput, availability | Single-request latency |
| **Vertical scaling** (bigger machine) | CPU/memory bound work | Availability, cost at scale |
| **Caching** | Read-heavy workloads, latency | Write-heavy, consistency |
| **Read replicas** | Read throughput on database | Write throughput |
| **Sharding** | Data volume, write throughput | Cross-shard queries, complexity |

### Observability Checklist

Every service should have:
- [ ] **Structured logging** — JSON logs with correlation IDs
- [ ] **Metrics** — request rate, error rate, latency (RED method)
- [ ] **Health checks** — liveness + readiness endpoints
- [ ] **Distributed tracing** — trace ID propagated across service calls
- [ ] **Alerting** — on SLO violations, not just errors

---

## Producing Artifacts

When this skill is invoked, produce **all three**:

### 1. Guidance

Answer the user's question using the frameworks above. Explain the trade-offs, not just the recommendation. Always mention what would change the answer.

### 2. Architecture Decision Record (ADR)

Write a short ADR documenting the decision. Use the template in [ADR_TEMPLATE.md](ADR_TEMPLATE.md). Store ADRs in `docs/adr/` in the project repo.

### 3. Diagram

Generate a mermaid diagram appropriate to the decision:
- **System design** → service boundaries, data flow, communication
- **Code architecture** → module dependencies, layer diagram
- **Infrastructure** → deployment topology, network layout

---

## Anti-Patterns to Flag

When reviewing architecture, watch for these:

| Anti-pattern | What it looks like | Why it's bad |
|-------------|-------------------|--------------|
| **Distributed monolith** | Microservices that must deploy together | Worst of both worlds — complexity without independence |
| **Shared database** | Multiple services reading/writing same tables | Hidden coupling, schema changes break everything |
| **God service** | One service that does everything | Single point of failure, impossible to scale selectively |
| **Chatty services** | Service A makes 10+ calls to Service B per request | Latency amplification, tight coupling |
| **Circular dependencies** | A → B → C → A | Impossible to deploy independently, tangled logic |
| **Anemic domain** | Entities are just data bags, all logic in services | Business rules scattered, hard to enforce invariants |
| **Big ball of mud** | No clear boundaries, everything imports everything | Untestable, un-refactorable, onboarding nightmare |

---

## Quick Reference

```
Architecture Decision Flow:
1. Clarify the problem (not the solution)
2. Identify decision type (system / code / infra)
3. Apply the framework (score-based questions)
4. Document with ADR + diagram
5. Review anti-patterns

Artifacts to produce:
- Guidance with trade-offs
- ADR in docs/adr/
- Mermaid diagram
```
