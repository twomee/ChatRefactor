# Isolated E2E Environments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the e2e test suite with disposable, isolated environments — `make e2e-docker` spins up a clean Docker Compose env, runs tests, dumps logs, tears down. `make e2e-k8s` does the same with a Kind cluster. `make e2e-all` runs both.

**Architecture:** A `docker-compose.e2e.yml` override changes ports (Kong 8090, Frontend 3090). A `infra/scripts/e2e-lifecycle.sh` script orchestrates up → wait → test → logs → down for both Docker and K8s. Makefile targets call the lifecycle script.

**Tech Stack:** Docker Compose, Kind, bash, existing pytest suite

---

## File Map

| File | Responsibility |
|------|---------------|
| `docker-compose.e2e.yml` | Port overrides for isolated Docker Compose environment |
| `infra/scripts/e2e-lifecycle.sh` | Lifecycle orchestrator: up → wait → test → logs → down |
| `infra/k8s/scripts/build-images.sh` | Modified to accept CLUSTER_NAME env var |
| `tests/e2e/conftest.py` | Add e2e ports to auto-detection fallback |
| `Makefile` | Replace old e2e targets with lifecycle-based targets |
| `.gitignore` | Add tests/e2e/logs/ |
| `docs/operations/makefile-reference.md` | Update e2e docs with new targets |

---

### Task 1: Docker Compose Override File

**Files:**
- Create: `docker-compose.e2e.yml`

- [ ] **Step 1: Create docker-compose.e2e.yml**

```yaml
# docker-compose.e2e.yml — Port overrides for isolated e2e environment.
# Usage: docker compose -p chatbox-e2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build

services:
  kong:
    ports:
      - "8090:8000"

  frontend:
    ports:
      - "3090:80"
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.e2e.yml
git commit -m "feat(e2e): add Docker Compose override for isolated e2e environment"
```

---

### Task 2: Lifecycle Script

**Files:**
- Create: `infra/scripts/e2e-lifecycle.sh`

- [ ] **Step 1: Create the lifecycle script**

