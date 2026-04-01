# cHATBOX Development Workflow

This guide explains every tool we use to build, test, and maintain ChatBox.
No prior DevOps knowledge needed.

---

## Table of Contents

1. [The Big Picture](#the-big-picture)
2. [Jira — Task Tracking](#jira--task-tracking)
3. [Confluence — Documentation](#confluence--documentation)
4. [GitHub — Code Storage](#github--code-storage)
5. [GitHub Actions — Automated Pipelines](#github-actions--automated-pipelines)
6. [CodeQL — Static Security Analysis](#codeql--static-security-analysis)
7. [SonarCloud — Code Quality](#sonarcloud--code-quality)
8. [Codecov — Coverage Tracking](#codecov--coverage-tracking)
9. [Ruff — Python Linter](#ruff--python-linter)
10. [ESLint — JavaScript Linter](#eslint--javascript-linter)
11. [pytest + Coverage — Testing](#pytest--coverage--testing)
12. [Coverage Thresholds](#coverage-thresholds)
13. [Trivy — Security Scanner](#trivy--security-scanner)
14. [Gitleaks — Secret Scanner](#gitleaks--secret-scanner)
15. [Dependabot — Dependency Updates](#dependabot--dependency-updates)
16. [Pre-commit Hooks — Local Safety Net](#pre-commit-hooks--local-safety-net)
17. [Branch Protection](#branch-protection)
18. [How It All Works Together](#how-it-all-works-together)
19. [Microservices CI/CD](#microservices-cicd)
20. [Common Troubleshooting Tasks](#common-troubleshooting-tasks)

---

## The Big Picture

When you write code and push it, a bunch of tools run automatically to make sure
your code is clean, secure, tested, and doesn't break anything. You don't have to
run them manually — they just work.

```
You write code (in one of 4 microservices or the frontend)
    |
    v
git commit --> pre-commit hooks catch problems BEFORE the code leaves your machine
    |
    v
git push + open PR --> GitHub Actions run in the cloud:
    |                    - Is the code formatted correctly? (Ruff, golangci-lint, ESLint)
    |                    - Do the service's tests pass? (pytest, go test, Vitest)
    |                    - Is 50%+ of the code covered by tests?
    |                    - Are there security vulnerabilities? (Trivy)
    |                    - Are there leaked secrets? (Gitleaks)
    |                    - Does the Docker image build? (docker build)
    |
    v
All checks green? --> Safe to merge into main
    |
    v
Every Monday --> Dependabot checks if any dependencies are outdated or vulnerable
```

> **Key difference from monolith:** Each microservice has its own CI pipeline that only triggers when that service's code changes. A change to auth-service doesn't trigger chat-service tests.

When you open a Pull Request, these checks run automatically:

| Tool | What It Does | Runs On |
|------|-------------|---------|
| **Service CI** (lint + test + docker build) | Checks your code compiles, passes tests, and the Docker image builds | PRs that change that service |
| **Trivy Filesystem Scan** | Scans dependencies for known security vulnerabilities (CVEs) | Every PR |
| **SonarCloud** | Analyzes code quality: bugs, code smells, duplication, security hotspots | Every PR |
| **Gitleaks** | Scans for accidentally committed secrets (API keys, passwords) | Every PR |
| **CodeQL** | Deep static security analysis (SQL injection, XSS, etc.) | Push to main + weekly |
| **Trivy Docker Image Scans** | Scans built Docker images for OS-level and dependency vulnerabilities | Push to main + weekly |
| **Codecov** | Tracks test coverage over time, shows coverage diff on PRs | Every PR (via service CIs) |

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

### Per-Service CI Pipelines
Each microservice has its own pipeline that only runs when its code changes. See [Microservices CI/CD](#microservices-cicd) for details.

### Legacy Monolith CI Pipeline (`.github/workflows/ci.yml`)
Runs on changes to `v1/backend/` or `frontend/`.

| Job | What it does | Time |
|-----|-------------|------|
| Backend Lint | Checks Python code style with Ruff | ~6s |
| Backend Tests | Runs legacy monolith tests, checks 50%+ coverage | ~20s |
| Frontend Lint | Checks JavaScript code style with ESLint | ~7s |
| Frontend Build | Makes sure the React app compiles | ~10s |
| Docker Build | Makes sure Docker images build | ~40s |

### Security Scan (`.github/workflows/security.yml`)
Runs on every PR, push to main, and every Monday.

| Job | What it does |
|-----|-------------|
| Trivy Code Scan | Scans your code dependencies for known security vulnerabilities |
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

## CodeQL — Static Security Analysis

**What it does:** Scans your actual source code for security vulnerabilities. Unlike Trivy (which checks dependencies), CodeQL analyzes your code logic for patterns like SQL injection, cross-site scripting (XSS), path traversal, and insecure cryptography.

**Where results appear:**
- GitHub Security tab
- Annotations directly on PR diffs (highlights the vulnerable line)

**Configuration file:** `.github/workflows/codeql.yml`

**When it runs:** On push to main and every Monday at 10:00 AM UTC. It does NOT run on PRs (to keep PR checks fast).

**Languages scanned:** Python, Go, JavaScript/TypeScript

**What to do when it finds something:** Fix the vulnerability before deploying. CodeQL findings are real security issues, not style complaints.

---

## SonarCloud — Code Quality

**What it does:** Analyzes your code for:
- **Bugs** - Logic errors that will cause incorrect behavior
- **Code Smells** - Patterns that make code harder to maintain
- **Duplication** - Copy-pasted code that should be refactored
- **Security Hotspots** - Code that needs manual review for security

**Where results appear:**
- PR check status (pass/fail based on quality gate)
- SonarCloud dashboard: https://sonarcloud.io/project/overview?id=twomee_ChatRefactor

**Configuration files:**
- `.github/workflows/sonarcloud.yml` - The workflow
- `sonar-project.properties` - What to scan, what to exclude

**Secrets required:** `SONAR_TOKEN` (repository secret in GitHub Settings > Secrets > Actions)

**Important setting:** Automatic Analysis must be **OFF** on SonarCloud (Project > Administration > Analysis Method). Our CI workflow handles analysis instead.

### SonarCloud Dashboard Walkthrough

When you open https://sonarcloud.io/project/overview?id=twomee_ChatRefactor, you will see:

**Main Dashboard:**
- **Quality Gate** - Pass/Fail indicator. This is the overall health of your project. A "Passed" quality gate means your code meets all configured quality thresholds.
- **Bugs** - Code that is demonstrably wrong (will cause incorrect behavior at runtime). Fix these first.
- **Vulnerabilities** - Security issues in your code (not dependencies — that is Trivy's job).
- **Code Smells** - Code that works but is hard to maintain. Examples: too-complex functions, unused variables, duplicated logic.
- **Coverage** - Test coverage percentage (if configured to ingest coverage reports).
- **Duplications** - Percentage of code that is copy-pasted elsewhere.

**PR Analysis:**
When you open a PR, SonarCloud analyzes only the NEW code in that PR. It shows:
- How many new bugs/vulnerabilities/code smells the PR introduces
- Whether the new code meets the quality gate
- This means old code is not penalized — only new code must meet the standards

**Key Pages:**
- **Issues** tab - List of all bugs, vulnerabilities, and code smells with file/line references
- **Security Hotspots** - Code that SonarCloud flagged for manual security review (not necessarily a bug, but worth checking)
- **Measures** tab - Detailed metrics (complexity, duplication, coverage per file)
- **Activity** tab - History of quality gate status over time

**Quality Gate:**
The quality gate is a set of conditions that must ALL pass. The default SonarCloud quality gate ("Sonar way") requires:
- No new bugs
- No new vulnerabilities
- New code coverage >= 80%
- New code duplication <= 3%

You can customize this in SonarCloud under Project > Administration > Quality Gates.

---

## Codecov — Coverage Tracking

**What it does:** Collects test coverage reports from all services and shows:
- Total coverage percentage per service
- Coverage diff on each PR (did this PR increase or decrease coverage?)
- Per-file coverage breakdown

**Where results appear:** Comment on each PR showing coverage changes.

**How it works:** Each service CI workflow runs tests with coverage enabled, then uploads the report to Codecov. Coverage is tagged per service using "flags":
- `auth-service`
- `chat-service`
- `message-service`
- `file-service`
- `frontend`
- `legacy-backend`

**Setup:** Install the Codecov GitHub App at https://github.com/apps/codecov. No token needed for public repos.

---

## Ruff — Python Linter

**What:** A tool that checks your Python code for bugs, style issues, and
formatting problems. Think of it as a spell-checker for code.

**Config:** Each Python service has its own `ruff.toml`:
- `services/auth-service/ruff.toml`
- `services/message-service/ruff.toml`
- `v1/backend/ruff.toml` (legacy monolith)

**What it catches:**
- Unused imports and variables
- Unsorted imports
- Common bugs (e.g., unused loop variables)
- Security issues (e.g., hardcoded passwords)
- Code that could be simpler

**How to use locally:**
```bash
# For a specific service
cd services/auth-service    # or services/message-service

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

## Testing — Per-Service

**What:** Each microservice has its own test suite using the standard framework for its language.

**Our stats (per service):**

| Service | Framework | Coverage |
|---------|-----------|---------|
| Auth Service (Python) | pytest + pytest-asyncio | 90%+ |
| Chat Service (Go) | go test | 95%+ |
| Message Service (Python) | pytest + pytest-asyncio | 85%+ |
| File Service (Node.js) | Vitest | — |

CI fails if coverage drops below 50% for any service.

**How to run locally:**
```bash
# Auth service (Python)
cd services/auth-service
pytest tests/ -v --cov=app

# Chat service (Go)
cd services/chat-service
go test ./... -v -cover

# Message service (Python)
cd services/message-service
pytest tests/ -v --cov=app

# File service (Node.js/TypeScript)
cd services/file-service
npm test
npm run test:coverage
```

**What the coverage number means:**
- 90% = 90% of your code lines are executed during tests
- The rest are edge cases, error handlers, or code paths not yet tested
- 50% minimum is enforced in CI — if you add code without tests, it might fail

---

## Coverage Thresholds

Each service has a minimum test coverage threshold. If coverage drops below this, CI fails.

| Service | Threshold | Current Coverage |
|---------|-----------|-----------------|
| Auth Service | 95% | ~99% |
| Message Service | 95% | ~98% |
| Chat Service | 85% | ~87% |
| File Service | 90% (statements, functions, lines), 80% (branches) | ~93% |
| Frontend | No threshold enforced | ~31% |
| Legacy Backend (v1) | 50% | ~50% |

**Where thresholds are configured:**
- Python services: `--cov-fail-under=XX` in the CI workflow YAML
- Go service: Shell script in `ci-chat.yml` that checks the coverage percentage
- File service: `thresholds` in `services/file-service/vitest.config.ts`

---

## Trivy — Security Scanner

**What:** Scans your code and Docker images for known security vulnerabilities (CVEs).
A CVE is a publicly known security bug in a library or system package.

**Two types of scanning:**

1. **Filesystem scan** (runs on every PR) - Scans `package.json`, `requirements.txt`, `go.mod`, etc. for dependencies with known CVEs.
2. **Docker image scans** (runs on push to main + weekly) - Builds each Docker image and scans it for vulnerabilities in the OS packages, runtime, and bundled dependencies.

**Configuration file:** `.github/workflows/security.yml`

**Severity filter:** Only fails on `CRITICAL` and `HIGH` severity. Lower severities are ignored. Only vulnerabilities with available fixes are flagged (`ignore-unfixed: true`).

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

**What to do when it finds something:**
- Check which package has the CVE
- Update the package version (usually a patch bump fixes it)
- For Docker base image vulnerabilities, update the base image version

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

**Configuration file:** `.github/workflows/secrets.yml` and `.pre-commit-config.yaml` (also runs as a pre-commit hook locally)

**How it works:**
1. **Pre-commit hook** (local) — blocks the commit before it happens
2. **GitHub Action** (cloud) — scans every PR as a safety net

**What to do when it finds something:** Rotate the exposed secret immediately. Removing it from git history is not enough because the secret was already pushed.

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

## Branch Protection

The `main` branch is protected by a GitHub ruleset ("Protect main"):

| Rule | Effect |
|------|--------|
| No direct push | All changes must go through a Pull Request |
| No branch deletion | Nobody can delete main |
| No force push | Nobody can rewrite main's history |
| CodeQL gate | PRs cannot merge if CodeQL finds high/critical vulnerabilities |
| Admin bypass | Only the repo owner can merge PRs |

**Where configured:** GitHub Settings > Rules > Rulesets > "Protect main"

---

## How It All Works Together

Here's the full flow from writing code to merging (using auth-service as an example):

```
1. CREATE TICKET
   Go to Jira, create a ticket (e.g., KAN-21)

2. CREATE BRANCH
   git checkout -b KAN-21-auth-rate-limiting

3. WRITE CODE
   Edit files in services/auth-service/

4. COMMIT
   git add . && git commit -m "KAN-21 add rate limiting to login endpoint"
   |
   --> Pre-commit hooks run automatically:
       [gitleaks]  no secrets found           OK
       [ruff]      auto-fixed 1 import        OK
   |
   Commit created!

5. PUSH + OPEN PR
   git push -u origin KAN-21-auth-rate-limiting
   Open PR on GitHub
   |
   --> ONLY ci-auth.yml triggers (not chat, message, or file service CI):
       [Auth Lint]         ruff check passed       OK
       [Auth Tests]        45 passed, 91% cov      OK
       [Auth Docker]       image built              OK
   |
   --> Repo-wide pipelines also trigger:
       [Trivy]             no CVEs found            OK
       [Gitleaks]          no secrets found         OK

6. MERGE
   All checks green --> merge PR
   Only auth-service needs redeployment

7. WEEKLY MAINTENANCE (automatic)
   Monday: Dependabot creates PRs for outdated deps across all 8 directories
   Monday: Trivy re-scans for newly discovered CVEs
```

---

## Quick Reference

| I want to... | Command |
|--------------|---------|
| Lint auth service | `cd services/auth-service && ruff check .` |
| Lint chat service | `cd services/chat-service && golangci-lint run ./...` |
| Lint message service | `cd services/message-service && ruff check .` |
| Lint file service | `cd services/file-service && npm run lint` |
| Lint frontend | `cd frontend && npm run lint` |
| Test auth service | `cd services/auth-service && pytest tests/ -v` |
| Test chat service | `cd services/chat-service && go test ./... -v` |
| Test message service | `cd services/message-service && pytest tests/ -v` |
| Test file service | `cd services/file-service && npm test` |
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

### How the CI Pipeline Works Per Service

Each microservice has its own CI workflow that only runs when files in that service change:

```
services/auth-service/**  -->  .github/workflows/ci-auth.yml
services/chat-service/**  -->  .github/workflows/ci-chat.yml
services/message-service/** --> .github/workflows/ci-message.yml
services/file-service/**  -->  .github/workflows/ci-file.yml
v1/** or frontend/**      -->  .github/workflows/ci.yml
```

Each workflow runs three jobs in sequence:
1. **Lint** - Code style and formatting checks
2. **Test** - Run test suite with coverage
3. **Docker Build** - Verify the Docker image builds (only if lint and tests pass)

After the test step, coverage is uploaded to Codecov.

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

---

## Common Troubleshooting Tasks

### "A Dependabot PR has failing checks"

Dependabot PRs may fail if the workflow files on their branch are outdated. Fix by commenting `@dependabot rebase` on the PR. This rebases it onto the latest main.

### "Trivy found a CVE in a Docker image"

1. Check which package/base image has the vulnerability
2. Update the version in the Dockerfile or dependency file
3. The fix will be verified on the next push to main

### "SonarCloud says Project not found"

1. Verify `SONAR_TOKEN` exists as a **Repository secret** (not Environment secret) in GitHub Settings > Secrets > Actions
2. Verify Automatic Analysis is **OFF** on SonarCloud (Project > Administration > Analysis Method)
3. Verify `sonar.organization` and `sonar.projectKey` in `sonar-project.properties` match your SonarCloud project

### "Coverage dropped below the threshold"

1. Write more tests for the uncovered code
2. Or temporarily lower the threshold (not recommended - fix the tests instead)
3. Check which files lost coverage: `go tool cover -func=coverage.out` (Go) or look at the Codecov PR comment

### "I want to add a new service"

1. Create a new CI workflow at `.github/workflows/ci-<service>.yml` following the pattern of existing ones
2. Add a Codecov upload step with a new flag name
3. Add a Trivy image scan job in `security.yml`
4. Add the service's source/test directories to `sonar-project.properties`
5. Add a Dependabot config entry in `.github/dependabot.yml`
