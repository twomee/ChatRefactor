#!/bin/sh
# docker-entrypoint.sh — Generate runtime config.js from environment variables
# This allows changing API URLs without rebuilding the frontend image

CONFIG_FILE="/usr/share/nginx/html/config.js"

cat > "$CONFIG_FILE" <<EOF
// Runtime configuration — generated at container startup
// Do not edit manually. Set environment variables instead.
window.__RUNTIME_CONFIG__ = {
  VITE_API_BASE: "${VITE_API_BASE:-http://localhost}",
  VITE_WS_BASE: "${VITE_WS_BASE:-ws://localhost}"
};
EOF

echo "Runtime config written to $CONFIG_FILE"
echo "  VITE_API_BASE: ${VITE_API_BASE:-http://localhost}"
echo "  VITE_WS_BASE: ${VITE_WS_BASE:-ws://localhost}"

# Start nginx
exec nginx -g 'daemon off;'