```bash
#!/usr/bin/env bash
# e2e-lifecycle.sh — Black-box e2e: spin up clean env → test → dump logs → tear down
#
# Usage: infra/scripts/e2e-lifecycle.sh <docker|k8s> [pytest-args...]
# Examples:
#   infra/scripts/e2e-lifecycle.sh docker              # all tests, Docker Compose
#   infra/scripts/e2e-lifecycle.sh docker -m smoke      # smoke tests only
#   infra/scripts/e2e-lifecycle.sh k8s                  # all tests, Kind cluster
#   infra/scripts/e2e-lifecycle.sh docker -k test_auth  # auth tests only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
K8S_DIR="$PROJECT_ROOT/infra/k8s"

MODE="${1:?Usage: e2e-lifecycle.sh <docker|k8s> [pytest-args...]}"
shift
PYTEST_ARGS=("$@")

TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
LOG_DIR="$PROJECT_ROOT/tests/e2e/logs/$TIMESTAMP"
EXIT_CODE=0
ENV_UP=false

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

step()    { echo -e "\n${YELLOW}══ $1${NC}"; }
success() { echo -e "${GREEN}✓ $1${NC}"; }
fail()    { echo -e "${RED}✗ $1${NC}"; }

# ── Docker Compose helpers ───────────────────────────────────────────────────
COMPOSE_CMD="docker compose -p chatbox-e2e -f $PROJECT_ROOT/docker-compose.yml -f $PROJECT_ROOT/docker-compose.e2e.yml"

docker_up() {
    step "Starting Docker Compose e2e environment..."
    $COMPOSE_CMD up -d --build --quiet-pull
    ENV_UP=true
    success "Containers started"
}

docker_wait() {
    step "Waiting for services to be healthy..."
    local timeout=120
    local elapsed=0
    while ! curl -sf http://localhost:8090 > /dev/null 2>&1; do
        if [ "$elapsed" -ge "$timeout" ]; then
            fail "Timed out waiting for Kong on port 8090 after ${timeout}s"
            exit 1
        fi
        sleep 3
        elapsed=$((elapsed + 3))
        echo -n "."
    done
    echo ""
    success "Kong responding on port 8090 (${elapsed}s)"
}

docker_logs() {
    step "Dumping service logs to $LOG_DIR..."
    mkdir -p "$LOG_DIR"
    for svc in auth-service chat-service message-service file-service kong frontend; do
        $COMPOSE_CMD logs "$svc" > "$LOG_DIR/$svc.log" 2>&1 || true
    done
    success "Logs saved to $LOG_DIR"
}

docker_down() {
    step "Tearing down Docker Compose e2e environment..."
    $COMPOSE_CMD down -v --remove-orphans 2>/dev/null || true
    success "Environment destroyed"
}

# ── K8s helpers ──────────────────────────────────────────────────────────────
E2E_CLUSTER="chatbox-e2e"
E2E_KONG_PORT=31080
E2E_FRONTEND_PORT=31000
E2E_GRAFANA_PORT=31030

k8s_up() {
    step "Creating Kind cluster '$E2E_CLUSTER'..."

    # Delete stale cluster if it exists
    if kind get clusters 2>/dev/null | grep -q "^${E2E_CLUSTER}$"; then
        echo "  Stale cluster found, deleting..."
        kind delete cluster --name "$E2E_CLUSTER"
    fi

    kind create cluster --name "$E2E_CLUSTER" --config - <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: $E2E_KONG_PORT
        hostPort: $E2E_KONG_PORT
        protocol: TCP
      - containerPort: $E2E_FRONTEND_PORT
        hostPort: $E2E_FRONTEND_PORT
        protocol: TCP
      - containerPort: $E2E_GRAFANA_PORT
        hostPort: $E2E_GRAFANA_PORT
        protocol: TCP
EOF
    ENV_UP=true
    success "Kind cluster created"

    step "Setting kubectl context..."
    kubectl cluster-info --context "kind-${E2E_CLUSTER}" > /dev/null

    step "Creating namespaces..."
    kubectl apply -f "$K8S_DIR/base/namespace.yaml"
    kubectl apply -f "$K8S_DIR/infra/namespace.yaml"

    step "Installing infrastructure (Helm)..."
    local SECRETS_FILE="$K8S_DIR/secrets.env"
    if [ ! -f "$SECRETS_FILE" ]; then
        SECRETS_FILE="$K8S_DIR/base/secrets.env.example"
    fi
    source "$SECRETS_FILE"

    helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
    helm repo update --quiet

    echo "  Installing PostgreSQL..."
    helm upgrade --install postgres bitnami/postgresql \
        --namespace chatbox-infra \
        --values "$K8S_DIR/infra/helm-values/postgres.yaml" \
        --set auth.postgresPassword="$POSTGRES_PASSWORD" \
        --set auth.password="$POSTGRES_PASSWORD" \
        --version 18.5.14 \
        --wait --timeout 180s

    echo "  Installing Redis..."
    helm upgrade --install redis bitnami/redis \
        --namespace chatbox-infra \
        --values "$K8S_DIR/infra/helm-values/redis.yaml" \
        --set auth.password="$REDIS_PASSWORD" \
        --version 25.3.9 \
        --wait --timeout 120s

    echo "  Installing Kafka..."
    kubectl apply -f "$K8S_DIR/infra/kafka.yaml"
    kubectl rollout status deployment/kafka --namespace chatbox-infra --timeout=120s

    step "Applying secrets..."
    bash "$K8S_DIR/scripts/generate-secrets.sh"

    step "Running init jobs..."
    kubectl delete job db-init --namespace chatbox --ignore-not-found
    kubectl delete job kafka-init --namespace chatbox --ignore-not-found
    kubectl apply -f "$K8S_DIR/jobs/db-init-job.yaml"
    kubectl apply -f "$K8S_DIR/jobs/kafka-init-job.yaml"
    kubectl wait --for=condition=complete job/db-init --namespace chatbox --timeout=120s
    kubectl wait --for=condition=complete job/kafka-init --namespace chatbox --timeout=120s

    step "Building and loading Docker images..."
    CLUSTER_NAME="$E2E_CLUSTER" bash "$K8S_DIR/scripts/build-images.sh"

    step "Deploying application..."
    kubectl apply -k "$K8S_DIR/overlays/dev"
    success "K8s deployment complete"
}

k8s_wait() {
    step "Waiting for pods to be ready..."
    local timeout=300
    local elapsed=0
    while true; do
        local not_ready
        not_ready=$(kubectl get pods -n chatbox --no-headers 2>/dev/null \
            | grep -v Completed \
            | grep -v Running || true)
        if [ -z "$not_ready" ] && kubectl get pods -n chatbox --no-headers 2>/dev/null | grep -q Running; then
            break
        fi
        if [ "$elapsed" -ge "$timeout" ]; then
            fail "Timed out waiting for pods after ${timeout}s"
            kubectl get pods -n chatbox
            exit 1
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        echo -n "."
    done
    echo ""
    success "All pods running"

    # Wait for Kong to respond
    elapsed=0
    while ! curl -sf "http://localhost:${E2E_KONG_PORT}" > /dev/null 2>&1; do
        if [ "$elapsed" -ge 60 ]; then
            fail "Kong not responding on port ${E2E_KONG_PORT}"
            exit 1
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    success "Kong responding on port ${E2E_KONG_PORT}"
}

k8s_logs() {
    step "Dumping pod logs to $LOG_DIR..."
    mkdir -p "$LOG_DIR"
    for pod in $(kubectl get pods -n chatbox --no-headers -o custom-columns=":metadata.name" 2>/dev/null); do
        kubectl logs "$pod" -n chatbox > "$LOG_DIR/$pod.log" 2>&1 || true
    done
    success "Logs saved to $LOG_DIR"
}

k8s_down() {
    step "Deleting Kind cluster '$E2E_CLUSTER'..."
    kind delete cluster --name "$E2E_CLUSTER" 2>/dev/null || true
    success "Cluster deleted"
}

# ── Test runner ──────────────────────────────────────────────────────────────
run_tests() {
    local kong_url="$1"
    step "Running e2e tests against $kong_url..."
    KONG_URL="$kong_url" python3 -m pytest "$PROJECT_ROOT/tests/e2e/" \
        -v --tb=short -c "$PROJECT_ROOT/tests/e2e/pytest.ini" \
        "${PYTEST_ARGS[@]}" || EXIT_CODE=$?

    if [ "$EXIT_CODE" -eq 0 ]; then
        success "All tests passed!"
    else
        fail "Tests failed (exit code $EXIT_CODE)"
    fi
}

# ── Cleanup trap ─────────────────────────────────────────────────────────────
cleanup() {
    if [ "$ENV_UP" = true ]; then
        case "$MODE" in
            docker)
                docker_logs
                docker_down
                ;;
            k8s)
                k8s_logs
                k8s_down
                ;;
        esac
    fi
}

trap cleanup EXIT

# ── Main ─────────────────────────────────────────────────────────────────────
case "$MODE" in
    docker)
        docker_up
        docker_wait
        run_tests "http://localhost:8090"
        ;;
    k8s)
        k8s_up
        k8s_wait
        run_tests "http://localhost:${E2E_KONG_PORT}"
        ;;
    *)
        echo "Usage: e2e-lifecycle.sh <docker|k8s> [pytest-args...]"
        exit 1
        ;;
esac

exit "$EXIT_CODE"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x infra/scripts/e2e-lifecycle.sh
```

