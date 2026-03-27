#!/usr/bin/env bash
# deploy.sh — Deploy or update application services
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
K8S_DIR="$PROJECT_ROOT/k8s"
OVERLAY="${1:-dev}"

echo "Deploying with overlay: $OVERLAY"
kubectl apply -k "$K8S_DIR/overlays/$OVERLAY"

echo ""
echo "Waiting for rollouts..."
for svc in auth-service chat-service message-service file-service frontend kong; do
  echo "  Waiting for $svc..."
  kubectl rollout status deployment/$svc --namespace chatbox --timeout=120s
done

echo ""
echo "Deployment complete!"
kubectl get pods -n chatbox
