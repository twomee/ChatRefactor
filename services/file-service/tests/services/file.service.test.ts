// tests/services/file.service.test.ts — Unit tests for file service business logic
//
// Focuses on edge cases not covered by route integration tests:
// - Path traversal prevention during upload
// - Kafka event failure handling (fire-and-forget error catch)

import { describe, it, expect, vi, beforeEach } from "vitest";

// ── Hoisted mocks ──────────────────────────────────────────────────────────
const { mockPrismaFile, mockQueryRaw } = vi.hoisted(() => ({
  mockPrismaFile: {
    create: vi.fn(),
    findUnique: vi.fn(),
    findMany: vi.fn(),
  },
  mockQueryRaw: vi.fn().mockResolvedValue([{ "?column?": 1 }]),
}));

const { mockExistsSync, mockWriteFileSync, mockMkdirSync } = vi.hoisted(() => ({
  mockExistsSync: vi.fn().mockReturnValue(true),
  mockWriteFileSync: vi.fn(),
  mockMkdirSync: vi.fn(),
}));

const mockProduceEvent = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

vi.mock("@prisma/client", () => ({
  PrismaClient: vi.fn().mockImplementation(() => ({
    file: mockPrismaFile,
    $queryRaw: mockQueryRaw,
  })),
}));

vi.mock("node:fs", () => ({
  default: {
    existsSync: (...args: unknown[]) => mockExistsSync(...args),
    writeFileSync: (...args: unknown[]) => mockWriteFileSync(...args),
    mkdirSync: (...args: unknown[]) => mockMkdirSync(...args),
    createReadStream: vi.fn(),
  },
}));

vi.mock("../../src/kafka/events.js", () => ({
  produceFileUploadedEvent: (...args: unknown[]) => mockProduceEvent(...args),
}));

vi.mock("../../src/kafka/logger.js", () => ({
  logger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
  },
}));

vi.mock("../../src/config/env.config.js", () => ({
  config: {
    nodeEnv: "test",
    port: 8005,
    secretKey: "test-secret",
    uploadDir: "/tmp/file-service-test-uploads",
    maxFileSizeMB: 150,
    allowedExtensions: new Set([".txt", ".pdf", ".jpg", ".png"]),
    databaseUrl: "postgresql://test:test@localhost:5432/test",
    kafkaBrokers: ["localhost:9092"],
  },
}));

describe("services/file.service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("uploadFile", () => {
    it("should upload a valid file and return metadata", async () => {
      const { uploadFile } = await import("../../src/services/file.service.js");

      mockPrismaFile.create.mockResolvedValue({
        id: 1,
        originalName: "test.txt",
        storedPath: "/tmp/file-service-test-uploads/abc_test.txt",
        fileSize: 11,
        senderId: 1,
        roomId: 5,
        uploadedAt: new Date("2026-01-01"),
      });

      const result = await uploadFile(
        Buffer.from("hello world"),
        "test.txt",
        1,
        "alice",
        5
      );

      expect(result.id).toBe(1);
      expect(result.originalName).toBe("test.txt");
      expect(result.fileSize).toBe(11);
      expect(mockWriteFileSync).toHaveBeenCalled();
      expect(mockProduceEvent).toHaveBeenCalled();
    });

    it("should handle Kafka event failure gracefully (fire-and-forget)", async () => {
      const { uploadFile } = await import("../../src/services/file.service.js");

      mockPrismaFile.create.mockResolvedValue({
        id: 2,
        originalName: "test.txt",
        storedPath: "/tmp/file-service-test-uploads/abc_test.txt",
        fileSize: 5,
        senderId: 1,
        roomId: 3,
        uploadedAt: new Date(),
      });

      // Kafka fails — should NOT throw
      mockProduceEvent.mockRejectedValueOnce(new Error("Kafka down"));

      const result = await uploadFile(
        Buffer.from("hello"),
        "test.txt",
        1,
        "alice",
        3
      );

      // Upload still succeeds even though Kafka failed
      expect(result.id).toBe(2);
    });

    it("should reject disallowed file extensions", async () => {
      const { uploadFile } = await import("../../src/services/file.service.js");

      await expect(
        uploadFile(Buffer.from("data"), "script.sh", 1, "alice", 1)
      ).rejects.toThrow();
    });
  });

  describe("getFile", () => {
    it("should return file record for valid file", async () => {
      const { getFile } = await import("../../src/services/file.service.js");

      mockPrismaFile.findUnique.mockResolvedValue({
        id: 1,
        originalName: "test.txt",
        storedPath: "/tmp/file-service-test-uploads/abc_test.txt",
        fileSize: 11,
        senderId: 1,
        roomId: 1,
        uploadedAt: new Date(),
      });
      mockExistsSync.mockReturnValue(true);

      const result = await getFile(1);
      expect(result.id).toBe(1);
      expect(result.originalName).toBe("test.txt");
    });

    it("should throw 404 for non-existent file", async () => {
      const { getFile } = await import("../../src/services/file.service.js");

      mockPrismaFile.findUnique.mockResolvedValue(null);

      await expect(getFile(999)).rejects.toThrow("File not found");
    });

    it("should throw 403 for path traversal on download", async () => {
      const { getFile } = await import("../../src/services/file.service.js");

      mockPrismaFile.findUnique.mockResolvedValue({
        id: 1,
        originalName: "passwd",
        storedPath: "/etc/passwd",
        fileSize: 100,
        senderId: 1,
        roomId: 1,
        uploadedAt: new Date(),
      });

      await expect(getFile(1)).rejects.toThrow("Access denied");
    });

    it("should throw 404 when file missing on disk", async () => {
      const { getFile } = await import("../../src/services/file.service.js");

      mockPrismaFile.findUnique.mockResolvedValue({
        id: 1,
        originalName: "test.txt",
        storedPath: "/tmp/file-service-test-uploads/missing.txt",
        fileSize: 11,
        senderId: 1,
        roomId: 1,
        uploadedAt: new Date(),
      });
      mockExistsSync.mockReturnValue(false);

      await expect(getFile(1)).rejects.toThrow("File not found on disk");
    });
  });

  describe("listRoomFiles", () => {
    it("should return file metadata for a room", async () => {
      const { listRoomFiles } = await import("../../src/services/file.service.js");

      mockPrismaFile.findMany.mockResolvedValue([
        {
          id: 1,
          originalName: "a.txt",
          fileSize: 10,
          senderId: 1,
          roomId: 5,
          uploadedAt: new Date("2026-01-01"),
        },
      ]);

      const result = await listRoomFiles(5);
      expect(result).toHaveLength(1);
      expect(result[0].originalName).toBe("a.txt");
      expect(result[0].uploadedAt).toBe("2026-01-01T00:00:00.000Z");
    });

    it("should return empty array for room with no files", async () => {
      const { listRoomFiles } = await import("../../src/services/file.service.js");

      mockPrismaFile.findMany.mockResolvedValue([]);

      const result = await listRoomFiles(99);
      expect(result).toEqual([]);
    });
  });
});
