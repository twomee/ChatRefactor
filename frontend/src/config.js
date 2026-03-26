// Runtime configuration helper
// In K8s, config.js is generated at container startup by docker-entrypoint.sh
// which writes window.__RUNTIME_CONFIG__ with values from environment variables.
// In development (Vite), falls back to import.meta.env variables.

export const config = {
  apiBase:
    window.__RUNTIME_CONFIG__?.VITE_API_BASE ||
    import.meta.env.VITE_API_BASE ||
    'http://localhost',
  wsBase:
    window.__RUNTIME_CONFIG__?.VITE_WS_BASE ||
    import.meta.env.VITE_WS_BASE ||
    'ws://localhost',
};
