---
name: dev-docs
description: Capture session context (working state, decisions, technical discoveries) into structured dev-docs. Triggers before context compaction, before commits, before PR creation, or on manual request. Use when saving session state, documenting progress, preserving decisions, capturing debugging findings, session notes, save context, document progress, context compaction, session summary, what did we do, where were we, before committing, before PR.
---

# Dev Docs — Session Memory

## Purpose

Capture **working state and technical discoveries** from a development session into a structured document that:
1. Survives context compaction (when conversation history gets trimmed)
2. Lets future sessions pick up exactly where this one left off
3. Preserves decisions, gotchas, and rationale that aren't in the code or git history

### What This Is NOT

| System | Purpose | Use dev-docs instead? |
|--------|---------|-----------------------|
| **Auto-memory** (`~/.claude/projects/.../memory/`) | Durable user prefs, project facts, feedback | No — memory is cross-session, dev-docs is per-session |
| **Git history** | Code changes, commit messages | No — git tracks *what* changed, dev-docs tracks *why* and *what's next* |
| **Tasks** (TaskCreate/TaskUpdate) | Current session work breakdown | No — tasks are ephemeral, dev-docs persist across sessions |
| **`dev-docs-update` / other dev-docs skills** | Different skills with different scope | No — this skill is specifically for session memory |

## When This Skill Activates

### Auto-suggested (remind, don't block)
- **Before context compaction** — save everything a future session needs
- **Before commits** — capture decisions and discoveries alongside the code change
- **Before PR creation** — document the full context of the work

### Manual invocation
- "save dev docs", "session notes", "document what we did", "where were we"
- Starting a new session on existing work — read previous dev-docs first

## Storage

### Default: Private (per-user)

```
~/.claude/projects/<project-hash>/dev-docs/YYYY-MM-DD-<topic-slug>.md
```

Dev-docs are private by default — they live alongside your memory files, not in the repo.

### Promote to repo (on request)

When the user says "promote this doc" or "share this dev-doc":

```
.claude/dev-docs/YYYY-MM-DD-<topic-slug>.md
```

Copy to the repo's `.claude/dev-docs/` directory so it's committed and shared with the team. Add `.claude/dev-docs/` to `.gitignore` if the user wants it tracked only locally within the repo.

## Lifecycle: Append-Only

- Each session creates a **new doc** — never overwrite previous ones
- Old docs stay as historical reference
- When work is fully complete, mark status as `completed` in the doc
- Promote durable learnings to auto-memory before archiving

## Document Template

```markdown
# Dev Doc: <Topic>

**Date:** YYYY-MM-DD
**Branch:** <current git branch>
**Session:** <brief description of what this session focused on>
**Status:** in-progress | completed | blocked

## Context

What is the goal? Why are we doing this?
Link to ticket/PR if applicable.

## Decisions Made

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| ... | ... | ... |

## What Was Done

- Completed work with file paths for key changes
- Tests added or modified

## Key Discoveries

Technical findings not obvious from the code:
- Gotchas, edge cases, surprising behavior
- Performance characteristics
- Dependency quirks or version constraints
- Debugging dead-ends (what was tried and why it didn't work)

## Current State

- What works
- What's partially done
- What's broken or blocked

## Next Steps

1. First priority
2. Second priority

## Open Questions

- Unresolved decisions needing input
- Things to investigate further
```

## How to Create a Dev Doc

### Step 1: Gather Context

Before writing, collect:
- The user's original goal for this session
- `git status` and `git diff` for current changes
- Key decisions made and their rationale
- Problems encountered and how they were resolved
- Anything surprising or non-obvious discovered
- What's left to do

### Step 2: Write the Doc

```bash
# Determine the private dev-docs path
~/.claude/projects/<project-hash>/dev-docs/YYYY-MM-DD-<topic>.md
```

Use the template above. Be specific — a future session with **zero context** should be able to read this doc and continue the work.

**Good entries:**
- "Chose sync delivery over Kafka for chat-service because Kafka consumer had 200ms lag breaking real-time guarantees. See `services/chat-service/cmd/main.go:45`."
- "Auth middleware returns 401 for expired tokens but frontend expects 403 — blocked on frontend team decision."
- "Discovered that `golangci-lint` v1.55+ requires Go 1.21 — pinned to v1.54 in CI. Will revisit when we upgrade Go."

**Bad entries:**
- "Worked on auth stuff" (too vague)
- "Fixed the bug" (which bug? what root cause?)

### Step 3: On Future Sessions

When resuming work:
1. List files in the dev-docs directory
2. Read the most recent relevant doc
3. Resume from **Next Steps** section
4. Create a new doc for the new session (append-only)

### Step 4: Promote (Optional)

When the user asks to share a dev-doc with the team:
1. Copy from private path to `.claude/dev-docs/` in the repo
2. Confirm with user before adding to git

### Step 5: Archive

When work is complete:
1. Update status to `completed` in the doc
2. Extract any durable learnings → save as auto-memory
3. Leave the doc in place — don't delete
