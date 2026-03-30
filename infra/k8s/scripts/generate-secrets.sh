#!/usr/bin/env bash
# generate-secrets.sh — Generate K8s Secret manifests from environment variables
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$K8S_DIR/../.." && pwd)"

# Load secrets from file
SECRETS_FILE="$K8S_DIR/secrets.env"
if [ ! -f "$SECRETS_FILE" ]; then
  SECRETS_FILE="$K8S_DIR/base/secrets.env.example"
  echo "Warning: No secrets.env found, using defaults from secrets.env.example"
fi
source "$SECRETS_FILE"

PG_HOST="postgres-postgresql.chatbox-infra.svc.cluster.local"
REDIS_HOST="redis-master.chatbox-infra.svc.cluster.local"

# Bitnami Redis ignores --set auth.password on helm upgrade if the secret already exists.
# Read the actual password from the Helm-created secret so our REDIS_URL is always correct.
ACTUAL_REDIS_PASSWORD=$(kubectl get secret redis -n chatbox-infra \
  -o jsonpath='{.data.redis-password}' 2>/dev/null | base64 -d || echo "${REDIS_PASSWORD}")

echo "Applying K8s secrets..."

# Shared infra secrets
kubectl create secret generic chatbox-infra-secrets \
  --namespace chatbox \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=REDIS_PASSWORD="$ACTUAL_REDIS_PASSWORD" \
  --from-literal=SECRET_KEY="$SECRET_KEY" \
  --from-literal=REDIS_URL="redis://default:${ACTUAL_REDIS_PASSWORD}@${REDIS_HOST}:6379/0" \
  --dry-run=client -o yaml | kubectl apply -f -

# Per-service secrets (DATABASE_URL with embedded password)
kubectl create secret generic auth-service-secrets \
  --namespace chatbox \
  --from-literal=DATABASE_URL="postgresql://chatbox:${POSTGRES_PASSWORD}@${PG_HOST}:5432/chatbox_auth" \
  --from-literal=TOTP_ENCRYPTION_KEY="${TOTP_ENCRYPTION_KEY:?TOTP_ENCRYPTION_KEY is required in secrets.env}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic chat-service-secrets \
  --namespace chatbox \
  --from-literal=DATABASE_URL="postgresql://chatbox:${POSTGRES_PASSWORD}@${PG_HOST}:5432/chatbox_chat" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic message-service-secrets \
  --namespace chatbox \
  --from-literal=DATABASE_URL="postgresql://chatbox:${POSTGRES_PASSWORD}@${PG_HOST}:5432/chatbox_messages" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic file-service-secrets \
  --namespace chatbox \
  --from-literal=DATABASE_URL="postgresql://chatbox:${POSTGRES_PASSWORD}@${PG_HOST}:5432/chatbox_files" \
  --dry-run=client -o yaml | kubectl apply -f -

# Auth admin secret
kubectl create secret generic auth-admin-secret \
  --namespace chatbox \
  --from-literal=ADMIN_USERNAME="${ADMIN_USERNAME:?ADMIN_USERNAME is required in secrets.env}" \
  --from-literal=ADMIN_PASSWORD="${ADMIN_PASSWORD:?ADMIN_PASSWORD is required in secrets.env}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "All secrets applied!"
