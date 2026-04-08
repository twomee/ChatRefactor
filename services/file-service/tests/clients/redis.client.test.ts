// tests/clients/redis.client.test.ts — Unit tests for the Redis client module

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ── Hoisted mocks ──────────────────────────────────────────────────────────
const mockOn = vi.hoisted(() => vi.fn());
const mockQuit = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

vi.mock("ioredis", () => {
  return {
    // Must use a regular function (not arrow) so it can be used as a constructor
    default: vi.fn().mockImplementation(function () {
      return { on: mockOn, quit: mockQuit };
    }),
  };
});

vi.mock("../../src/kafka/logger.js", () => ({
  logger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
  },
}));

// Import after mocks are set up
import {
  getRedisClient,
  initRedisClient,
  closeRedisClient,
} from "../../src/clients/redis.client.js";
import { logger } from "../../src/kafka/logger.js";
import Redis from "ioredis";

describe("clients/redis.client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(async () => {
    // Reset module state between tests
    await closeRedisClient();
  });

  describe("getRedisClient", () => {
    it("returns null before init", () => {
      expect(getRedisClient()).toBeNull();
    });

    it("returns client after init", () => {
      initRedisClient("redis://localhost:6379");
      expect(getRedisClient()).not.toBeNull();
    });
  });

  describe("initRedisClient", () => {
    it("does nothing when redisUrl is empty", () => {
      initRedisClient("");
      expect(Redis).not.toHaveBeenCalled();
      expect(getRedisClient()).toBeNull();
    });

    it("creates Redis instance with provided URL", () => {
      initRedisClient("redis://localhost:6379");
      expect(Redis).toHaveBeenCalledWith("redis://localhost:6379", expect.objectContaining({
        maxRetriesPerRequest: 2,
        enableOfflineQueue: false,
      }));
    });

    it("registers connect and error event handlers", () => {
      initRedisClient("redis://localhost:6379");
      expect(mockOn).toHaveBeenCalledWith("connect", expect.any(Function));
      expect(mockOn).toHaveBeenCalledWith("error", expect.any(Function));
    });

    it("logs info on connect event", () => {
      initRedisClient("redis://localhost:6379");
      // Get the connect handler and invoke it
      const connectCall = mockOn.mock.calls.find(([event]) => event === "connect");
      expect(connectCall).toBeDefined();
      connectCall![1](); // invoke handler
      expect(logger.info).toHaveBeenCalledWith("Redis connected (token blacklist)");
    });

    it("logs warning on error event", () => {
      initRedisClient("redis://localhost:6379");
      const errorCall = mockOn.mock.calls.find(([event]) => event === "error");
      expect(errorCall).toBeDefined();
      errorCall![1](new Error("connection refused")); // invoke handler
      expect(logger.warn).toHaveBeenCalledWith(
        "Redis connection error",
        expect.objectContaining({ error: "connection refused" })
      );
    });
  });

  describe("closeRedisClient", () => {
    it("does nothing when client is null", async () => {
      await closeRedisClient(); // no client initialized
      expect(mockQuit).not.toHaveBeenCalled();
    });

    it("calls quit and sets client to null", async () => {
      initRedisClient("redis://localhost:6379");
      expect(getRedisClient()).not.toBeNull();

      await closeRedisClient();

      expect(mockQuit).toHaveBeenCalled();
      expect(getRedisClient()).toBeNull();
    });
  });
});
