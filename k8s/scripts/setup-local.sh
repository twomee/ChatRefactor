#!/usr/bin/env bash
# setup-local.sh — One-command local Kubernetes setup using kind
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
K8S_DIR="$PROJECT_ROOT/k8s"
CLUSTER_NAME="chatbox"

echo "========================================="
echo "  Chatbox K8s Local Setup"
echo "========================================="

# Step 1: Create kind cluster
echo ""
echo "[1/7] Creating kind cluster..."
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
  echo "  Cluster '$CLUSTER_NAME' already exists, skipping..."
else
  kind create cluster --name "$CLUSTER_NAME" --config - <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080
        hostPort: 30080
        protocol: TCP
      - containerPort: 30000
        hostPort: 30000
        protocol: TCP
      - containerPort: 30030
        hostPort: 30030
        protocol: TCP
EOF
fi

# Step 2: Create namespaces
echo ""
echo "[2/7] Creating namespaces..."
kubectl apply -f "$K8S_DIR/base/namespace.yaml"
kubectl apply -f "$K8S_DIR/infra/namespace.yaml"

# Step 3: Install infrastructure via Helm
echo ""
echo "[3/7] Installing infrastructure (Helm)..."
helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
helm repo update

# Load secrets
SECRETS_FILE="$K8S_DIR/secrets.env"
if [ ! -f "$SECRETS_FILE" ]; then
  echo "  No secrets.env found, using defaults from secrets.env.example..."
  SECRETS_FILE="$K8S_DIR/base/secrets.env.example"
fi
source "$SECRETS_FILE"

# PostgreSQL
echo "  Installing PostgreSQL..."
helm upgrade --install postgres bitnami/postgresql \
  --namespace chatbox-infra \
  --values "$K8S_DIR/infra/helm-values/postgres.yaml" \
  --set auth.postgresPassword="$POSTGRES_PASSWORD" \
  --set auth.password="$POSTGRES_PASSWORD" \
  --version 16.4.5 \
  --wait --timeout 120s

# Redis
echo "  Installing Redis..."
helm upgrade --install redis bitnami/redis \
  --namespace chatbox-infra \
  --values "$K8S_DIR/infra/helm-values/redis.yaml" \
  --set auth.password="$REDIS_PASSWORD" \
  --version 20.6.2 \
  --wait --timeout 120s

# Kafka
echo "  Installing Kafka..."
helm upgrade --install kafka bitnami/kafka \
  --namespace chatbox-infra \
  --values "$K8S_DIR/infra/helm-values/kafka.yaml" \
  --version 31.2.0 \
  --wait --timeout 180s

# Step 4: Generate and apply secrets
echo ""
echo "[4/7] Applying secrets..."
bash "$K8S_DIR/scripts/generate-secrets.sh"

# Step 5: Run init jobs
echo ""
echo "[5/7] Running init jobs..."
kubectl delete job db-init --namespace chatbox --ignore-not-found
kubectl delete job kafka-init --namespace chatbox --ignore-not-found
kubectl apply -f "$K8S_DIR/jobs/db-init-job.yaml"
kubectl apply -f "$K8S_DIR/jobs/kafka-init-job.yaml"
echo "  Waiting for db-init job..."
kubectl wait --for=condition=complete job/db-init --namespace chatbox --timeout=120s
echo "  Waiting for kafka-init job..."
kubectl wait --for=condition=complete job/kafka-init --namespace chatbox --timeout=120s

# Step 6: Build and load images
echo ""
echo "[6/7] Building and loading Docker images..."
bash "$K8S_DIR/scripts/build-images.sh"

# Step 7: Deploy application
echo ""
echo "[7/7] Deploying application..."
kubectl apply -k "$K8S_DIR/overlays/dev"

echo ""
echo "========================================="
echo "  Setup complete!"
echo "========================================="
echo ""
echo "  Frontend: http://localhost:30000"
echo "  API (Kong): http://localhost:30080"
echo ""
echo "  Check status: make k8s-status"
echo "  View logs: make k8s-logs SVC=auth-service"
echo "========================================="
