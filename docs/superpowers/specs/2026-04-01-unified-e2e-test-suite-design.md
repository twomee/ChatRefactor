# Unified E2E Test Suite — Design Spec

**Date:** 2026-04-01
**Goal:** Replace the bash e2e script with a pytest suite that covers all 85 features and runs against both Docker Compose and Kubernetes with a single `make e2e` command.

---

## Problem

- The current `infra/k8s/scripts/e2e-test.sh` covers ~11% of features (46 tests across 8 sections)
- It only works against K8s (reads admin creds from `kubectl get secret`)
- Every feature change requires manual testing in both Docker Compose and K8s
- Bash + `python3 -c` one-liners for JSON parsing is fragile at scale

## Solution

A pytest-based e2e suite that:
- Auto-detects which environment is running (Docker Compose on port 80, K8s on port 30080)
- Resolves admin credentials via a chain: env vars → `secrets.env` → `kubectl` → defaults
- Covers all 85 user-facing features
- Supports smoke test subset (`pytest -m smoke`, ~15 tests)
- Replaces the old bash script entirely

---

## Project Structure

```
tests/e2e/
  conftest.py              # fixtures, URL detection, credential resolution
  requirements.txt         # pytest, requests, websockets, pyotp
  test_frontend.py         # 2 tests
  test_auth.py             # 14 tests
  test_chat_rooms.py       # 12 tests
  test_chat_websocket.py   # 11 tests
  test_pm.py               # 11 tests
  test_messages.py         # 12 tests
  test_files.py            # 9 tests
  test_admin.py            # 8 tests
  test_monitoring.py       # 5 tests (skipped if Grafana unreachable)
```

Pytest configuration added to `pyproject.toml` or `pytest.ini` at project root:

```ini
[pytest]
markers =
    smoke: core tests matching the old e2e-test.sh coverage (~15 tests)
    monitoring: requires Grafana/Prometheus (auto-skipped if unreachable)
testpaths = tests/e2e
```

---

## conftest.py — Fixtures & Configuration

### URL Auto-Detection

Resolution order:
1. `KONG_URL` env var → use it directly
2. Probe `http://localhost:80` → Docker Compose
3. Probe `http://localhost:30080` → K8s
4. Neither responds → `pytest.exit("No environment running. Start with 'make deploy' or 'make k8s-setup-local'")`

WS URL derived automatically: replace `http://` with `ws://` from the resolved Kong URL.

### Credential Resolution Chain

Resolution order for admin username/password:
1. `ADMIN_USER` / `ADMIN_PASSWORD` env vars
2. Parse `infra/k8s/secrets.env` (looks for `ADMIN_USERNAME` and `ADMIN_PASSWORD`)
3. `kubectl get secret auth-admin-secret` (K8s only, silently skipped if kubectl fails)
4. Hardcoded defaults: `admin` / `changeme`

### Session-Scoped Fixtures (created once per run)

| Fixture | What it does |
|---------|-------------|
| `kong_url` | Resolved Kong base URL |
| `ws_url` | Derived WebSocket URL |
| `api` | `requests.Session` with Kong base URL |
| `admin_token` | Credential chain → login → JWT token |
| `user1` | Register + login → `{"username": "alice_<ts>", "token": "..."}` |
| `user2` | Register + login → `{"username": "bob_<ts>", "token": "..."}` |
| `test_room` | Admin creates room → `{"id": "...", "name": "testroom_<ts>"}` |

### Module-Scoped Fixtures (per test file)

Each file creates its own test data (messages, files, etc.) so tests don't leak across files. Example: `test_messages.py` has a `sent_message` fixture that sends a message and returns its ID for edit/delete/reaction tests.

---

## Test Coverage — 85 Tests

### test_frontend.py (2 tests)

| Test | Smoke |
|------|-------|
| Frontend returns 200 | YES |
| Response contains HTML | YES |

### test_auth.py (14 tests)

| Test | Smoke |
|------|-------|
| Register new user → 201 | YES |
| Duplicate register → 409 | YES |
| Login → 200 + JWT token | YES |
| Wrong password → 401 | |
| Ping with valid token → 200 | |
| Ping without token → 401 | |
| Get profile → returns username, email | |
| Update email → 200 | |
| Update password → 200, login with new password works | |
| Forgot password → 200 (endpoint accepts request) | |
| 2FA setup → returns QR secret | |
| 2FA verify + login with TOTP → 200 | |
| Logout → user disappears from online users immediately | |
| Logout → user retains room admin role (re-login → still admin) | |

### test_chat_rooms.py (12 tests)

