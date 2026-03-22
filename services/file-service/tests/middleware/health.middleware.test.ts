// tests/middleware/health.middleware.test.ts — Integration tests for health check endpoints
//
// Tests GET /health (liveness) and GET /ready (readiness) endpoints.
// These are registered before auth middleware, so no JWT is needed.

import { describe, it, expect, vi, beforeEach } from "vitest";
import request from "supertest";

// ── Hoisted mocks ──────────────────────────────────────────────────────────
const { mockPrismaFile, mockQueryRaw } = vi.hoisted(() => ({
  mockPrismaFile: {
    create: vi.fn(),
    findUnique: vi.fn(),
    findMany: vi.fn(),
  },
  mockQueryRaw: vi.fn().mockResolvedValue([{ "?column?": 1 }]),
}));

const { mockExistsSync, mockCreateReadStream, mockWriteFileSync, mockMkdirSync } = vi.hoisted(() => ({
  mockExistsSync: vi.fn().mockReturnValue(true),
  mockCreateReadStream: vi.fn(),
  mockWriteFileSync: vi.fn(),
  mockMkdirSync: vi.fn(),
}));

vi.mock("@prisma/client", () => {
  return {
    PrismaClient: vi.fn().mockImplementation(() => ({
      file: mockPrismaFile,
      $queryRaw: mockQueryRaw,
    })),
  };
});

const mockProducerSend = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockProducerConnect = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockProducerDisconnect = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

vi.mock("kafkajs", () => {
  const mockProducer = {
    connect: mockProducerConnect,
    send: mockProducerSend,
    disconnect: mockProducerDisconnect,
  };
  return {
    Kafka: vi.fn().mockImplementation(() => ({
      producer: vi.fn().mockReturnValue(mockProducer),
    })),
    logLevel: { WARN: 4 },
  };
});

vi.mock("node:fs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs")>();
  const { Readable: ReadableStream } = await import("node:stream");

  const makeFakeStream = () =>
    new ReadableStream({
      read() {
        this.push(Buffer.from("file content"));
        this.push(null);
      },
    });

  mockCreateReadStream.mockImplementation(() => makeFakeStream());

  return {
    ...actual,
    default: {
      ...actual,
      writeFileSync: mockWriteFileSync,
      mkdirSync: mockMkdirSync,
      existsSync: mockExistsSync,
      createReadStream: mockCreateReadStream,
    },
    writeFileSync: mockWriteFileSync,
    mkdirSync: mockMkdirSync,
    existsSync: mockExistsSync,
    createReadStream: mockCreateReadStream,
  };
});

import { app } from "../../src/index.js";

// ── Tests ──────────────────────────────────────────────────────────────────

describe("middleware/health.middleware", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("GET /health", () => {
    it("should return liveness status", async () => {
      const res = await request(app).get("/health");
      expect(res.status).toBe(200);
      expect(res.body).toEqual({ status: "ok" });
    });
  });

  describe("GET /ready", () => {
    it("should return readiness status with checks", async () => {
      const res = await request(app).get("/ready");
      expect(res.status).toBe(200);
      expect(res.body.status).toBe("ok");
      expect(res.body.checks).toBeDefined();
      expect(res.body.checks.database).toBe("ok");
    });

    it("should return 503 when database is unavailable", async () => {
      mockQueryRaw.mockRejectedValueOnce(new Error("Connection refused"));

      const res = await request(app).get("/ready");
      expect(res.status).toBe(503);
      expect(res.body.status).toBe("not ready");
      expect(res.body.checks.database).toBe("unavailable");
    });
  });
});
