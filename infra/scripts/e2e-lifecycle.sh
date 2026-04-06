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

# Check for --ui or --all flags
TEST_MODE="api"
FILTERED_ARGS=()
for arg in "${PYTEST_ARGS[@]}"; do
    case "$arg" in
        --ui)  TEST_MODE="ui" ;;
        --all) TEST_MODE="all" ;;
        *)     FILTERED_ARGS+=("$arg") ;;
    esac
done
PYTEST_ARGS=("${FILTERED_ARGS[@]}")

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

    step "Waiting for cluster DNS to be ready..."
    local dns_elapsed=0
    while ! kubectl get pods -n kube-system -l k8s-app=kube-dns --no-headers 2>/dev/null | grep -q "Running"; do
        if [ "$dns_elapsed" -ge 120 ]; then
            fail "CoreDNS not ready after 120s"
            exit 1
        fi
        sleep 3
        dns_elapsed=$((dns_elapsed + 3))
    done
    kubectl wait --for=condition=ready pod -l k8s-app=kube-dns -n kube-system --timeout=120s
    success "CoreDNS ready"

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
    helm repo update 2>/dev/null

    step "Pre-pulling infrastructure images into Kind cluster..."
    # Kind can't pull large images fast enough during Helm install.
    # Pull on the host (cached) and load into Kind instead.
    for img in bitnami/postgresql:latest bitnami/redis:latest apache/kafka:3.8.1 apache/kafka:latest postgres:16-alpine busybox:1.36; do
        docker pull "$img" 2>/dev/null || true
        kind load docker-image "$img" --name "$E2E_CLUSTER" 2>/dev/null || true
    done
    success "Infrastructure images loaded"

    echo "  Installing PostgreSQL..."
    helm upgrade --install postgres bitnami/postgresql \
        --namespace chatbox-infra \
        --values "$K8S_DIR/infra/helm-values/postgres.yaml" \
        --set auth.postgresPassword="$POSTGRES_PASSWORD" \
        --set auth.password="$POSTGRES_PASSWORD" \
        --set metrics.enabled=false \
        --set metrics.serviceMonitor.enabled=false \
        --set primary.persistence.enabled=false \
        --version 18.5.14 \
        --wait --timeout 300s

    echo "  Installing Redis..."
    helm upgrade --install redis bitnami/redis \
        --namespace chatbox-infra \
        --values "$K8S_DIR/infra/helm-values/redis.yaml" \
        --set auth.password="$REDIS_PASSWORD" \
        --set metrics.enabled=false \
        --set metrics.serviceMonitor.enabled=false \
        --set master.persistence.enabled=false \
        --set replica.persistence.enabled=false \
        --version 25.3.9 \
        --wait --timeout 300s

    echo "  Installing Kafka..."
    kubectl apply -f "$K8S_DIR/infra/kafka.yaml"
    kubectl rollout status deployment/kafka --namespace chatbox-infra --timeout=300s

    step "Applying secrets..."
    bash "$K8S_DIR/scripts/generate-secrets.sh"

    step "Running init jobs..."
    kubectl delete job db-init --namespace chatbox --ignore-not-found
    kubectl delete job kafka-init --namespace chatbox --ignore-not-found
    kubectl apply -f "$K8S_DIR/jobs/db-init-job.yaml"
    kubectl apply -f "$K8S_DIR/jobs/kafka-init-job.yaml"
    kubectl wait --for=condition=complete job/db-init --namespace chatbox --timeout=300s
    kubectl wait --for=condition=complete job/kafka-init --namespace chatbox --timeout=300s

    step "Building and loading Docker images..."
    CLUSTER_NAME="$E2E_CLUSTER" KONG_PORT="$E2E_KONG_PORT" bash "$K8S_DIR/scripts/build-images.sh"

    step "Deploying application..."
    # Use the e2e overlay (different NodePorts: 31080/31000 to avoid conflict with dev).
    # Ignore ServiceMonitor errors — e2e cluster has no Prometheus CRDs.
    kubectl apply -k "$K8S_DIR/overlays/e2e" 2>&1 | grep -v "ServiceMonitor" || true
    success "K8s deployment complete"
}

k8s_wait() {
    step "Waiting for deployments to roll out..."
    # Use kubectl rollout status per deployment — more reliable than grep-polling pod
    # phases because it understands init containers and the Ready condition.
    # Run all waits in parallel (deployments started simultaneously) and collect
    # failures so every timed-out deployment is reported before we exit.
    local rollout_timeout=480s
    local pids=() names=()
    for deploy in auth-service chat-service message-service file-service frontend kong; do
        kubectl rollout status deployment/"$deploy" \
            --namespace chatbox \
            --timeout="$rollout_timeout" &
        pids+=($!)
        names+=("$deploy")
    done

    local fail=0
    for i in "${!pids[@]}"; do
        if ! wait "${pids[$i]}"; then
            fail "Deployment ${names[$i]} did not become ready within $rollout_timeout"
            fail=1
        fi
    done

    if [ "$fail" -ne 0 ]; then
        echo ""
        kubectl get pods -n chatbox
        exit 1
    fi
    success "All deployments ready"

    # Wait for Kong to respond and all backend services to be routable
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

    # Wait for backend services to be routable through Kong (not just Kong itself)
    elapsed=0
    while ! curl -sf "http://localhost:${E2E_KONG_PORT}/rooms" -H "Authorization: Bearer test" 2>/dev/null | grep -q "401\|Invalid\|\[" ; do
        if [ "$elapsed" -ge 60 ]; then
            echo "  Warning: backend services may not be fully ready"
            break
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    success "Backend services routable"
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

    if [ "$TEST_MODE" = "api" ] || [ "$TEST_MODE" = "all" ]; then
        step "Running API e2e tests against $kong_url..."
        KONG_URL="$kong_url" python3 -m pytest "$PROJECT_ROOT/tests/e2e/" \
            -v --tb=short -c "$PROJECT_ROOT/tests/e2e/pytest.ini" \
            "${PYTEST_ARGS[@]}" || EXIT_CODE=$?
    fi

    if [ "$TEST_MODE" = "ui" ] || [ "$TEST_MODE" = "all" ]; then
        step "Running UI e2e tests against $kong_url..."
        cd "$PROJECT_ROOT/tests/e2e-ui"
        npm ci --silent 2>/dev/null || npm install --silent
        npx playwright install chromium 2>/dev/null || true
        BASE_URL="$kong_url" npx playwright test "${PYTEST_ARGS[@]}" || EXIT_CODE=$?
        cd "$PROJECT_ROOT"
    fi

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
