# ADR Template Reference

## Table of Contents

- [What is an ADR?](#what-is-an-adr)
- [Template](#template)
- [Storage](#storage)
- [Naming Convention](#naming-convention)
- [Examples](#examples)

---

## What is an ADR?

An Architecture Decision Record (ADR) captures a significant architectural decision along with its context and consequences. ADRs are lightweight, versioned, and stored alongside the code they affect.

**Write an ADR when:**
- Choosing between service architectures (monolith vs microservices)
- Picking a communication pattern (sync vs async)
- Deciding on data ownership or storage strategy
- Making deployment topology decisions
- Choosing frameworks or significant libraries
- Defining module boundaries or layering strategy

**Don't write an ADR for:**
- Implementation details (which sort algorithm, variable naming)
- Trivial decisions with obvious answers
- Decisions that are easily reversible with no cost

---

## Template

```markdown
# ADR-NNNN: <Title — short, descriptive>

**Status:** proposed | accepted | deprecated | superseded by ADR-NNNN
**Date:** YYYY-MM-DD
**Decision makers:** <who was involved>

## Context

What is the issue? What forces are at play? What constraints exist?
Be factual, not persuasive. A reader should understand the situation
without knowing the decision yet.

## Decision

What is the change we're making? State it clearly in one or two sentences.

## Rationale

Why this option over the alternatives? What trade-offs are we accepting?

## Alternatives Considered

### Alternative 1: <Name>
- **Pros:** ...
- **Cons:** ...
- **Why rejected:** ...

### Alternative 2: <Name>
- **Pros:** ...
- **Cons:** ...
- **Why rejected:** ...

## Consequences

### Positive
- What gets better?

### Negative
- What gets worse or becomes harder?

### Risks
- What could go wrong? What assumptions might break?

## Diagram

Include a mermaid diagram showing the architecture this decision creates.

## Follow-up Actions

- [ ] Action items that result from this decision
```

---

## Storage

Store ADRs in the project repository:

```
docs/adr/
  0001-use-event-driven-messaging.md
  0002-separate-auth-into-own-service.md
  0003-adopt-modular-monolith.md
```

Create the directory if it doesn't exist: `mkdir -p docs/adr`

---

## Naming Convention

```
NNNN-<kebab-case-title>.md
```

- `NNNN` — sequential number, zero-padded to 4 digits
- Title — short, starts with a verb (use, adopt, separate, choose, implement)

**Examples:**
- `0001-use-postgresql-for-persistence.md`
- `0002-separate-auth-service.md`
- `0003-adopt-saga-pattern-for-orders.md`

To find the next number:
```bash
ls docs/adr/ | tail -1  # see the latest ADR number
```

---

## Examples

### Minimal ADR (small decisions)

```markdown
# ADR-0005: Use Redis for Session Storage

**Status:** accepted
**Date:** 2026-03-25

## Context
We need server-side session storage. Sessions are short-lived (24h TTL),
read-heavy, and don't need ACID guarantees.

## Decision
Use Redis for session storage.

## Rationale
Redis handles TTL natively, is fast for key-value lookups, and we already
run it for caching. Adding a second data store for sessions adds no new
operational burden.

## Alternatives Considered
- **PostgreSQL:** Already in use, but overkill for ephemeral key-value data.
  Would need manual TTL cleanup.
- **In-memory (process):** No persistence, lost on restart, no sharing across
  instances.

## Consequences
- **Positive:** Fast lookups, automatic TTL, shared across instances
- **Negative:** Redis becomes a harder dependency (was optional for cache)
```

### Full ADR (significant decisions)

Use the full template above — include diagram, risks, and follow-up actions.
