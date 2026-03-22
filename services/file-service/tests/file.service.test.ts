// tests/file.service.test.ts — Unit and integration tests for the File Service
//
// Strategy: mock Prisma and Kafka at the module level so we test the actual
// Express routes + business logic without external dependencies.

import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import request from "supertest";
import jwt from "jsonwebtoken";
import path from "node:path";


// ── Hoisted mocks (must be declared with vi.hoisted before vi.mock) ────────
const { mockPrismaFile, mockQueryRaw } = vi.hoisted(() => ({
  mockPrismaFile: {
    create: vi.fn(),
    findUnique: vi.fn(),
    findMany: vi.fn(),
  },
  mockQueryRaw: vi.fn().mockResolvedValue([{ "?column?": 1 }]),
}));

// Track fs mock state so individual tests can override behavior
const { mockExistsSync, mockCreateReadStream, mockWriteFileSync, mockMkdirSync } = vi.hoisted(() => ({
  mockExistsSync: vi.fn().mockReturnValue(true),
  mockCreateReadStream: vi.fn(),
  mockWriteFileSync: vi.fn(),
  mockMkdirSync: vi.fn(),
}));

// ── Mock Prisma ────────────────────────────────────────────────────────────
vi.mock("@prisma/client", () => {
  return {
    PrismaClient: vi.fn().mockImplementation(() => ({
      file: mockPrismaFile,
      $queryRaw: mockQueryRaw,
    })),
  };
});

// ── Mock Kafka ─────────────────────────────────────────────────────────────
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

// ── Mock fs to avoid actual disk writes in tests ───────────────────────────
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

// Now import the app after mocks are in place
import { app } from "../src/index.js";

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
const uploadDir = "/tmp/file-service-test-uploads";

// ── Tests ──────────────────────────────────────────────────────────────────

