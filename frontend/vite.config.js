import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Suppress EPIPE/ECONNREFUSED errors on all proxy routes.
// These happen when the browser drops connections on refresh or
// when a backend service is temporarily down.
const silenceProxyErrors = {
  error: () => {},
  proxyReq: (_proxyReq, _req, res) => {
    res.on('error', () => {});
  },
  proxyReqWs: (_proxyReq, _req, socket) => {
    socket.on('error', () => {});
  },
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': { target: 'http://localhost:8001', on: silenceProxyErrors },
      '/rooms': { target: 'http://localhost:8003', on: silenceProxyErrors },
      '/ws': { target: 'http://localhost:8003', ws: true, on: silenceProxyErrors },
      '/pm': { target: 'http://localhost:8003', on: silenceProxyErrors },
      '/admin': {
        target: 'http://localhost:8003',
        on: silenceProxyErrors,
        // Don't proxy browser page navigation (SPA route /admin).
        // Only proxy API calls (XHR/fetch) to the chat service.
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html';
          }
        },
      },
      '/messages': { target: 'http://localhost:8004', on: silenceProxyErrors },
      '/files': { target: 'http://localhost:8005', on: silenceProxyErrors },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/test/**', 'src/main.jsx', 'src/assets/**'],
      thresholds: {
        // Global thresholds — pages and hooks with complex WebSocket/routing
        // dependencies will be covered by integration tests; these thresholds
        // reflect realistic unit-test coverage for the full src/ tree.
        lines: 32,
        functions: 33,
        branches: 28,
        statements: 31,
      },
    },
  },
})
