#!/usr/bin/env bash
# build-images.sh — Build all Docker images and load into kind
#
# Images are built in parallel to cut CI time from ~20 min → ~5 min.
# Each background job writes to its own log; failures are collected and
# reported after all jobs finish so nothing is silently swallowed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-chatbox}"
KONG_PORT="${KONG_PORT:-30080}"

LOG_DIR=$(mktemp -d)
trap 'rm -rf "$LOG_DIR"' EXIT

echo "========================================="
echo "  Building Docker Images (parallel)"
echo "========================================="

build() {
  local name="$1"; shift
  echo "[build] $name starting..."
  if docker build -t "${name}:latest" "$@" >"$LOG_DIR/${name}.log" 2>&1; then
    echo "[build] $name done"
  else
    echo "[build] $name FAILED — log:"
    cat "$LOG_DIR/${name}.log"
    return 1
  fi
}

# ── Parallel builds ────────────────────────────────────────────────────────────
build auth-service    "$PROJECT_ROOT/services/auth-service"    &
build chat-service    "$PROJECT_ROOT/services/chat-service"    &
build message-service "$PROJECT_ROOT/services/message-service" &
build file-service    "$PROJECT_ROOT/services/file-service"    &
build frontend        \
  --build-arg VITE_API_BASE="http://localhost:${KONG_PORT}" \
  --build-arg VITE_WS_BASE="ws://localhost:${KONG_PORT}"   \
  "$PROJECT_ROOT/frontend" &

# Collect results — if any build job failed, exit non-zero
FAIL=0
for job in $(jobs -p); do
  wait "$job" || FAIL=1
done
[ "$FAIL" -eq 0 ] || { echo "One or more image builds failed"; exit 1; }

echo ""
echo "========================================="
echo "  Loading images into Kind (parallel)"
echo "========================================="

load() {
  local name="$1"
  echo "[load] ${name}:latest starting..."
  if kind load docker-image "${name}:latest" --name "$CLUSTER_NAME" \
       >"$LOG_DIR/load-${name}.log" 2>&1; then
    echo "[load] ${name}:latest done"
  else
    echo "[load] ${name}:latest FAILED — log:"
    cat "$LOG_DIR/load-${name}.log"
    return 1
  fi
}

load auth-service    &
load chat-service    &
load message-service &
load file-service    &
load frontend        &

FAIL=0
for job in $(jobs -p); do
  wait "$job" || FAIL=1
done
[ "$FAIL" -eq 0 ] || { echo "One or more Kind loads failed"; exit 1; }

echo ""
echo "All images built and loaded!"
