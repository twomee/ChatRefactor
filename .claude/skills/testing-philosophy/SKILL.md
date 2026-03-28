---
name: testing-philosophy
description: Testing strategy and philosophy guide. Covers what to test, unit vs integration decisions, when to mock, coverage philosophy, testing pyramid, test behavior not implementation, tests as documentation. Use when making testing decisions, writing tests, discussing test strategy, or evaluating what is worth testing.
---

# Testing Philosophy

## Purpose

This skill guides **testing judgment** — the decisions you make about *what* to test, *how deeply*, and *why*. It complements the `superpowers:test-driven-development` skill: TDD owns the red-green-refactor *process*, this skill owns the *strategy* behind what you write.

If you're following TDD, use these frameworks to decide which test to write first. If you're writing tests after implementation, use them to decide which tests actually matter.

## The Testing Pyramid

```
        /  E2E  \          Few — slow, expensive, high confidence
       /----------\
      / Integration \      Some — test real boundaries
     /----------------\
    /    Unit Tests     \   Many — fast, cheap, focused
   /____________________\
```

The pyramid is about **feedback speed**, not about unit tests being "better."

- **Bottom (unit):** Fast feedback. Run in milliseconds. Catch logic errors immediately.
- **Middle (integration):** Real boundary validation. Catch wiring errors, protocol mismatches, data format issues.
- **Top (e2e):** Full system confidence. Catch emergent behavior. Expensive to maintain.

**The key insight:** Move tests *down* the pyramid whenever possible. If you can verify behavior with a unit test, don't write an integration test for it. Save integration tests for things that *only* break when real components interact.

## Decision Frameworks

### 1. "Is this worth testing?"

**Test it if:**
- It contains business logic or rules (calculations, validations, state transitions)
- Breaking it would cause user-facing impact or data corruption
- It handles error cases that are hard to catch manually
- It's a public API contract that other code depends on

**Skip it if:**
- The test would just restate the implementation (testing that `getAge()` returns `self.age`)
- It's framework boilerplate or glue code that the framework already tests
- It's a trivial getter/setter with no logic
- It's configuration that's validated at startup

**The heuristic:** If the test teaches you nothing new about the system's behavior, it's not adding value. Tests should verify *decisions* your code makes, not *structure* your code has.

### 2. "Unit or integration test?"

**Unit test when:**
- You're testing pure logic: a function takes inputs and returns outputs
- The behavior is self-contained — no databases, no HTTP, no file system
- You want fast, precise feedback on a specific rule or calculation
- You're testing edge cases and boundary conditions

**Integration test when:**
- You're testing that components work together across a boundary
- The behavior involves real I/O: database queries, HTTP calls, message queues
- You need to verify serialization, protocol handling, or data format compatibility
- The "unit" is meaningless without its collaborators (e.g., a repository without a database)

**The principle:** The boundary between unit and integration is not about file count — it's about whether you're crossing a system boundary. Two classes collaborating in memory is still a unit test. One class talking to a database is an integration test.

### 3. "Should I mock this?"

**Mock it if:**
- It's an external system you don't control (third-party APIs, email services, payment gateways)
- It's slow or expensive to set up (full database, message broker cluster)
- You need to simulate failure modes (network timeout, 500 error, disk full)
- It's a system boundary — you're testing *your* code's behavior, not the dependency's

**Use the real thing if:**
- It's an internal collaborator (another class, module, or function in your codebase)
- It's cheap to set up (in-memory database, local test fixtures)
- The interaction *is* what you're testing (query correctness, serialization format)
- Mock setup would be more complex than using the real implementation

**The principle:** Mocks test your *assumptions* about a dependency, not the dependency itself. When your assumptions drift from reality, mocked tests pass but production breaks. Mock at the outer boundary of your system, use real implementations inside it.

**Warning signs you're over-mocking:**
- Mock setup is longer than the test itself
- Refactoring internals breaks tests even though behavior is unchanged
- Tests pass but the feature doesn't work end-to-end
- You're mocking things you own and control

### 4. "How much coverage is enough?"

**What coverage tells you:** Which lines of code *executed* during tests.

**What coverage does NOT tell you:** Whether the behavior was *verified*. A test that calls a function and ignores the result gives you coverage with zero confidence.

**Guidelines:**
- **High coverage on business logic** — Aim for thorough coverage on the code that makes decisions: validators, calculators, state machines, authorization rules
- **Moderate coverage on integration points** — Cover the happy path and critical error paths for API endpoints, database operations, message handlers
- **Don't chase coverage on boilerplate** — Config files, framework setup, dependency injection wiring, generated code
- **Never game the metric** — Writing a test solely to bump a coverage number without verifying behavior is worse than no test — it gives false confidence

**The heuristic:** If a coverage report shows an uncovered line, ask: "Would I notice if this line were deleted?" If yes, write a test. If no, it might not be worth covering.

## Testing Principles

### Test behavior, not implementation

A well-written test describes *what* the system does, not *how* it does it internally.

**Behavior test:** "When a user submits an expired coupon, the order total is unchanged and an error message is returned."

**Implementation test:** "The `validateCoupon` method calls `dateService.isExpired()` and then calls `errorBuilder.create('EXPIRED')`."

The behavior test survives refactoring. The implementation test breaks the moment you restructure the internals, even if the behavior is identical. If you refactor working code and tests break, those tests were testing implementation.

### Tests are documentation

A new engineer should be able to read your tests and understand what the system does. Test names should describe scenarios, not method names.

- **Bad:** `testProcessOrder`, `test_validate`, `it('works')`
- **Good:** `expired coupon does not reduce order total`, `test_duplicate_email_returns_409`, `it('reconnects after connection drop')`

### Fast tests get run, slow tests get skipped

A test suite that takes 30 seconds gets run on every save. A test suite that takes 10 minutes gets run before commit. A test suite that takes an hour gets run in CI and ignored locally. Optimize for the fastest feedback loop possible.

**Practical implication:** When a test *can* be a unit test, make it a unit test. Only reach for integration tests when the unit test can't verify the behavior you care about.

### One assertion per concept

This isn't "one `assert` statement per test" — it's one *logical assertion* per test. A test that checks "the response status is 201 AND the body contains the created resource" is asserting one concept: successful creation. That's fine.

A test that checks "creation works AND listing works AND deletion works" is asserting three concepts. Split it. When it fails, you want to know *which* concept broke without reading the test body.

## Relationship to TDD

If you're using `superpowers:test-driven-development`, these two skills work together:

- **TDD** tells you: write the test *first*, watch it fail, make it pass, refactor.
- **Testing philosophy** tells you: write *this kind* of test — at this layer, with this level of mocking, testing this behavior.

The TDD loop is the process. The testing philosophy is the compass that points each iteration in the right direction.
