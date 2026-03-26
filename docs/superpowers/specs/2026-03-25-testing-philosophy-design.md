# Testing Philosophy Skill — Design Spec

**Date:** 2026-03-25
**Status:** Approved
**Type:** Domain skill (suggest enforcement)

## Problem

Engineers need guidance not just on *how* to write tests (TDD process) but on *what* to test, *how deeply*, and *why*. Without a testing philosophy, teams end up with tests that restate implementation, chase coverage numbers, mock everything, or miss critical integration boundaries.

## Scope

This skill covers testing **judgment and strategy** — the decisions an engineer makes before writing a test. It is language-agnostic and complements the existing `superpowers:test-driven-development` skill, which owns the red-green-refactor process.

**In scope:**
- Decision frameworks: what to test, unit vs integration, when to mock, coverage philosophy
- Testing principles: behavior over implementation, tests as documentation, feedback speed
- Relationship to TDD workflow

**Out of scope:**
- Language-specific syntax or framework APIs
- The TDD process itself (owned by `superpowers:test-driven-development`)
- CI/CD configuration or coverage tooling setup

## Design

### Skill Identity

| Field | Value |
|-------|-------|
| Name | `testing-philosophy` |
| Location | `.claude/skills/testing-philosophy/SKILL.md` |
| Type | `domain` |
| Enforcement | `suggest` |
| Priority | `medium` |

### Content Structure

1. **Purpose & Scope** — Positions the skill as the "what and why" complement to TDD's "when and how"
2. **The Testing Pyramid** — Mental model for test distribution. Key insight: the pyramid is about feedback speed, not unit test superiority.
3. **Decision Frameworks** — Four decisions engineers face:
   - "Is this worth testing?" — Test behavior with consequences. Skip glue code and trivial accessors.
   - "Unit or integration test?" — Unit for pure logic, integration for boundary crossings.
   - "Should I mock this?" — Mock at system boundaries, real implementations for internal collaborators.
   - "How much coverage is enough?" — Coverage is a smell detector, not a quality metric.
4. **Testing Principles** — The "why" behind the frameworks:
   - Test behavior, not implementation
   - Tests are documentation
   - Fast tests get run, slow tests get skipped
   - One assertion per concept
5. **Relationship to TDD** — Brief note on how to use these frameworks within a TDD workflow.

### Trigger Configuration

- **Keywords:** test, testing, mock, coverage, unit test, integration test, e2e test, what to test, test strategy, test philosophy, testing approach, worth testing, should I mock, test boundary
- **Intent patterns:** `(should|how|when|what).*(test|mock|cover)`, `(unit|integration|e2e).*(test)`, `(test|mock|stub).*(strateg|approach|decision|boundar)`, `(worth|need).*(test|cover)`

### Relationship to Other Skills

- Complements `superpowers:test-driven-development` (TDD owns process, this owns judgment)
- No dependency on or conflict with other existing skills

## Success Criteria

- Skill triggers when testing-related prompts are entered
- Content is under 500 lines (Anthropic best practice)
- Decision frameworks are actionable — an engineer can follow them to make a testing decision
- Principles explain *why*, not just *what*
