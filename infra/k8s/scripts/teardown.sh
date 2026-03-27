#!/usr/bin/env bash
# teardown.sh — Remove everything and delete the kind cluster
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
K8S_DIR="$PROJECT_ROOT/infra/k8s"
CLUSTER_NAME="chatbox"

echo "========================================="
echo "  Chatbox K8s Teardown"
echo "========================================="

echo ""
echo "[1/5] Removing application..."
kubectl delete -k "$K8S_DIR/overlays/dev" --ignore-not-found 2>/dev/null || true

echo ""
echo "[2/5] Removing init jobs..."
kubectl delete -f "$K8S_DIR/jobs/" --ignore-not-found 2>/dev/null || true

echo ""
echo "[3/5] Removing infrastructure..."
kubectl delete -f "$K8S_DIR/infra/kafka.yaml" --ignore-not-found 2>/dev/null || true
helm uninstall redis --namespace chatbox-infra 2>/dev/null || true
helm uninstall postgres --namespace chatbox-infra 2>/dev/null || true

echo ""
echo "[4/5] Removing monitoring..."
helm uninstall monitoring --namespace chatbox-monitoring 2>/dev/null || true

echo ""
echo "[5/5] Deleting kind cluster..."
kind delete cluster --name "$CLUSTER_NAME"

echo ""
echo "========================================="
echo "  Teardown complete!"
echo "========================================="