describe("File Service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Restore default fs mock behavior
    mockExistsSync.mockReturnValue(true);
  });

  // ── Health Endpoints ───────────────────────────────────────────────────

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

  // ── Upload Endpoint ────────────────────────────────────────────────────

  describe("POST /files/upload", () => {
    it("should upload a file successfully", async () => {
      const mockRecord = {
        id: 1,
        originalName: "test.txt",
        storedPath: path.join(uploadDir, "abc123_test.txt"),
        fileSize: 11,
        senderId: 1,
        roomId: 1,
        uploadedAt: new Date("2024-01-01T00:00:00Z"),
      };
      mockPrismaFile.create.mockResolvedValue(mockRecord);

      const res = await request(app)
        .post("/files/upload?room_id=1")
        .set("Authorization", `Bearer ${validToken}`)
        .attach("file", Buffer.from("hello world"), "test.txt");

      expect(res.status).toBe(201);
      expect(res.body.id).toBe(1);
      expect(res.body.originalName).toBe("test.txt");
      expect(res.body.fileSize).toBe(11);
      expect(res.body.roomId).toBe(1);
      expect(mockPrismaFile.create).toHaveBeenCalledOnce();
    });

    it("should reject invalid file extension", async () => {
      const res = await request(app)
        .post("/files/upload?room_id=1")
        .set("Authorization", `Bearer ${validToken}`)
        .attach("file", Buffer.from("data"), "malware.exe");

      expect(res.status).toBe(400);
      expect(res.body.error).toContain("not allowed");
    });

    it("should upload small file successfully (multer size check defers to service)", async () => {
      const mockRecord = {
        id: 2,
        originalName: "small.txt",
        storedPath: path.join(uploadDir, "def456_small.txt"),
        fileSize: 5,
        senderId: 1,
        roomId: 1,
        uploadedAt: new Date("2024-01-01T00:00:00Z"),
      };
      mockPrismaFile.create.mockResolvedValue(mockRecord);

      const res = await request(app)
        .post("/files/upload?room_id=1")
        .set("Authorization", `Bearer ${validToken}`)
        .attach("file", Buffer.from("small"), "small.txt");

      expect(res.status).toBe(201);
    });

    it("should return 401 when no auth token provided", async () => {
      const res = await request(app)
        .post("/files/upload?room_id=1")
        .attach("file", Buffer.from("hello"), "test.txt");

      expect(res.status).toBe(401);
      expect(res.body.error).toContain("Authentication required");
    });

    it("should return 400 when room_id is missing", async () => {
      const res = await request(app)
        .post("/files/upload")
        .set("Authorization", `Bearer ${validToken}`)
        .attach("file", Buffer.from("hello"), "test.txt");

      expect(res.status).toBe(400);
      expect(res.body.error).toContain("room_id");
    });

    it("should return 400 when no file is provided", async () => {
      const res = await request(app)
        .post("/files/upload?room_id=1")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(400);
      expect(res.body.error).toContain("No file provided");
    });

    it("should return 400 when room_id is not a number", async () => {
      const res = await request(app)
        .post("/files/upload?room_id=abc")
        .set("Authorization", `Bearer ${validToken}`)
        .attach("file", Buffer.from("hello"), "test.txt");

      expect(res.status).toBe(400);
      expect(res.body.error).toContain("room_id");
    });

    it("should return 500 when database create fails", async () => {
      mockPrismaFile.create.mockRejectedValueOnce(new Error("DB connection lost"));

      const res = await request(app)
        .post("/files/upload?room_id=1")
        .set("Authorization", `Bearer ${validToken}`)
        .attach("file", Buffer.from("hello"), "test.txt");

      expect(res.status).toBe(500);
      expect(res.body.error).toBe("Internal server error");
    });
  });

  // ── Download Endpoint ──────────────────────────────────────────────────

  describe("GET /files/download/:fileId", () => {
    // The mock fs.createReadStream pushes "file content" (12 bytes).
    // fileSize must match so Content-Length doesn't cause a parse error in supertest.
    const MOCK_STREAM_CONTENT_LENGTH = 12; // "file content".length

    it("should download a file successfully", async () => {
      const mockRecord = {
        id: 1,
        originalName: "test.txt",
        storedPath: path.join(uploadDir, "abc123_test.txt"),
        fileSize: MOCK_STREAM_CONTENT_LENGTH,
        senderId: 1,
        roomId: 1,
        uploadedAt: new Date("2024-01-01T00:00:00Z"),
      };
      mockPrismaFile.findUnique.mockResolvedValue(mockRecord);

      const res = await request(app)
        .get("/files/download/1")
        .set("Authorization", `Bearer ${validToken}`)
        .buffer(true);

      expect(res.status).toBe(200);
      expect(res.headers["content-type"]).toBe("application/octet-stream");
      expect(res.headers["content-disposition"]).toContain("test.txt");
      expect(mockPrismaFile.findUnique).toHaveBeenCalledWith({
        where: { id: 1 },
      });
    });

    it("should accept token from query parameter", async () => {
      const mockRecord = {
        id: 1,
        originalName: "test.txt",
        storedPath: path.join(uploadDir, "abc123_test.txt"),
        fileSize: MOCK_STREAM_CONTENT_LENGTH,
        senderId: 1,
        roomId: 1,
        uploadedAt: new Date("2024-01-01T00:00:00Z"),
      };
      mockPrismaFile.findUnique.mockResolvedValue(mockRecord);

      const res = await request(app)
        .get(`/files/download/1?token=${validToken}`)
        .buffer(true);

      expect(res.status).toBe(200);
    });

    it("should return 404 when file not found", async () => {
      mockPrismaFile.findUnique.mockResolvedValue(null);

      const res = await request(app)
        .get("/files/download/999")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(404);
      expect(res.body.error).toContain("not found");
    });

    it("should return 401 when no auth token provided", async () => {
      const res = await request(app).get("/files/download/1");

      expect(res.status).toBe(401);
    });

    it("should return 400 when fileId is not a number", async () => {
      const res = await request(app)
        .get("/files/download/abc")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(400);
      expect(res.body.error).toContain("fileId must be a number");
    });

    it("should return 403 when stored path is outside upload directory (path traversal)", async () => {
      const mockRecord = {
        id: 1,
        originalName: "secret.txt",
        storedPath: "/etc/passwd",
        fileSize: MOCK_STREAM_CONTENT_LENGTH,
        senderId: 1,
        roomId: 1,
        uploadedAt: new Date("2024-01-01T00:00:00Z"),
      };
      mockPrismaFile.findUnique.mockResolvedValue(mockRecord);

      const res = await request(app)
        .get("/files/download/1")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(403);
      expect(res.body.error).toContain("Access denied");
    });

    it("should return 404 when file record exists but file is missing on disk", async () => {
      const mockRecord = {
        id: 1,
        originalName: "deleted.txt",
        storedPath: path.join(uploadDir, "abc123_deleted.txt"),
        fileSize: MOCK_STREAM_CONTENT_LENGTH,
        senderId: 1,
        roomId: 1,
        uploadedAt: new Date("2024-01-01T00:00:00Z"),
      };
      mockPrismaFile.findUnique.mockResolvedValue(mockRecord);
      mockExistsSync.mockReturnValue(false);

      const res = await request(app)
        .get("/files/download/1")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(404);
      expect(res.body.error).toContain("not found on disk");
    });

    it("should return 500 when database query fails on download", async () => {
      mockPrismaFile.findUnique.mockRejectedValueOnce(new Error("DB error"));

      const res = await request(app)
        .get("/files/download/1")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(500);
      expect(res.body.error).toBe("Internal server error");
    });
  });

  // ── List Room Files Endpoint ───────────────────────────────────────────

  describe("GET /files/room/:roomId", () => {
    it("should list files in a room", async () => {
      const mockFiles = [
        {
          id: 1,
          originalName: "file1.txt",
          fileSize: 100,
          senderId: 1,
          roomId: 1,
          uploadedAt: new Date("2024-01-01T00:00:00Z"),
        },
        {
          id: 2,
          originalName: "file2.pdf",
          fileSize: 200,
          senderId: 2,
          roomId: 1,
          uploadedAt: new Date("2024-01-02T00:00:00Z"),
        },
      ];
      mockPrismaFile.findMany.mockResolvedValue(mockFiles);

      const res = await request(app)
        .get("/files/room/1")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
      expect(res.body[0].originalName).toBe("file1.txt");
      expect(res.body[1].originalName).toBe("file2.pdf");
    });

    it("should return empty array for room with no files", async () => {
      mockPrismaFile.findMany.mockResolvedValue([]);

      const res = await request(app)
        .get("/files/room/99")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(200);
      expect(res.body).toEqual([]);
    });

    it("should return 401 when no auth token provided", async () => {
      const res = await request(app).get("/files/room/1");

      expect(res.status).toBe(401);
    });

    it("should return 400 when roomId is not a number", async () => {
      const res = await request(app)
        .get("/files/room/abc")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(400);
      expect(res.body.error).toContain("roomId must be a number");
    });

    it("should return 500 when database query fails", async () => {
      mockPrismaFile.findMany.mockRejectedValueOnce(new Error("DB error"));

      const res = await request(app)
        .get("/files/room/1")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(500);
      expect(res.body.error).toBe("Internal server error");
    });
  });

  // ── Auth Middleware ────────────────────────────────────────────────────

  describe("Auth Middleware", () => {
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
});

