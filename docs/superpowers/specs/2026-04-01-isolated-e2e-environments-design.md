# Isolated E2E Test Environments — Design Spec

**Date:** 2026-04-01
**Depends on:** [Unified E2E Test Suite](2026-04-01-unified-e2e-test-suite-design.md) (pytest suite, 82 tests)
**Goal:** Wrap the existing e2e test suite with fully isolated, disposable environments so every test run gets a clean slate — no state leakage, no interference with dev environments.

---

## Problem

The e2e test suite currently runs against whatever environment the developer has up (Docker Compose on port 80 or K8s on port 30080). This causes:
- **State pollution** — leftover users, changed passwords, stale data from previous runs break tests
- **Environment interference** — tests modify the dev database, breaking manual testing
- **No reproducibility** — test results depend on what state the dev environment is in

## Solution

Black-box Makefile targets that spin up a clean, isolated environment, run all tests, dump logs, and tear everything down — regardless of success or failure.

```bash
make e2e-docker    # black box Docker Compose (~1-2 min)
make e2e-k8s       # black box K8s via Kind (~10 min)
make e2e-all       # both sequentially
```

---

## Docker Compose E2E Environment

### Override File: `docker-compose.e2e.yml`

A minimal override (~20 lines) that changes only the external ports:

| Service | Dev Port | E2E Port |
|---------|----------|----------|
| Kong | 80 | 8090 |
| Frontend | 3000 | 3090 |

Run with:
```bash
docker compose -p chatbox-e2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build
```

The `-p chatbox-e2e` project name creates fully isolated resources:

| Resource | Dev | E2E | Collision? |
|----------|-----|-----|-----------|
| Container names | `chat-project-final-*` | `chatbox-e2e-*` | No |
| Docker network | `chat-project-final_default` | `chatbox-e2e_default` | No |
| Named volumes (pgdata, uploads) | `chat-project-final_*` | `chatbox-e2e_*` | No |
| Kong port | 80 | 8090 | No |
| Frontend port | 3000 | 3090 | No |
| `.env` file | Shared (read-only) | Shared (read-only) | Acceptable |
| Kong config, init scripts | Shared (read-only) | Shared (read-only) | No |

### Lifecycle

1. `docker compose -p chatbox-e2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build`
2. Poll `http://localhost:8090` until healthy (timeout: 120s)
3. Run `python3 -m pytest tests/e2e/ -v --tb=short -c tests/e2e/pytest.ini` with `KONG_URL=http://localhost:8090`
4. Capture pytest exit code
5. Dump all service logs to `tests/e2e/logs/<timestamp>/`
6. `docker compose -p chatbox-e2e -f docker-compose.yml -f docker-compose.e2e.yml down -v` (always, even on failure)
7. Return pytest exit code

---

## K8s E2E Environment

### Separate Kind Cluster: `chatbox-e2e`

| Resource | Dev Cluster | E2E Cluster |
|----------|------------|-------------|
| Kind cluster name | `chatbox` | `chatbox-e2e` |
| Kong NodePort | 30080 | 31080 |
| Frontend NodePort | 30000 | 31000 |
| Grafana NodePort | 30030 | 31030 |

No collision — Kind clusters are fully isolated Docker containers with separate kubeconfig contexts.

### Lifecycle

1. `kind create cluster --name chatbox-e2e` with inline config mapping ports 31080, 31000, 31030
2. Deploy infra via Helm (Postgres, Redis, Kafka) into the e2e cluster
3. Build Docker images + `kind load docker-image --name chatbox-e2e`
4. Run init jobs + deploy services via kustomize
5. Wait for all pods in `chatbox` namespace to be Ready (timeout: 300s)
6. Run pytest with `KONG_URL=http://localhost:31080`
7. Capture pytest exit code
8. Dump pod logs to `tests/e2e/logs/<timestamp>/`
9. `kind delete cluster --name chatbox-e2e` (always, even on failure)
10. Return pytest exit code

### Build Script Modification

`infra/k8s/scripts/build-images.sh` currently hardcodes `--name chatbox`. The e2e lifecycle script passes `CLUSTER_NAME=chatbox-e2e` as an environment variable. The build script uses `${CLUSTER_NAME:-chatbox}` for the `kind load` command.

---

## Lifecycle Shell Script

**`infra/scripts/e2e-lifecycle.sh`** — single script handling both environments:

```
Usage: infra/scripts/e2e-lifecycle.sh <docker|k8s> [pytest-args...]

Examples:
  infra/scripts/e2e-lifecycle.sh docker              # all tests
  infra/scripts/e2e-lifecycle.sh docker -m smoke      # smoke only
  infra/scripts/e2e-lifecycle.sh k8s                  # all tests
  infra/scripts/e2e-lifecycle.sh docker -k test_auth  # just auth tests
```

### Script Structure

