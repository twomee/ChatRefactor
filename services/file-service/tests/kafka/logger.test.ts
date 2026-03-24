import { describe, it, expect, vi } from "vitest";

// Mock config before importing logger
vi.mock("../../src/config/env.config.js", () => ({
  config: {
    nodeEnv: "test",
    port: 8005,
    secretKey: "test-secret",
    uploadDir: "/tmp/test-uploads",
    maxFileSizeMB: 150,
    allowedExtensions: [".txt"],
    databaseUrl: "postgresql://test:test@localhost:5432/test",
    kafkaBrokers: ["localhost:9092"],
  },
}));

describe("kafka/logger", () => {
  it("should export a logger instance", async () => {
    const { logger } = await import("../../src/kafka/logger.js");
    expect(logger).toBeDefined();
    expect(logger.info).toBeTypeOf("function");
    expect(logger.warn).toBeTypeOf("function");
    expect(logger.error).toBeTypeOf("function");
  });

  it("should redact password fields in log metadata", async () => {
    const { logger } = await import("../../src/kafka/logger.js");
    const transport = logger.transports[0];

    // Capture log output
    let loggedInfo: Record<string, unknown> = {};
    const originalWrite = transport.write;
    transport.write = (info: Record<string, unknown>) => {
      loggedInfo = info;
      return true;
    };

    logger.info("test", { password: "secret123", username: "alice" });

    transport.write = originalWrite;

    expect(loggedInfo["password"]).toBe("[REDACTED]");
    expect(loggedInfo["username"]).toBe("alice");
  });

  it("should redact Bearer tokens in string values", async () => {
    const { logger } = await import("../../src/kafka/logger.js");
    const transport = logger.transports[0];

    let loggedInfo: Record<string, unknown> = {};
    const originalWrite = transport.write;
    transport.write = (info: Record<string, unknown>) => {
      loggedInfo = info;
      return true;
    };

    logger.info("test", { authorization: "Bearer eyJhbGci.token.here" });

    transport.write = originalWrite;

    // authorization key is in REDACT_KEYS, so the whole value is redacted
    expect(loggedInfo["authorization"]).toBe("[REDACTED]");
  });

  it("should redact Bearer tokens embedded in other string fields", async () => {
    const { logger } = await import("../../src/kafka/logger.js");
    const transport = logger.transports[0];

    let loggedInfo: Record<string, unknown> = {};
    const originalWrite = transport.write;
    transport.write = (info: Record<string, unknown>) => {
      loggedInfo = info;
      return true;
    };

    logger.info("test", { header: "Authorization: Bearer eyJhbGci.real.token" });

    transport.write = originalWrite;

    expect(loggedInfo["header"]).toContain("[REDACTED]");
    expect(loggedInfo["header"]).not.toContain("eyJhbGci");
  });
});
