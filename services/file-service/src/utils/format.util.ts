// utils/format.util.ts — Filename sanitization matching monolith logic

import path from "node:path";
import { config } from "../config/env.config.js";

export interface SanitizeResult {
  cleanName: string;
  extension: string;
}

/**
 * Sanitize an uploaded filename to prevent security issues.
 *
 * Mirrors the Python monolith logic exactly:
 * 1. Strip directory/path components (prevents path traversal like "../../etc/passwd")
 * 2. Remove null bytes (prevents null byte injection)
 * 3. Strip leading dots (prevents hidden files like ".env", "..secret")
 * 4. Fall back to "unnamed" if nothing remains
 */
export function sanitizeFilename(rawName: string): SanitizeResult {
  // Normalize Windows backslashes to forward slashes before stripping path
  // components. On Linux, path.basename doesn't treat '\' as a separator,
  // so "..\\..\\etc\\passwd" would survive path.basename unchanged.
  const normalized = rawName.replace(/\\/g, "/");

  // path.basename strips all directory components (like Python Path.name)
  let cleanName = path.basename(normalized);

  // Remove null bytes and CRLF characters (prevents header injection via
  // Content-Disposition when the filename is embedded in HTTP headers)
  cleanName = cleanName.replace(/[\0\r\n]/g, "");

  // Strip leading dots to prevent hidden files
  cleanName = cleanName.replace(/^\.+/, "");

  // Fall back to "unnamed" if the name is empty after sanitization
  if (!cleanName) {
    cleanName = "unnamed";
  }

  const extension = path.extname(cleanName).toLowerCase();

  return { cleanName, extension };
}

/**
 * Validate that the file extension is in the allowlist.
 * Returns the lowercase extension if valid, throws a descriptive error if not.
 */
export function validateExtension(extension: string): void {
  if (!config.allowedExtensions.has(extension)) {
    throw new FileValidationError(
      `File type '${extension}' is not allowed`,
      400
    );
  }
}

/**
 * Map of file extensions to their expected MIME type prefixes.
 * Used by validateMimeType to verify the file's magic bytes match the claimed extension.
 * Text-based formats (.txt, .csv, .md, .log, .svg) have no reliable magic bytes
 * and are skipped during validation.
 */
const EXTENSION_MIME_MAP: Record<string, string[]> = {
  ".pdf": ["application/pdf"],
  ".png": ["image/png"],
  ".jpg": ["image/jpeg"],
  ".jpeg": ["image/jpeg"],
  ".gif": ["image/gif"],
  ".webp": ["image/webp"],
  ".mp4": ["video/mp4"],
  ".mp3": ["audio/mpeg"],
  ".wav": ["audio/wav", "audio/x-wav"],
  ".ogg": ["audio/ogg", "video/ogg", "application/ogg"],
  ".doc": ["application/msword", "application/x-cfb"],
  ".docx": ["application/zip", "application/vnd.openxmlformats"],
  ".xls": ["application/vnd.ms-excel", "application/x-cfb"],
  ".xlsx": ["application/zip", "application/vnd.openxmlformats"],
  ".ppt": ["application/vnd.ms-powerpoint", "application/x-cfb"],
  ".pptx": ["application/zip", "application/vnd.openxmlformats"],
  ".zip": ["application/zip"],
  ".gz": ["application/gzip"],
  ".7z": ["application/x-7z-compressed"],
  ".rar": ["application/x-rar-compressed", "application/vnd.rar"],
  ".tar": ["application/x-tar"],
};

/**
 * Validate that the file's magic bytes match the claimed extension.
 * Uses the `file-type` package to detect MIME type from the buffer.
 *
 * Text-based extensions (.txt, .csv, .md, .log, .svg) are skipped because
 * they have no reliable magic bytes — `file-type` returns undefined for them.
 */
export async function validateMimeType(
  buffer: Buffer,
  extension: string
): Promise<void> {
  const expectedMimes = EXTENSION_MIME_MAP[extension];
  if (!expectedMimes) {
    // Text-based format with no magic bytes — skip validation
    return;
  }

  const { fileTypeFromBuffer } = await import("file-type");
  const detected = await fileTypeFromBuffer(buffer);

  if (!detected) {
    throw new FileValidationError(
      `File content does not match claimed type '${extension}'`,
      400
    );
  }

  const matches = expectedMimes.some(
    (mime) => detected.mime === mime || detected.mime.startsWith(mime.split("/")[0] + "/")
  );

  if (!matches) {
    throw new FileValidationError(
      `File content (${detected.mime}) does not match claimed type '${extension}'`,
      400
    );
  }
}

/**
 * Validate that the file size does not exceed the maximum.
 */
export function validateFileSize(sizeBytes: number): void {
  if (sizeBytes > config.maxFileSizeBytes) {
    throw new FileValidationError(
      "File exceeds maximum size of 150 MB",
      413
    );
  }
}

/**
 * Custom error class for file validation failures.
 * Carries an HTTP status code so the route handler can respond appropriately.
 */
export class FileValidationError extends Error {
  public readonly statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "FileValidationError";
    this.statusCode = statusCode;
  }
}
