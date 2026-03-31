#!/usr/bin/env bash
# deploy.sh — Deploy or update application services
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
K8S_DIR="$PROJECT_ROOT/infra/k8s"
OVERLAY="${1:-dev}"

echo "Deploying with overlay: $OVERLAY"

# Apply secrets first so pods start with correct credentials.
# secrets.yaml files are intentionally excluded from kustomization.yaml
# and managed exclusively here to prevent kubectl apply from overwriting
# live secrets with the CHANGE_ME placeholders committed to the repo.
bash "$SCRIPT_DIR/generate-secrets.sh"

kubectl apply -k "$K8S_DIR/overlays/$OVERLAY"

# Restart all services so they pick up any secret changes.
# K8s does not propagate secret updates to running pods automatically.
echo ""
echo "Restarting services to pick up latest secrets..."
kubectl rollout restart deployment/auth-service deployment/chat-service \
  deployment/message-service deployment/file-service \
  deployment/frontend deployment/kong \
  --namespace chatbox

echo ""
echo "Waiting for rollouts..."
for svc in auth-service chat-service message-service file-service frontend kong; do
  echo "  Waiting for $svc..."
  kubectl rollout status deployment/$svc --namespace chatbox --timeout=120s
done

echo ""
echo "Deployment complete!"
kubectl get pods -n chatbox