| Test | Smoke |
|------|-------|
| List rooms → 200, has default rooms | YES |
| Admin creates room → 201 | YES |
| Regular user create room → 403 | |
| Get room users → 200 | |
| Admin mutes user → user's message blocked | |
| Admin unmutes user → user can send again | |
| Admin kicks muted user → user rejoins → still muted | |
| Admin kicks user → success | |
| Admin promotes user to room admin → success | |
| Admin removes room admin → success | |
| Set room inactive → success | |
| Non-admin room actions → 403 | |

### test_chat_websocket.py (11 tests)

| Test | Smoke |
|------|-------|
| Connect to lobby WebSocket | YES |
| Connect to room WebSocket (requires lobby first) | YES |
| Send message → broadcast received | |
| Typing indicator → broadcast received (not echoed to sender) | |
| Edit message via WebSocket → update broadcast | |
| Delete message via WebSocket → delete broadcast | |
| Add reaction via WebSocket → broadcast | |
| Remove reaction via WebSocket → broadcast | |
| Clear room message history → messages no longer returned | |
| Refresh (disconnect + reconnect) → no leave/join broadcast | |
| Refresh → admin role preserved (no auto-promotion to other user) | |

### test_pm.py (11 tests)

| Test | Smoke |
|------|-------|
| Send PM → recipient receives via lobby WebSocket | |
| PM typing indicator → recipient receives | |
| Edit PM → 200 | |
| Delete PM → 200 | |
| Add PM reaction → 200 | |
| Remove PM reaction → 200 | |
| PM history → returns conversation | |
| Delete PM conversation → 200 | |
| Get deleted conversations → includes deleted | |
| PM file upload → 201 + recipient notified | |
| Remove DM user from sidebar panel → conversation hidden | |

### test_messages.py (12 tests)

| Test | Smoke |
|------|-------|
| Get room history → 200, returns array | YES |
| Replay with `?since=` → 200 | YES |
| History without auth → 401 | |
| Edit message → 200, content updated | |
| Delete message → 200, soft-deleted | |
| Get reactions for message → 200 | |
| Search messages → returns matches | |
| Message context (`?message_id=&before=&after=`) → 200 | |
| PM history endpoint → 200 | |
| PM context endpoint → 200 | |
| Clear room history → 200 | |
| Link preview → returns OG metadata | |

### test_files.py (9 tests)

| Test | Smoke |
|------|-------|
| Upload file to room → 201 | YES |
| List room files → includes uploaded file | YES |
| Download file → correct content | YES |
| Upload without auth → 401 | |
| Upload PM file → 201 | |
| List files for PM → includes file | |
| Download PM file → correct content | |
| Upload invalid file type → rejected | |
| Upload image → response includes image metadata for rendering | |

### test_admin.py (8 tests)

| Test | Smoke |
|------|-------|
| List all rooms (including inactive) → 200 | |
| List online users → 200 | |
| Close specific room → success | |
| Open specific room → success | |
| Close all rooms → success | |
| Open all rooms → success | |
| Promote user to global admin → success | |
| Non-admin access → 403 | |

### test_monitoring.py (5 tests, all auto-skipped if Grafana unreachable)

| Test | Smoke |
|------|-------|
| Grafana health → 200, database ok | |
| Grafana has datasources | |
| Prometheus healthy | |
| Prometheus active targets > 0 | |
| Prometheus scraping chatbox metrics | |

---

## Makefile Targets

| Target | What it does |
|--------|-------------|
| `make e2e` | Auto-detect environment, run all 85 tests |
| `make e2e-smoke` | Quick subset (~15 core tests) |
| `make e2e-all` | Run against Docker Compose then K8s, combined report |
| `make e2e KONG_URL=http://custom:8080` | Explicit URL override |
| `make e2e-auth` | Run only auth tests |
| `make e2e-pm` | Run only PM tests |
| `make e2e-files` | Run only file tests |
| `make e2e-setup` | `pip install -r tests/e2e/requirements.txt` |

### `make e2e-all` behavior

1. Probe port 80 → if up, run full suite against Docker Compose
2. Probe port 30080 → if up, run full suite against K8s
3. Print combined summary
4. If only one is running, run that one and warn the other isn't available

---

## Dependencies

`tests/e2e/requirements.txt`:

```
pytest>=8.0
requests>=2.31
websockets>=12.0
pyotp>=2.9
```

---

## Old Script Removal

- Delete `infra/k8s/scripts/e2e-test.sh`
- Update `docs/operations/makefile-reference.md` — add new e2e section, update old e2e-test.sh reference
- Update `docs/operations/kubernetes-commands.md` — update e2e-test.sh reference to point to new pytest suite

No md files are deleted. References are updated in place.

---

## What This Does NOT Cover

- **CI integration** — running e2e in GitHub Actions (requires Docker Compose in CI). Separate task.
- **Adding monitoring to Docker Compose** — monitoring tests skip when Grafana is unavailable.
- **Load testing** — Locust setup already exists separately.
- **Unit tests** — per-service pytest suites are separate and unchanged.
