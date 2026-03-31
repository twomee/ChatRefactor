// tests/utils/format.util.mime.test.ts — Tests for validateMimeType
//
// validateMimeType uses a dynamic import of the "file-type" package.
// This file mocks "file-type" so the MIME-detection logic can be tested
// without needing real binary file buffers.

import { describe, it, expect, vi, beforeEach } from "vitest";

// Must be declared before any imports that trigger the module under test
vi.mock("file-type", () => ({
  fileTypeFromBuffer: vi.fn(),
}));

import { validateMimeType, FileValidationError } from "../../src/utils/format.util.js";
import { fileTypeFromBuffer } from "file-type";

const mockFileType = vi.mocked(fileTypeFromBuffer);

describe("validateMimeType", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── SVG delegates to validateSvgContent ────────────────────────────

  it("passes for .svg extension with clean SVG content", async () => {
    const buf = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>');
    await expect(validateMimeType(buf, ".svg")).resolves.toBeUndefined();
    // file-type is NOT called for SVG — content scanning is used instead
    expect(mockFileType).not.toHaveBeenCalled();
  });

  it("throws for .svg with dangerous script content", async () => {
    const buf = Buffer.from('<svg><script>alert(1)</script></svg>');
    await expect(validateMimeType(buf, ".svg")).rejects.toThrow(FileValidationError);
    await expect(validateMimeType(buf, ".svg")).rejects.toThrow("dangerous content");
  });

  // ── Text-based extensions are skipped ──────────────────────────────

  it("skips validation for .txt (no magic bytes expected)", async () => {
    const buf = Buffer.from("hello world");
    await expect(validateMimeType(buf, ".txt")).resolves.toBeUndefined();
    expect(mockFileType).not.toHaveBeenCalled();
  });

  it("skips validation for .csv", async () => {
    const buf = Buffer.from("col1,col2\nval1,val2");
    await expect(validateMimeType(buf, ".csv")).resolves.toBeUndefined();
    expect(mockFileType).not.toHaveBeenCalled();
  });

  it("skips validation for .md", async () => {
    const buf = Buffer.from("# Hello");
    await expect(validateMimeType(buf, ".md")).resolves.toBeUndefined();
    expect(mockFileType).not.toHaveBeenCalled();
  });

  // ── Binary extensions: MIME match passes ───────────────────────────

  it("passes for .png when file-type detects image/png", async () => {
    mockFileType.mockResolvedValue({ mime: "image/png", ext: "png" });
    const buf = Buffer.from("fake-png-bytes");
    await expect(validateMimeType(buf, ".png")).resolves.toBeUndefined();
  });

  it("passes for .pdf when file-type detects application/pdf", async () => {
    mockFileType.mockResolvedValue({ mime: "application/pdf", ext: "pdf" });
    const buf = Buffer.from("fake-pdf-bytes");
    await expect(validateMimeType(buf, ".pdf")).resolves.toBeUndefined();
  });

  it("passes for .jpg when file-type detects image/jpeg", async () => {
    mockFileType.mockResolvedValue({ mime: "image/jpeg", ext: "jpg" });
    const buf = Buffer.from("fake-jpg-bytes");
    await expect(validateMimeType(buf, ".jpg")).resolves.toBeUndefined();
  });

  // ── Binary extensions: MIME mismatch throws ─────────────────────────

  it("throws when file-type detects wrong MIME for .pdf", async () => {
    mockFileType.mockResolvedValue({ mime: "image/png", ext: "png" });
    const buf = Buffer.from("actually-a-png");
    await expect(validateMimeType(buf, ".pdf")).rejects.toThrow(FileValidationError);
    await expect(validateMimeType(buf, ".pdf")).rejects.toThrow("does not match claimed type");
  });

  it("throws when file-type returns undefined for a binary extension", async () => {
    mockFileType.mockResolvedValue(undefined);
    const buf = Buffer.from("garbage-data");
    await expect(validateMimeType(buf, ".png")).rejects.toThrow(FileValidationError);
    await expect(validateMimeType(buf, ".png")).rejects.toThrow("does not match claimed type");
  });

  it("throws for .zip with wrong MIME type", async () => {
    mockFileType.mockResolvedValue({ mime: "image/gif", ext: "gif" });
    const buf = Buffer.from("not-a-zip");
    await expect(validateMimeType(buf, ".zip")).rejects.toThrow(FileValidationError);
  });
});
