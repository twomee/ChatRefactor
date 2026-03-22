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
vi.mock("kafkajs", () => {
  const mockProducer = {
    connect: vi.fn().mockResolvedValue(undefined),
    send: vi.fn().mockResolvedValue(undefined),
    disconnect: vi.fn().mockResolvedValue(undefined),
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

  return {
    ...actual,
    default: {
      ...actual,
      writeFileSync: vi.fn(),
      mkdirSync: vi.fn(),
      existsSync: vi.fn().mockReturnValue(true),
      createReadStream: vi.fn().mockImplementation(() => makeFakeStream()),
    },
    writeFileSync: vi.fn(),
    mkdirSync: vi.fn(),
    existsSync: vi.fn().mockReturnValue(true),
    createReadStream: vi.fn().mockImplementation(() => makeFakeStream()),
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
  });
});

// ── Filename Sanitization Unit Tests ─────────────────────────────────────

describe("Filename Sanitization", () => {
  // Import the utility directly for unit testing
  let sanitizeFilename: typeof import("../src/utils/format.util.js").sanitizeFilename;
  let validateExtension: typeof import("../src/utils/format.util.js").validateExtension;
  let FileValidationError: typeof import("../src/utils/format.util.js").FileValidationError;

  beforeAll(async () => {
    const mod = await import("../src/utils/format.util.js");
    sanitizeFilename = mod.sanitizeFilename;
    validateExtension = mod.validateExtension;
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
