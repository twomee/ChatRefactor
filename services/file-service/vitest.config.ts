import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.ts"],
      exclude: ["src/index.ts", "src/types/**"],
      thresholds: {
        statements: 90,
        branches: 80,
        functions: 90,
        lines: 90,
      },
    },
    setupFiles: ["tests/setup.ts"],
  },
});