```bash
#!/usr/bin/env bash
set -euo pipefail

MODE=$1; shift
PYTEST_ARGS=("$@")
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
LOG_DIR="tests/e2e/logs/$TIMESTAMP"
EXIT_CODE=0

# Trap: always teardown + dump logs on exit
trap cleanup EXIT

case $MODE in
  docker) docker_up; docker_wait; run_tests; ;;
  k8s)    k8s_up;    k8s_wait;    run_tests; ;;
esac

exit $EXIT_CODE
```

### Functions

**`docker_up`:**
```bash
docker compose -p chatbox-e2e \
  -f docker-compose.yml \
  -f docker-compose.e2e.yml \
  up -d --build
```

**`docker_wait`:** Poll `curl -sf http://localhost:8090` every 3s, timeout 120s.

**`k8s_up`:**
1. Create Kind cluster with inline config (ports 31080, 31000, 31030)
2. Run infra setup (Helm charts)
3. Generate secrets from `.env`
4. Build + load images
5. Run init jobs + deploy

**`k8s_wait`:** Poll `kubectl get pods -n chatbox` until all Running/Completed, timeout 300s. Then poll `curl -sf http://localhost:31080` until Kong responds.

**`run_tests`:**
```bash
KONG_URL=$KONG_URL python3 -m pytest tests/e2e/ -v --tb=short \
  -c tests/e2e/pytest.ini "${PYTEST_ARGS[@]}" || EXIT_CODE=$?
```

**`cleanup`:**
1. Create `$LOG_DIR`
2. If Docker: `docker compose -p chatbox-e2e ... logs > logs/`
3. If K8s: `kubectl logs` for each pod in chatbox namespace
4. If Docker: `docker compose -p chatbox-e2e ... down -v`
5. If K8s: `kind delete cluster --name chatbox-e2e`

---

## Makefile Targets

| Target | Command | Description |
|--------|---------|-------------|
| `make e2e-docker` | `e2e-lifecycle.sh docker` | Black box Docker Compose: up, test all, down |
| `make e2e-k8s` | `e2e-lifecycle.sh k8s` | Black box K8s: create cluster, deploy, test all, delete |
| `make e2e-all` | `e2e-lifecycle.sh docker` then `e2e-lifecycle.sh k8s` | Both sequentially |
| `make e2e-smoke` | `e2e-lifecycle.sh docker -m smoke` | Docker Compose, smoke tests only |
| `make e2e-auth` | `e2e-lifecycle.sh docker -k test_auth` | Docker Compose, auth tests only |
| `make e2e-pm` | `e2e-lifecycle.sh docker -k test_pm` | Docker Compose, PM tests only |
| `make e2e-files` | `e2e-lifecycle.sh docker -k test_files` | Docker Compose, file tests only |
| `make e2e-chat` | `e2e-lifecycle.sh docker -k "test_chat_rooms or test_chat_websocket"` | Docker Compose, chat tests only |
| `make e2e-messages` | `e2e-lifecycle.sh docker -k test_messages` | Docker Compose, message tests only |
| `make e2e-admin` | `e2e-lifecycle.sh docker -k test_admin` | Docker Compose, admin tests only |
| `make e2e-monitoring` | `e2e-lifecycle.sh docker -k test_monitoring` | Docker Compose, monitoring tests only |
| `make e2e-setup` | `pip install -r tests/e2e/requirements.txt` | Install test dependencies (no environment) |

All targets except `e2e-setup` do the full black box lifecycle: up → wait → test → dump logs → down.

---

## conftest.py Changes

Update `_resolve_kong_url()` auto-detection to add the e2e ports:

```
1. KONG_URL env var (set by lifecycle script)
2. localhost:80    (dev Docker Compose)
3. localhost:8090  (e2e Docker Compose)
4. localhost:30080 (dev K8s)
5. localhost:31080 (e2e K8s)
```

In practice, the lifecycle script always sets `KONG_URL` explicitly, so auto-detection is only a fallback for manual runs.

---

## Log Dump

On every run (pass or fail), service logs are saved:

```
tests/e2e/logs/
  2026-04-01_190500/
    auth-service.log
    chat-service.log
    message-service.log
    file-service.log
    kong.log
    frontend.log
```

For K8s runs, pod logs are dumped similarly.

`tests/e2e/logs/` is added to `.gitignore`.

---

## Files Created / Modified

| File | Action |
|------|--------|
| `docker-compose.e2e.yml` | Create — port override for e2e environment |
| `infra/scripts/e2e-lifecycle.sh` | Create — lifecycle orchestrator |
| `infra/k8s/scripts/build-images.sh` | Modify — accept `CLUSTER_NAME` env var |
| `tests/e2e/conftest.py` | Modify — add e2e ports to auto-detection |
| `Makefile` | Modify — replace old targets with new lifecycle targets |
| `.gitignore` | Modify — add `tests/e2e/logs/` |
| `docs/operations/makefile-reference.md` | Modify — update e2e section with new targets |

---

## What This Does NOT Cover

- **CI integration** — running `make e2e-docker` in GitHub Actions (future task)
- **Playwright / UI tests** — future addition, would run against the same Docker Compose e2e environment
- **Parallel execution** — Docker and K8s run sequentially in `e2e-all`, not in parallel (port conflicts if parallelized)
