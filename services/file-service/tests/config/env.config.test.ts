// tests/config/env.config.test.ts — Unit tests for environment configuration
//
// Tests that the config module correctly reads environment variables
// and applies defaults. The setup.ts file sets test env vars, so we
// verify config reflects those values.

import { describe, it, expect } from "vitest";
import { config } from "../../src/config/env.config.js";

describe("config/env.config", () => {
  it("should read NODE_ENV from environment", () => {
    expect(config.nodeEnv).toBe("test");
  });

  it("should read SECRET_KEY from environment", () => {
    expect(config.secretKey).toBe("test-secret-key-for-jwt-signing");
  });

  it("should read DATABASE_URL from environment", () => {
    expect(config.databaseUrl).toBe("postgresql://test:test@localhost:5432/test");
  });

  it("should read KAFKA_BOOTSTRAP_SERVERS from environment", () => {
    expect(config.kafkaBootstrapServers).toBe("localhost:9092");
  });

  it("should read UPLOAD_DIR from environment", () => {
    expect(config.uploadDir).toContain("file-service-test-uploads");
  });

  it("should use HS256 as the JWT algorithm", () => {
    expect(config.algorithm).toBe("HS256");
  });

  it("should have a numeric port", () => {
    expect(typeof config.port).toBe("number");
    expect(Number.isNaN(config.port)).toBe(false);
  });

  it("should have a numeric maxFileSizeBytes", () => {
    expect(typeof config.maxFileSizeBytes).toBe("number");
    expect(config.maxFileSizeBytes).toBeGreaterThan(0);
  });

  it("should have allowedExtensions as a Set", () => {
    expect(config.allowedExtensions).toBeInstanceOf(Set);
    expect(config.allowedExtensions.has(".txt")).toBe(true);
    expect(config.allowedExtensions.has(".pdf")).toBe(true);
    expect(config.allowedExtensions.has(".exe")).toBe(false);
  });
});
