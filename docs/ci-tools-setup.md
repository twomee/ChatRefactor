# CI Tools Setup Guide

This document explains the CI/CD tools configured for this project, what each one does, and how to maintain them.

## Overview

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

## Tools Explained

### 1. CodeQL (GitHub's SAST Scanner)

**What it does:** Scans your actual source code for security vulnerabilities. Unlike Trivy (which checks dependencies), CodeQL analyzes your code logic for patterns like SQL injection, cross-site scripting (XSS), path traversal, and insecure cryptography.

**Where results appear:**
- GitHub Security tab
- Annotations directly on PR diffs (highlights the vulnerable line)

**Configuration file:** `.github/workflows/codeql.yml`

**When it runs:** On push to main and every Monday at 10:00 AM UTC. It does NOT run on PRs (to keep PR checks fast).

**Languages scanned:** Python, Go, JavaScript/TypeScript

**What to do when it finds something:** Fix the vulnerability before deploying. CodeQL findings are real security issues, not style complaints.

---

### 2. SonarCloud (Code Quality)

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

### 3. Codecov (Coverage Tracking)

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

### 4. Trivy (Vulnerability Scanner)

**What it does:** Two types of scanning:

1. **Filesystem scan** (runs on every PR) - Scans `package.json`, `requirements.txt`, `go.mod`, etc. for dependencies with known CVEs.
2. **Docker image scans** (runs on push to main + weekly) - Builds each Docker image and scans it for vulnerabilities in the OS packages, runtime, and bundled dependencies.

**Configuration file:** `.github/workflows/security.yml`

**Severity filter:** Only fails on `CRITICAL` and `HIGH` severity. Lower severities are ignored. Only vulnerabilities with available fixes are flagged (`ignore-unfixed: true`).

**What to do when it finds something:**
- Check which package has the CVE
- Update the package version (usually a patch bump fixes it)
- For Docker base image vulnerabilities, update the base image version

---

### 5. Gitleaks (Secret Scanner)

**What it does:** Scans every commit for accidentally committed secrets like API keys, passwords, tokens, and private keys.

**Configuration file:** `.github/workflows/secrets.yml` and `.pre-commit-config.yaml` (also runs as a pre-commit hook locally)

**What to do when it finds something:** Rotate the exposed secret immediately. Removing it from git history is not enough because the secret was already pushed.

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

## How the CI Pipeline Works Per Service

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

---

## Common Tasks

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