// ── Filename Sanitization Unit Tests ─────────────────────────────────────

describe("Filename Sanitization", () => {
  // Import the utility directly for unit testing
  let sanitizeFilename: typeof import("../src/utils/format.util.js").sanitizeFilename;
  let validateExtension: typeof import("../src/utils/format.util.js").validateExtension;
  let validateFileSize: typeof import("../src/utils/format.util.js").validateFileSize;
  let FileValidationError: typeof import("../src/utils/format.util.js").FileValidationError;

  beforeAll(async () => {
    const mod = await import("../src/utils/format.util.js");
    sanitizeFilename = mod.sanitizeFilename;
    validateExtension = mod.validateExtension;
    validateFileSize = mod.validateFileSize;
    FileValidationError = mod.FileValidationError;
  });

  it("should strip path traversal components", () => {
    const result = sanitizeFilename("../../etc/passwd");
    expect(result.cleanName).toBe("passwd");
    expect(result.extension).toBe("");
  });

  it("should strip Windows-style path traversal", () => {
    const result = sanitizeFilename("..\\..\\windows\\system32\\config.txt");
    expect(result.cleanName).toBe("config.txt");
    expect(result.extension).toBe(".txt");
  });

  it("should remove null bytes", () => {
    const result = sanitizeFilename("test\x00.txt");
    expect(result.cleanName).toBe("test.txt");
    expect(result.cleanName).not.toContain("\x00");
  });

  it("should remove CRLF characters", () => {
    const result = sanitizeFilename("test\r\n.txt");
    expect(result.cleanName).toBe("test.txt");
    expect(result.cleanName).not.toContain("\r");
    expect(result.cleanName).not.toContain("\n");
  });

  it("should remove lone CR character", () => {
    const result = sanitizeFilename("test\r.txt");
    expect(result.cleanName).toBe("test.txt");
  });

  it("should remove lone LF character", () => {
    const result = sanitizeFilename("test\n.txt");
    expect(result.cleanName).toBe("test.txt");
  });

  it("should strip leading dots (hidden files)", () => {
    const result = sanitizeFilename(".env");
    expect(result.cleanName).toBe("env");
    expect(result.cleanName).not.toMatch(/^\./);
  });

  it("should strip multiple leading dots", () => {
    const result = sanitizeFilename("..secret");
    expect(result.cleanName).toBe("secret");
  });

  it("should handle .dotfile with nested path", () => {
    const result = sanitizeFilename("/home/user/.bashrc");
    expect(result.cleanName).toBe("bashrc");
  });

  it("should fall back to 'unnamed' for empty result", () => {
    const result = sanitizeFilename("...");
    expect(result.cleanName).toBe("unnamed");
  });

  it("should fall back to 'unnamed' for null bytes only", () => {
    const result = sanitizeFilename("\x00\x00");
    expect(result.cleanName).toBe("unnamed");
  });

  it("should preserve valid filenames", () => {
    const result = sanitizeFilename("report-2024.pdf");
    expect(result.cleanName).toBe("report-2024.pdf");
    expect(result.extension).toBe(".pdf");
  });

  it("should lowercase the extension", () => {
    const result = sanitizeFilename("IMAGE.PNG");
    expect(result.extension).toBe(".png");
  });

  // Extension validation tests
  it("should accept allowed extensions", () => {
    expect(() => validateExtension(".txt")).not.toThrow();
    expect(() => validateExtension(".pdf")).not.toThrow();
    expect(() => validateExtension(".png")).not.toThrow();
    expect(() => validateExtension(".json")).not.toThrow();
  });

  it("should reject disallowed extensions", () => {
    expect(() => validateExtension(".exe")).toThrow(FileValidationError);
    expect(() => validateExtension(".bat")).toThrow(FileValidationError);
    expect(() => validateExtension(".sh")).toThrow(FileValidationError);
    expect(() => validateExtension(".dll")).toThrow(FileValidationError);
  });

  it("should reject empty extension", () => {
    expect(() => validateExtension("")).toThrow(FileValidationError);
  });

  // File size validation tests
  it("should accept file within size limit", () => {
    expect(() => validateFileSize(1024)).not.toThrow();
    expect(() => validateFileSize(0)).not.toThrow();
  });

  it("should reject file exceeding size limit", () => {
    // Default max is 150 * 1024 * 1024 = 157286400
    const oversized = 200 * 1024 * 1024;
    expect(() => validateFileSize(oversized)).toThrow(FileValidationError);
    expect(() => validateFileSize(oversized)).toThrow("exceeds maximum size");
  });

  // FileValidationError
  it("should create FileValidationError with correct properties", () => {
    const err = new FileValidationError("test error", 418);
    expect(err.message).toBe("test error");
    expect(err.statusCode).toBe(418);
    expect(err.name).toBe("FileValidationError");
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(FileValidationError);
  });
});

