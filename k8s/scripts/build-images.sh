#!/usr/bin/env bash
# build-images.sh — Build all Docker images and load into kind
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLUSTER_NAME="chatbox"

echo "========================================="
echo "  Building Docker Images"
echo "========================================="

echo ""
echo "[1/5] Building auth-service..."
docker build -t auth-service:latest "$PROJECT_ROOT/services/auth-service"

echo ""
echo "[2/5] Building chat-service..."
docker build -t chat-service:latest "$PROJECT_ROOT/services/chat-service"

echo ""
echo "[3/5] Building message-service..."
docker build -t message-service:latest "$PROJECT_ROOT/services/message-service"

echo ""
echo "[4/5] Building file-service..."
docker build -t file-service:latest "$PROJECT_ROOT/services/file-service"

echo ""
echo "[5/5] Building frontend..."
docker build -t frontend:latest \
  --build-arg VITE_API_BASE=http://localhost:30080 \
  --build-arg VITE_WS_BASE=ws://localhost:30080 \
  "$PROJECT_ROOT/frontend"

echo ""
echo "Loading images into kind cluster..."
kind load docker-image auth-service:latest --name "$CLUSTER_NAME"
kind load docker-image chat-service:latest --name "$CLUSTER_NAME"
kind load docker-image message-service:latest --name "$CLUSTER_NAME"
kind load docker-image file-service:latest --name "$CLUSTER_NAME"
kind load docker-image frontend:latest --name "$CLUSTER_NAME"

echo ""
echo "All images built and loaded!"
