// tests/middleware/auth.middleware.test.ts — Integration tests for JWT auth middleware
//
// Tests the auth middleware behavior through the Express app. Verifies token
// validation, extraction from header/query, and rejection of invalid tokens.

import { describe, it, expect, vi, beforeEach } from "vitest";
import request from "supertest";
import jwt from "jsonwebtoken";

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

// ── Helpers ────────────────────────────────────────────────────────────────

const SECRET_KEY = "test-secret-key-for-jwt-signing";

function generateToken(
  userId: number = 1,
  username: string = "testuser"
): string {
  return jwt.sign({ sub: String(userId), username }, SECRET_KEY, {
    algorithm: "HS256",
    expiresIn: "1h",
  });
}

const validToken = generateToken();

// ── Tests ──────────────────────────────────────────────────────────────────

describe("middleware/auth.middleware", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockExistsSync.mockReturnValue(true);
  });

  it("should reject expired token", async () => {
    const expiredToken = jwt.sign(
      { sub: "1", username: "testuser" },
      SECRET_KEY,
      { algorithm: "HS256", expiresIn: "-1h" }
    );

    const res = await request(app)
      .get("/files/room/1")
      .set("Authorization", `Bearer ${expiredToken}`);

    expect(res.status).toBe(401);
    expect(res.body.error).toContain("Invalid or expired token");
  });

  it("should reject token with wrong secret", async () => {
    const badToken = jwt.sign(
      { sub: "1", username: "testuser" },
      "wrong-secret",
      { algorithm: "HS256" }
    );

    const res = await request(app)
      .get("/files/room/1")
      .set("Authorization", `Bearer ${badToken}`);

    expect(res.status).toBe(401);
  });

  it("should reject malformed token", async () => {
    const res = await request(app)
      .get("/files/room/1")
      .set("Authorization", "Bearer not.a.valid.token");

    expect(res.status).toBe(401);
  });

  it("should reject token missing sub claim", async () => {
    const tokenNoSub = jwt.sign(
      { username: "testuser" },
      SECRET_KEY,
      { algorithm: "HS256", expiresIn: "1h" }
    );

    const res = await request(app)
      .get("/files/room/1")
      .set("Authorization", `Bearer ${tokenNoSub}`);

    expect(res.status).toBe(401);
    expect(res.body.error).toContain("Invalid token payload");
  });

  it("should reject token missing username claim", async () => {
    const tokenNoUsername = jwt.sign(
      { sub: "1" },
      SECRET_KEY,
      { algorithm: "HS256", expiresIn: "1h" }
    );

    const res = await request(app)
      .get("/files/room/1")
      .set("Authorization", `Bearer ${tokenNoUsername}`);

    expect(res.status).toBe(401);
    expect(res.body.error).toContain("Invalid token payload");
  });

  it("should reject token with non-numeric sub (NaN userId)", async () => {
    const tokenBadSub = jwt.sign(
      { sub: "not-a-number", username: "testuser" },
      SECRET_KEY,
      { algorithm: "HS256", expiresIn: "1h" }
    );

    const res = await request(app)
      .get("/files/room/1")
      .set("Authorization", `Bearer ${tokenBadSub}`);

    expect(res.status).toBe(401);
    expect(res.body.error).toContain("Invalid token payload");
  });

  it("should reject Authorization header without Bearer prefix", async () => {
    const res = await request(app)
      .get("/files/room/1")
      .set("Authorization", `Basic ${validToken}`);

    expect(res.status).toBe(401);
    expect(res.body.error).toContain("Authentication required");
  });
});
