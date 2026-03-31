// tests/utils/format.util.test.ts — Unit tests for filename sanitization and validation
//
// Pure unit tests — no Express app, no mocks needed. Tests the sanitize/validate
// functions from src/utils/format.util.ts directly.

import { describe, it, expect, beforeAll } from "vitest";

describe("format.util", () => {
  let sanitizeFilename: typeof import("../../src/utils/format.util.js").sanitizeFilename;
  let validateExtension: typeof import("../../src/utils/format.util.js").validateExtension;
  let validateFileSize: typeof import("../../src/utils/format.util.js").validateFileSize;
  let validateSvgContent: typeof import("../../src/utils/format.util.js").validateSvgContent;
  let FileValidationError: typeof import("../../src/utils/format.util.js").FileValidationError;

  beforeAll(async () => {
    const mod = await import("../../src/utils/format.util.js");
    sanitizeFilename = mod.sanitizeFilename;
    validateExtension = mod.validateExtension;
    validateFileSize = mod.validateFileSize;
    validateSvgContent = mod.validateSvgContent;
    FileValidationError = mod.FileValidationError;
  });

  // ── sanitizeFilename ─────────────────────────────────────────────────

  describe("sanitizeFilename", () => {
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
  });

  // ── validateExtension ────────────────────────────────────────────────

  describe("validateExtension", () => {
    it("should accept allowed extensions", () => {
      expect(() => validateExtension(".txt")).not.toThrow();
      expect(() => validateExtension(".pdf")).not.toThrow();
      expect(() => validateExtension(".png")).not.toThrow();
      expect(() => validateExtension(".zip")).not.toThrow();
    });

    it("should reject disallowed extensions", () => {
      expect(() => validateExtension(".exe")).toThrow(FileValidationError);
      expect(() => validateExtension(".bat")).toThrow(FileValidationError);
      expect(() => validateExtension(".sh")).toThrow(FileValidationError);
      expect(() => validateExtension(".dll")).toThrow(FileValidationError);
    });

    it("should reject previously-allowed executable extensions", () => {
      expect(() => validateExtension(".py")).toThrow(FileValidationError);
      expect(() => validateExtension(".js")).toThrow(FileValidationError);
      expect(() => validateExtension(".html")).toThrow(FileValidationError);
      expect(() => validateExtension(".json")).toThrow(FileValidationError);
      expect(() => validateExtension(".bin")).toThrow(FileValidationError);
    });

    it("should reject empty extension", () => {
      expect(() => validateExtension("")).toThrow(FileValidationError);
    });
  });

  // ── validateFileSize ─────────────────────────────────────────────────

  describe("validateFileSize", () => {
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
  });

  // ── validateSvgContent ──────────────────────────────────────────────

  describe("validateSvgContent", () => {
    it("should accept a safe SVG without scripting", () => {
      const buf = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>');
      expect(() => validateSvgContent(buf)).not.toThrow();
    });

    it("should reject SVG with <script> tag", () => {
      const buf = Buffer.from('<svg><script>alert(1)</script></svg>');
      expect(() => validateSvgContent(buf)).toThrow(FileValidationError);
      expect(() => validateSvgContent(buf)).toThrow("dangerous content");
    });

    it("should reject SVG with event handler attribute", () => {
      const buf = Buffer.from('<svg><rect onload="alert(1)"/></svg>');
      expect(() => validateSvgContent(buf)).toThrow(FileValidationError);
    });

    it("should reject SVG with javascript: protocol", () => {
      const buf = Buffer.from('<svg><a href="javascript:alert(1)"><text>click</text></a></svg>');
      expect(() => validateSvgContent(buf)).toThrow(FileValidationError);
    });

    it("should reject SVG with data:text/html URI", () => {
      const buf = Buffer.from('<svg><a href="data:text/html,<script>alert(1)</script>"><text>x</text></a></svg>');
      expect(() => validateSvgContent(buf)).toThrow(FileValidationError);
    });

    it("should reject SVG with <iframe>", () => {
      const buf = Buffer.from('<svg><foreignObject><iframe src="evil.com"/></foreignObject></svg>');
      expect(() => validateSvgContent(buf)).toThrow(FileValidationError);
    });

    it("should reject SVG with <object>", () => {
      const buf = Buffer.from('<svg><object data="evil.swf"/></svg>');
      expect(() => validateSvgContent(buf)).toThrow(FileValidationError);
    });

    it("should reject SVG with <embed>", () => {
      const buf = Buffer.from('<svg><embed src="evil.swf"/></svg>');
      expect(() => validateSvgContent(buf)).toThrow(FileValidationError);
    });

    it("should reject SVG with <foreignObject>", () => {
      const buf = Buffer.from('<svg><foreignObject width="100" height="100"><div>x</div></foreignObject></svg>');
      expect(() => validateSvgContent(buf)).toThrow(FileValidationError);
    });

    it("should be case-insensitive (uppercase SCRIPT tag)", () => {
      const buf = Buffer.from('<SVG><SCRIPT>alert(1)</SCRIPT></SVG>');
      expect(() => validateSvgContent(buf)).toThrow(FileValidationError);
    });
  });

  // ── FileValidationError ──────────────────────────────────────────────

  describe("FileValidationError", () => {
    it("should create FileValidationError with correct properties", () => {
      const err = new FileValidationError("test error", 418);
      expect(err.message).toBe("test error");
      expect(err.statusCode).toBe(418);
      expect(err.name).toBe("FileValidationError");
      expect(err).toBeInstanceOf(Error);
      expect(err).toBeInstanceOf(FileValidationError);
    });
  });
});
