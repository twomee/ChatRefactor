import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': 'http://localhost:8001',
      '/rooms': 'http://localhost:8003',
      '/ws': {
        target: 'http://localhost:8003',
        ws: true,
      },
      '/pm': 'http://localhost:8003',
      '/admin': 'http://localhost:8003',
      '/messages': 'http://localhost:8004',
      '/files': 'http://localhost:8005',
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