- [ ] **Step 3: Commit**

```bash
git add infra/scripts/e2e-lifecycle.sh
git commit -m "feat(e2e): add lifecycle script for isolated e2e environments"
```

---

### Task 3: Modify build-images.sh to Accept CLUSTER_NAME

**Files:**
- Modify: `infra/k8s/scripts/build-images.sh:7`

- [ ] **Step 1: Change hardcoded CLUSTER_NAME to env var with default**

Change line 7 from:
```bash
CLUSTER_NAME="chatbox"
```
to:
```bash
CLUSTER_NAME="${CLUSTER_NAME:-chatbox}"
```

- [ ] **Step 2: Commit**

```bash
git add infra/k8s/scripts/build-images.sh
git commit -m "feat(e2e): make build-images.sh accept CLUSTER_NAME env var"
```

---

### Task 4: Update conftest.py Auto-Detection

**Files:**
- Modify: `tests/e2e/conftest.py:39`

- [ ] **Step 1: Add e2e ports to the probe list**

Change line 39 from:
```python
    for port in (80, 30080):
```
to:
```python
    for port in (80, 8090, 30080, 31080):
```

Also update the error message at line 52 from:
```python
        "Tried: KONG_URL env var, localhost:80, localhost:30080.\n"
```
to:
```python
        "Tried: KONG_URL env var, localhost:80, localhost:8090, localhost:30080, localhost:31080.\n"
```

