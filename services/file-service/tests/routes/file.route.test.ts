// tests/routes/file.route.test.ts — Integration tests for file route endpoints
//
// Tests POST /files/upload, GET /files/download/:fileId, GET /files/room/:roomId
// through the Express app with mocked Prisma, Kafka, and filesystem.

import { describe, it, expect, vi, beforeEach } from "vitest";
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

const { mockExistsSync, mockCreateReadStream, mockWriteFileSync, mockMkdirSync } = vi.hoisted(() => ({
  mockExistsSync: vi.fn().mockReturnValue(true),
  mockCreateReadStream: vi.fn(),
  mockWriteFileSync: vi.fn(),
  mockMkdirSync: vi.fn(),
}));

// ── Mock Prisma ────────────────────────────────────────────────────────────
vi.mock("@prisma/client", () => {
  return {
    PrismaClient: vi.fn().mockImplementation(function () {
      return { file: mockPrismaFile, $queryRaw: mockQueryRaw };
    }),
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
    Kafka: vi.fn().mockImplementation(function () {
      return { producer: vi.fn().mockReturnValue(mockProducer) };
    }),
    logLevel: { WARN: 4 },
  };
});

// ── Mock auth client ───────────────────────────────────────────────────────
const mockGetUserByUsername = vi.hoisted(() => vi.fn());
vi.mock("../../src/clients/auth.client.js", () => ({
  getUserByUsername: mockGetUserByUsername,
}));

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
const uploadDir = "/tmp/file-service-test-uploads";

// ── Tests ──────────────────────────────────────────────────────────────────

describe("routes/file.route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockExistsSync.mockReturnValue(true);
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

    it("should upload a PM file with ?recipient=bob", async () => {
      mockGetUserByUsername.mockResolvedValue({ id: 7, username: "bob" });
      const mockRecord = {
        id: 2, originalName: "doc.txt", storedPath: "/app/uploads/abc_doc.txt",
        fileSize: 11, senderId: 1, senderName: "alice", roomId: null, recipientId: 7, isPrivate: true,
        uploadedAt: new Date(),
      };
      mockPrismaFile.create.mockResolvedValue(mockRecord);

      const res = await request(app)
        .post("/files/upload?recipient=bob")
        .set("Authorization", `Bearer ${validToken}`)
        .attach("file", Buffer.from("hello world"), "doc.txt");

      expect(res.status).toBe(201);
      expect(res.body.recipientId).toBe(7);
      expect(res.body.isPrivate).toBe(true);
      // Verify the DB record was created with PM-specific fields
      expect(mockPrismaFile.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            recipientId: 7,
            isPrivate: true,
            roomId: null,
          }),
        })
      );
    });

    it("should return 400 if both room_id and recipient are provided", async () => {
      const res = await request(app)
        .post("/files/upload?room_id=1&recipient=bob")
        .set("Authorization", `Bearer ${validToken}`)
        .attach("file", Buffer.from("content"), "test.txt");

      expect(res.status).toBe(400);
      expect(res.body.error).toMatch(/room_id.*recipient|mutually exclusive/i);
    });

    it("should return 400 if neither room_id nor recipient is provided", async () => {
      const res = await request(app)
        .post("/files/upload")
        .set("Authorization", `Bearer ${validToken}`)
        .attach("file", Buffer.from("content"), "test.txt");

      expect(res.status).toBe(400);
    });

    it("should return 404 if recipient username does not exist", async () => {
      mockGetUserByUsername.mockResolvedValue(null);
      const res = await request(app)
        .post("/files/upload?recipient=ghost")
        .set("Authorization", `Bearer ${validToken}`)
        .attach("file", Buffer.from("content"), "test.txt");

      expect(res.status).toBe(404);
      expect(res.body.error).toMatch(/recipient|not found/i);
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

    it("should return 403 if requester is not sender or recipient of a private file", async () => {
      // validToken is for userId=1; file belongs to sender=2, recipient=7; user 1 is neither
      const privateFile = {
        id: 99, originalName: "secret.txt", storedPath: path.join(uploadDir, "secret.txt"),
        fileSize: 10, senderId: 2, senderName: "other", recipientId: 7, isPrivate: true,
        roomId: null, uploadedAt: new Date(),
      };
      mockPrismaFile.findUnique.mockResolvedValue(privateFile);

      const res = await request(app)
        .get("/files/download/99")
        .set("Authorization", `Bearer ${validToken}`);

      expect(res.status).toBe(403);
    });

    it("should allow sender to download their own private file", async () => {
      // validToken is for userId=1; sender=1 matches the current user
      const privateFile = {
        id: 100, originalName: "mine.txt", storedPath: path.join(uploadDir, "mine.txt"),
        fileSize: 12, senderId: 1, senderName: "alice", recipientId: 7, isPrivate: true,
        roomId: null, uploadedAt: new Date(),
      };
      mockPrismaFile.findUnique.mockResolvedValue(privateFile);

      const res = await request(app)
        .get("/files/download/100")
        .set("Authorization", `Bearer ${validToken}`)
        .buffer(true);

      expect(res.status).toBe(200);
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
});