// ── Correlation ID Tests ─────────────────────────────────────────────────

describe("Correlation ID", () => {
  it("should echo back X-Request-ID if provided", async () => {
    const res = await request(app)
      .get("/health")
      .set("X-Request-ID", "test-correlation-123");

    expect(res.headers["x-request-id"]).toBe("test-correlation-123");
  });

  it("should generate a correlation ID if none provided", async () => {
    const res = await request(app).get("/health");

    expect(res.headers["x-request-id"]).toBeDefined();
    // UUID v4 format check
    expect(res.headers["x-request-id"]).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    );
  });
});

// ── Kafka Producer Unit Tests ─────────────────────────────────────────────

describe("Kafka Producer", () => {
  let initProducer: typeof import("../src/kafka/producer.js").initProducer;
  let produce: typeof import("../src/kafka/producer.js").produce;
  let shutdownProducer: typeof import("../src/kafka/producer.js").shutdownProducer;
  let isKafkaAvailable: typeof import("../src/kafka/producer.js").isKafkaAvailable;

  beforeAll(async () => {
    const mod = await import("../src/kafka/producer.js");
    initProducer = mod.initProducer;
    produce = mod.produce;
    shutdownProducer = mod.shutdownProducer;
    isKafkaAvailable = mod.isKafkaAvailable;
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should connect successfully and mark kafka as available", async () => {
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();
    expect(isKafkaAvailable()).toBe(true);
  });

  it("should handle connection failure gracefully", async () => {
    mockProducerConnect.mockRejectedValueOnce(new Error("Connection refused"));
    await initProducer();
    expect(isKafkaAvailable()).toBe(false);
  });

  it("should produce a message successfully when connected", async () => {
    // First ensure kafka is connected
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();

    mockProducerSend.mockResolvedValueOnce(undefined);
    const result = await produce("test-topic", "key1", { data: "value" });
    expect(result).toBe(true);
    expect(mockProducerSend).toHaveBeenCalledWith({
      topic: "test-topic",
      messages: [{ key: "key1", value: JSON.stringify({ data: "value" }) }],
    });
  });

  it("should return false when produce fails", async () => {
    // First ensure kafka is connected
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();

    mockProducerSend.mockRejectedValueOnce(new Error("Broker not available"));
    const result = await produce("test-topic", "key1", { data: "value" });
    expect(result).toBe(false);
  });

  it("should return false when kafka is not available", async () => {
    // Simulate failed connection
    mockProducerConnect.mockRejectedValueOnce(new Error("Connection refused"));
    await initProducer();

    const result = await produce("test-topic", "key1", { data: "value" });
    expect(result).toBe(false);
  });

  it("should disconnect gracefully during shutdown", async () => {
    // First connect
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();
    expect(isKafkaAvailable()).toBe(true);

    // Then shutdown
    mockProducerDisconnect.mockResolvedValueOnce(undefined);
    await shutdownProducer();
    expect(isKafkaAvailable()).toBe(false);
  });

  it("should handle disconnect error gracefully during shutdown", async () => {
    // First connect
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();

    // Disconnect throws
    mockProducerDisconnect.mockRejectedValueOnce(new Error("Disconnect error"));
    await shutdownProducer();
    // Should not throw, just log warning
    expect(isKafkaAvailable()).toBe(false);
  });

  it("should handle shutdown when producer is null (never connected)", async () => {
    // Simulate failed connection so producer stays null
    mockProducerConnect.mockRejectedValueOnce(new Error("Connection refused"));
    await initProducer();

    // Shutdown should not throw even with null producer
    await shutdownProducer();
    expect(isKafkaAvailable()).toBe(false);
  });
});

