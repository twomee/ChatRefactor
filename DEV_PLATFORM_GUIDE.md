# ChatBox Dev Platform Guide

This guide explains every tool we use to build, test, and maintain ChatBox.
No prior DevOps knowledge needed.

---

## Table of Contents

1. [The Big Picture](#the-big-picture)
2. [Jira — Task Tracking](#jira--task-tracking)
3. [Confluence — Documentation](#confluence--documentation)
4. [GitHub — Code Storage](#github--code-storage)
5. [GitHub Actions — Automated Pipelines](#github-actions--automated-pipelines)
6. [Ruff — Python Linter](#ruff--python-linter)
7. [ESLint — JavaScript Linter](#eslint--javascript-linter)
8. [pytest + Coverage — Testing](#pytest--coverage--testing)
9. [Trivy — Security Scanner](#trivy--security-scanner)
10. [Gitleaks — Secret Scanner](#gitleaks--secret-scanner)
11. [Dependabot — Dependency Updates](#dependabot--dependency-updates)
12. [Pre-commit Hooks — Local Safety Net](#pre-commit-hooks--local-safety-net)
13. [How It All Works Together](#how-it-all-works-together)
14. [Microservices CI/CD](#microservices-cicd)

---

## The Big Picture

When you write code and push it, a bunch of tools run automatically to make sure
your code is clean, secure, tested, and doesn't break anything. You don't have to
run them manually — they just work.

```
You write code
    |
    v
git commit --> pre-commit hooks catch problems BEFORE the code leaves your machine
    |
    v
git push + open PR --> GitHub Actions run in the cloud:
    |                    - Is the code formatted correctly? (Ruff, ESLint)
    |                    - Do all 111 tests pass? (pytest)
    |                    - Is 50%+ of the code covered by tests? (pytest-cov)
    |                    - Are there security vulnerabilities? (Trivy)
    |                    - Are there leaked secrets? (Gitleaks)
    |                    - Do the Docker images build? (docker build)
    |
    v
All checks green? --> Safe to merge into main
    |
    v
Every Monday --> Dependabot checks if any dependencies are outdated or vulnerable
```

---

## Jira — Task Tracking

**What:** A board where you track what needs to be done, what's in progress,
and what's done.

**Where:** https://12ido350.atlassian.net

**How companies use it:**
- Create a ticket before starting work (e.g., KAN-16: "WebSocket auto-reconnect")
- Move it to "In Progress" when you start
- Reference it in your branch name: `git checkout -b KAN-16-websocket-reconnect`
- Reference it in commits: `git commit -m "KAN-16 add reconnect logic"`
- Jira auto-links your commits, branches, and PRs to the ticket

**Our setup:**
- Project: "Ido Team" (key: KAN)
- Epics: DevOps, Security, Code Quality, Features
- 10 tickets created (5 done, 5 upcoming)

---

## Confluence — Documentation

**What:** A wiki where you write project documentation that the whole team can read.

**Where:** https://12ido350.atlassian.net/wiki

**Our pages:**
- **Project Home** — overview, tech stack, quick links
- **Architecture Overview** — how the system is designed, data flows, component structure
- **Local Development Setup** — step-by-step guide to run the project
- **API Reference** — every endpoint, request/response format, WebSocket protocol
- **Architecture Decision Records** — why we chose FastAPI, Kafka, Redis, Argon2, etc.

**Why it matters:** When a new developer joins, they read Confluence instead of
asking you 50 questions. When YOU forget why you chose Kafka over RabbitMQ,
you read the ADR page.

---

## GitHub — Code Storage

**What:** Where your source code lives. Every change goes through a Pull Request (PR)
so it can be reviewed and tested before merging.

**Our repo:** https://github.com/twomee/ChatRefactor (private)

**Workflow:**
```bash
# 1. Create a branch (never work directly on main)
git checkout -b feature/my-new-thing

# 2. Write code, commit
git add .
git commit -m "KAN-XX add my new thing"

# 3. Push and open a PR
git push -u origin feature/my-new-thing
# Then open a PR on GitHub
```

---

## GitHub Actions — Automated Pipelines

**What:** Robots that run in the cloud every time you push code or open a PR.
They check if everything is OK before you merge.

**Where:** They run on GitHub's servers (not your machine). You see results
in the PR page under "Checks".

**Our pipelines:**

### CI Pipeline (`.github/workflows/ci.yml`)
Runs on every PR and push to main.

| Job | What it does | Time |
|-----|-------------|------|
| Backend Lint | Checks Python code style with Ruff | ~6s |
| Backend Tests | Runs 111 tests, checks 50%+ coverage | ~20s |
| Frontend Lint | Checks JavaScript code style with ESLint | ~7s |
| Frontend Build | Makes sure the React app compiles | ~10s |
| Docker Build | Makes sure both Docker images build | ~40s |

### Security Scan (`.github/workflows/security.yml`)
Runs on every PR, push to main, and every Monday.

| Job | What it does |
|-----|-------------|
| Trivy Code Scan | Scans your code dependencies for known vulnerabilities |
| Trivy Backend Image | Scans the backend Docker image for vulnerabilities |
| Trivy Frontend Image | Scans the frontend Docker image for vulnerabilities |

### Secret Scanning (`.github/workflows/secrets.yml`)
Runs on every PR and push to main.

| Job | What it does |
|-----|-------------|
| Gitleaks | Scans your code for accidentally committed passwords, API keys, tokens |

**If any check fails:** The PR shows a red X. You fix the issue, push again,
and the checks re-run automatically.

---

## Ruff — Python Linter

**What:** A tool that checks your Python code for bugs, style issues, and
formatting problems. Think of it as a spell-checker for code.

**Config:** `backend/ruff.toml`

**What it catches:**
- Unused imports and variables
- Unsorted imports
- Common bugs (e.g., unused loop variables)
- Security issues (e.g., hardcoded passwords)
- Code that could be simpler

**How to use locally:**
```bash
cd backend

# Check for issues
ruff check .

# Auto-fix what it can
ruff check --fix .

# Format code (like Prettier for Python)
ruff format .
```

---

## ESLint — JavaScript Linter

**What:** Same as Ruff, but for JavaScript/React code.

**Config:** `frontend/eslint.config.js`

**What it catches:**
- Unused variables
- React hook rule violations
- Empty catch blocks
- Common JavaScript mistakes

**How to use locally:**
```bash
cd frontend
npm run lint
```

---

## pytest + Coverage — Testing

**What:** pytest runs your test files. pytest-cov measures how much of your
code is actually tested (coverage percentage).

**Our stats:**
- 111 tests
- 87% code coverage
- CI fails if coverage drops below 50%

**How to run locally:**
```bash
cd backend
APP_ENV=test SECRET_KEY=test-key ADMIN_USERNAME=admin ADMIN_PASSWORD=pass \
  DATABASE_URL=sqlite:///./test.db pytest tests/ -v --cov=.
```

**What the coverage number means:**
- 87% = 87% of your code lines are executed during tests
- The other 13% are edge cases, error handlers, or code paths not yet tested
- 50% minimum is enforced in CI — if you add code without tests, it might fail

---

## Trivy — Security Scanner

**What:** Scans your code and Docker images for known security vulnerabilities (CVEs).
A CVE is a publicly known security bug in a library or system package.

**Example of what it finds:**
```
Library: curl 8.5.0
CVE: CVE-2024-2398 (HIGH)
Fix: upgrade to 8.7.1
```

This means: "The version of curl in your Docker image has a known security bug.
Upgrade it to fix the issue."

**How it works:**
- Runs automatically on every PR
- Fails the PR if it finds HIGH or CRITICAL vulnerabilities
- Runs weekly on Monday to catch newly discovered CVEs

**You don't run Trivy locally.** It runs in GitHub Actions only.

---

## Gitleaks — Secret Scanner

**What:** Scans your code for accidentally committed secrets like:
- API keys (`AKIAIOSFODNN7EXAMPLE`)
- Passwords (`password = "admin123"`)
- Tokens (`ghp_xxxxxxxxxxxxxxxxxxxx`)
- Private keys

**Why it matters:** If you accidentally commit an API key to GitHub,
attackers can find it within seconds (bots scan public repos constantly).
Even in private repos, it's bad practice.

**How it works:**
1. **Pre-commit hook** (local) — blocks the commit before it happens
2. **GitHub Action** (cloud) — scans every PR as a safety net

---

## Dependabot — Dependency Updates

**What:** A GitHub bot that automatically checks if your dependencies
(Python packages, npm packages, GitHub Actions) are outdated or have
security vulnerabilities.

**Config:** `.github/dependabot.yml`

**How it works:**
- Every Monday, Dependabot scans your dependencies
- If it finds an update, it creates a PR with the upgrade already done
- The PR runs through your CI pipeline, so you can see if the upgrade breaks anything
- You review and merge (or close if it's not ready)

**Example PR from Dependabot:**
```
Title: chore(deps): bump vite from 8.0.0 to 8.0.1 in /frontend
Description: Bumps vite from 8.0.0 to 8.0.1.
  - Release notes: [link]
  - Changelog: [link]
```

**Tip:** Patch updates (8.0.0 → 8.0.1) are usually safe to merge.
Major updates (9.x → 10.x) should be tested locally first — they
may have breaking changes.

---

## Pre-commit Hooks — Local Safety Net

**What:** Scripts that run automatically on your machine every time you
`git commit`. They catch problems before the code leaves your laptop.

**Config:** `.pre-commit-config.yaml`

**Our hooks:**
| Hook | What it does |
|------|-------------|
| gitleaks | Blocks commit if it contains secrets |
| ruff | Auto-fixes Python lint issues and formats code |
| eslint | Auto-fixes JavaScript lint issues |

**One-time setup (run this once):**
```bash
pip install pre-commit
pre-commit install
```

**What happens after setup:**
```bash
git commit -m "add new feature"
# gitleaks runs... passed
# ruff runs... fixed 2 issues, reformatted 1 file
# eslint runs... passed
# commit created!
```

If a hook fails (e.g., gitleaks finds a secret), the commit is **blocked**.
You fix the issue and commit again.

---

## How It All Works Together

Here's the full flow from writing code to merging:

```
1. CREATE TICKET
   Go to Jira, create a ticket (e.g., KAN-16)

2. CREATE BRANCH
   git checkout -b KAN-16-websocket-reconnect

3. WRITE CODE
   Write your feature/fix

4. COMMIT
   git add . && git commit -m "KAN-16 add reconnect logic"
   |
   --> Pre-commit hooks run automatically:
       [gitleaks]  no secrets found           OK
       [ruff]      auto-fixed 1 import        OK
       [eslint]    no issues                  OK
   |
   Commit created!

5. PUSH + OPEN PR
   git push -u origin KAN-16-websocket-reconnect
   Open PR on GitHub
   |
   --> GitHub Actions run automatically:
       [Backend Lint]      ruff check passed       OK
       [Backend Tests]     111 passed, 87% cov     OK
       [Frontend Lint]     eslint passed            OK
       [Frontend Build]    build succeeded          OK
       [Docker Build]      both images built        OK
       [Trivy]             no CVEs found            OK
       [Gitleaks]          no secrets found         OK

6. MERGE
   All checks green --> merge PR
   Jira ticket auto-updates with the PR link

7. WEEKLY MAINTENANCE (automatic)
   Monday: Dependabot creates PRs for outdated dependencies
   Monday: Trivy re-scans for newly discovered CVEs
```

---

## Quick Reference

| I want to... | Command |
|--------------|---------|
| Check Python code style | `cd backend && ruff check .` |
| Auto-fix Python style | `cd backend && ruff check --fix . && ruff format .` |
| Check JavaScript code style | `cd frontend && npm run lint` |
| Run backend tests | `cd backend && pytest tests/ -v` |
| Run tests with coverage | `cd backend && pytest tests/ --cov=.` |
| Install pre-commit hooks | `pip install pre-commit && pre-commit install` |
| Run all hooks manually | `pre-commit run --all-files` |

---

## Cost

Everything is **free**:
- Jira Cloud Free (up to 10 users)
- Confluence Cloud Free (up to 10 users)
- GitHub private repo (free, unlimited)
- GitHub Actions (2000 minutes/month free)
- Trivy (open source)
- Gitleaks (open source)
- Dependabot (free, built into GitHub)
- Ruff (open source)
- ESLint (open source)
- pytest (open source)

---

## Microservices CI/CD

When we moved from a monolith to microservices, the CI pipeline had to evolve. Instead of one pipeline that tests everything, each service now has its own independent pipeline that only runs when that service's code changes.

### Why Per-Service Pipelines?

In a monolith, changing one line of code triggers ALL tests (backend + frontend + Docker build). With 4 microservices, you don't want a change to the auth-service to trigger the file-service pipeline. Per-service pipelines give you:

1. **Faster feedback** — Only the affected service's tests run (~30s instead of ~3min)
2. **Independent deployability** — Each service can be merged and deployed separately
3. **Clearer ownership** — When a pipeline fails, you know exactly which service is broken
4. **Parallel execution** — All 4 pipelines can run simultaneously on different GitHub runners

### Pipeline Files

| Pipeline | File | Triggers On | What It Tests |
|----------|------|------------|---------------|
| **Auth Service** | `.github/workflows/ci-auth.yml` | Changes in `services/auth-service/` | Python lint (Ruff), pytest, Docker build |
| **Chat Service** | `.github/workflows/ci-chat.yml` | Changes in `services/chat-service/` | Go lint (golangci-lint), go test, Docker build |
| **Message Service** | `.github/workflows/ci-message.yml` | Changes in `services/message-service/` | Python lint (Ruff), pytest, Docker build |
| **File Service** | `.github/workflows/ci-file.yml` | Changes in `services/file-service/` | TypeScript lint (ESLint), Vitest, Docker build |
| **Monolith** | `.github/workflows/ci.yml` | Changes in `backend/` or `frontend/` | Same as before (Ruff, pytest, ESLint, Docker build) |
| **Security** | `.github/workflows/security.yml` | All PRs + weekly | Trivy scans for all service Docker images |
| **Secrets** | `.github/workflows/secrets.yml` | All PRs | Gitleaks across entire repo |

### How Triggers Work

Each service pipeline uses `paths` filtering so it only runs when relevant files change:

```yaml
# ci-auth.yml triggers
on:
  push:
    paths: ['services/auth-service/**']
  pull_request:
    paths: ['services/auth-service/**']

# ci-chat.yml triggers
on:
  push:
    paths: ['services/chat-service/**']
  pull_request:
    paths: ['services/chat-service/**']
```

If you change a file in `services/auth-service/`, only `ci-auth.yml` runs. If you change files in both `services/auth-service/` and `services/message-service/`, both pipelines run in parallel.

### Multi-Language Testing

With a polyglot stack (Python, Go, Node.js/TypeScript), each service uses the standard testing framework for its language:

| Service | Language | Test Framework | Lint Tool | Coverage Tool |
|---------|----------|---------------|-----------|---------------|
| auth-service | Python | **pytest** + pytest-asyncio | **Ruff** | pytest-cov |
| chat-service | Go | **go test** | **golangci-lint** | go tool cover |
| message-service | Python | **pytest** + pytest-asyncio | **Ruff** | pytest-cov |
| file-service | Node.js/TS | **Vitest** | **ESLint** | @vitest/coverage-v8 |
| backend (monolith) | Python | **pytest** | **Ruff** | pytest-cov |
| frontend | JavaScript | N/A (planned) | **ESLint** | N/A |

**Running tests locally for each service:**

```bash
# Auth service (Python)
cd services/auth-service
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v --cov=app

# Chat service (Go)
cd services/chat-service
go test ./... -v -cover

# Message service (Python)
cd services/message-service
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v --cov=app

# File service (Node.js/TypeScript)
cd services/file-service
npm install
npm test
npm run test:coverage
```

### Contract Testing with Kafka Schemas

When services communicate through Kafka, they need to agree on the message format. If auth-service starts sending a different JSON shape than message-service expects, things break silently.

**How we handle it:**

1. **Shared schema definitions** — Kafka message schemas (JSON) are defined in each service's codebase with matching field names and types
2. **Producer validation** — Each service validates outgoing Kafka messages against the expected schema before producing
3. **Consumer validation** — Each service validates incoming Kafka messages and sends malformed ones to the DLQ (dead letter queue)
4. **CI contract checks** — Integration tests verify that producer output matches consumer expectations

**Kafka topics and their schemas:**

| Topic | Producer | Consumer(s) | Key Fields |
|-------|----------|-------------|------------|
| `chat.messages` | chat-service | message-service | `message_id`, `room_id`, `sender_id`, `content`, `timestamp` |
| `chat.private` | chat-service | message-service | `message_id`, `sender_id`, `recipient_id`, `content`, `timestamp` |
| `chat.events` | chat-service | message-service | `event_type`, `room_id`, `user_id`, `timestamp` |
| `file.events` | file-service | message-service | `event_type`, `file_id`, `room_id`, `uploader_id`, `filename` |
| `auth.events` | auth-service | chat-service, message-service | `event_type`, `user_id`, `username`, `timestamp` |
| `chat.dlq` | any (on failure) | manual investigation | Original message + error metadata |

If a producer changes a field name (e.g., `sender_id` to `user_id`), the consumer's validation will catch it and the integration test will fail, preventing a broken deployment.

### Updated Dependabot Configuration

With microservices, Dependabot now monitors **8 dependency directories** (up from 3):

| Directory | Ecosystem | What It Monitors |
|-----------|-----------|-----------------|
| `/backend` | pip (Python) | Monolith backend dependencies |
| `/frontend` | npm (Node.js) | React frontend dependencies |
| `/services/auth-service` | pip (Python) | Auth service dependencies |
| `/services/chat-service` | gomod (Go) | Chat service Go modules |
| `/services/message-service` | pip (Python) | Message service dependencies |
| `/services/file-service` | npm (Node.js) | File service dependencies |
| `/.github/workflows` | github-actions | CI/CD action versions |
| `/loadtests` | pip (Python) | Load test dependencies |

**What this means in practice:**

- Dependabot creates PRs for each directory independently
- A vulnerability in a Python package triggers PRs for auth-service, message-service, AND the monolith backend (if they all use that package)
- Go module updates only affect chat-service
- npm updates affect both frontend and file-service independently

**Expected weekly Dependabot PR volume:** ~5-15 PRs per week across all directories. Patch updates are generally safe to merge after CI passes. Major version bumps require manual testing.

### Microservices CI Flow

Here's how the full CI flow works when you change a microservice:

```
1. CREATE TICKET
   Go to Jira, create a ticket (e.g., KAN-21)

2. CREATE BRANCH
   git checkout -b KAN-21/message-service

3. WRITE CODE
   Edit files in services/message-service/

4. COMMIT
   git add . && git commit -m "KAN-21 add message replay endpoint"
   |
   --> Pre-commit hooks run:
       [gitleaks]  no secrets found           OK
       [ruff]      auto-fixed 1 import        OK

5. PUSH + OPEN PR
   git push -u origin KAN-21/message-service
   Open PR on GitHub
   |
   --> ONLY ci-message.yml runs (not ci-auth, ci-chat, ci-file):
       [Message Lint]      ruff check passed       OK
       [Message Tests]     42 passed, 78% cov      OK
       [Message Docker]    image built              OK
   |
   --> security.yml and secrets.yml also run (repo-wide):
       [Trivy]             no CVEs found            OK
       [Gitleaks]          no secrets found         OK

6. MERGE
   All checks green --> merge PR
   Only message-service needs redeployment
```

### Quick Reference (Microservices)

| I want to... | Command |
|--------------|---------|
| Lint auth service | `cd services/auth-service && ruff check .` |
| Lint chat service | `cd services/chat-service && golangci-lint run ./...` |
| Lint message service | `cd services/message-service && ruff check .` |
| Lint file service | `cd services/file-service && npm run lint` |
| Test auth service | `cd services/auth-service && pytest tests/ -v` |
| Test chat service | `cd services/chat-service && go test ./... -v` |
| Test message service | `cd services/message-service && pytest tests/ -v` |
| Test file service | `cd services/file-service && npm test` |
| Run all pre-commit hooks | `pre-commit run --all-files` |
| Run microservices load test | `cd loadtests && locust -f locustfile.py --host http://localhost` |