- [ ] **Step 2: Commit**

```bash
git add tests/e2e/conftest.py
git commit -m "feat(e2e): add e2e environment ports to conftest auto-detection"
```

---

### Task 5: Replace Makefile E2E Targets

**Files:**
- Modify: `Makefile:175-229`

- [ ] **Step 1: Replace the entire E2E section** (lines 175-229) with:

```makefile
# ── E2E Tests ────────────────────────────────────────────────────────────────

.PHONY: e2e-docker e2e-k8s e2e-all e2e-smoke e2e-setup e2e-auth e2e-pm e2e-files e2e-chat e2e-messages e2e-admin e2e-monitoring

E2E_LIFECYCLE := infra/scripts/e2e-lifecycle.sh

e2e-setup: ## Install e2e test dependencies
	pip install -r tests/e2e/requirements.txt

e2e-docker: ## Black box: spin up Docker Compose → test all → tear down
	@bash $(E2E_LIFECYCLE) docker

e2e-k8s: ## Black box: create Kind cluster → deploy → test all → delete cluster
	@bash $(E2E_LIFECYCLE) k8s

e2e-all: ## Run e2e-docker then e2e-k8s sequentially
	@bash $(E2E_LIFECYCLE) docker
	@bash $(E2E_LIFECYCLE) k8s

e2e-smoke: ## Black box Docker Compose, smoke tests only
	@bash $(E2E_LIFECYCLE) docker -m smoke

e2e-auth: ## Black box Docker Compose, auth tests only
	@bash $(E2E_LIFECYCLE) docker -k test_auth

e2e-pm: ## Black box Docker Compose, PM tests only
	@bash $(E2E_LIFECYCLE) docker -k test_pm

e2e-files: ## Black box Docker Compose, file tests only
	@bash $(E2E_LIFECYCLE) docker -k test_files

e2e-chat: ## Black box Docker Compose, chat tests only
	@bash $(E2E_LIFECYCLE) docker -k "test_chat_rooms or test_chat_websocket"

e2e-messages: ## Black box Docker Compose, message tests only
	@bash $(E2E_LIFECYCLE) docker -k test_messages

e2e-admin: ## Black box Docker Compose, admin tests only
	@bash $(E2E_LIFECYCLE) docker -k test_admin

e2e-monitoring: ## Black box Docker Compose, monitoring tests only
	@bash $(E2E_LIFECYCLE) docker -k test_monitoring
```

- [ ] **Step 2: Commit**

```bash
git add Makefile
git commit -m "feat(e2e): replace Makefile targets with black-box lifecycle targets"
```

---

### Task 6: Gitignore and Doc Updates

**Files:**
- Modify: `.gitignore`
- Modify: `docs/operations/makefile-reference.md`

- [ ] **Step 1: Add logs directory to .gitignore**

Append to `.gitignore`:
```
# E2E test logs
tests/e2e/logs/
```

- [ ] **Step 2: Update makefile-reference.md**

Replace the entire "9. End-to-End Tests" section with the updated content reflecting the new black-box targets, including:
- Quick Start section updated: `make e2e-docker` instead of `make e2e`
- All Targets table updated with new target names
- New "How It Works" section explaining the black-box lifecycle
- Per-service targets documented as also doing full lifecycle
- Log dump behavior documented

- [ ] **Step 3: Commit**

```bash
git add .gitignore docs/operations/makefile-reference.md
git commit -m "docs: update e2e docs and gitignore for isolated environment lifecycle"
```

---

## Self-Review

**Spec coverage:**
- ✅ docker-compose.e2e.yml override (Task 1)
- ✅ Lifecycle script docker mode (Task 2)
- ✅ Lifecycle script k8s mode (Task 2)
- ✅ Health wait with timeout (Task 2)
- ✅ Log dump on exit (Task 2)
- ✅ Always teardown via trap (Task 2)
- ✅ build-images.sh CLUSTER_NAME (Task 3)
- ✅ conftest.py port update (Task 4)
- ✅ All Makefile targets (Task 5)
- ✅ Gitignore + docs (Task 6)

**Placeholder scan:** No TBDs or TODOs. All code blocks are complete.

**Type consistency:** CLUSTER_NAME used consistently. Port numbers match spec (8090, 3090, 31080, 31000, 31030). Project name `chatbox-e2e` used consistently.