// ── Kafka Events Unit Tests ──────────────────────────────────────────────

describe("Kafka Events", () => {
  let produceFileUploadedEvent: typeof import("../src/kafka/events.js").produceFileUploadedEvent;
  let initProducer: typeof import("../src/kafka/producer.js").initProducer;

  beforeAll(async () => {
    const events = await import("../src/kafka/events.js");
    const producer = await import("../src/kafka/producer.js");
    produceFileUploadedEvent = events.produceFileUploadedEvent;
    initProducer = producer.initProducer;
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should produce event successfully and return true", async () => {
    // Connect kafka first
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();
    mockProducerSend.mockResolvedValueOnce(undefined);

    const event = {
      file_id: 1,
      filename: "test.txt",
      size: 1024,
      from: "testuser",
      room_id: 5,
      timestamp: new Date().toISOString(),
    };

    const result = await produceFileUploadedEvent(event);
    expect(result).toBe(true);
  });

  it("should return false when kafka is unavailable", async () => {
    // Kafka not connected
    mockProducerConnect.mockRejectedValueOnce(new Error("Connection refused"));
    await initProducer();

    const event = {
      file_id: 2,
      filename: "report.pdf",
      size: 2048,
      from: "alice",
      room_id: 3,
      timestamp: new Date().toISOString(),
    };

    const result = await produceFileUploadedEvent(event);
    expect(result).toBe(false);
  });
});
