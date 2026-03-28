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
 *
 * SECURITY: The extension value is sanitized before embedding in error messages
 * to prevent log injection or unexpected content in JSON error responses.
 */
export function validateExtension(extension: string): void {
  if (!config.allowedExtensions.has(extension)) {
    // Sanitize extension for error message — only allow alphanumeric and dots
    const safeExt = extension.replace(/[^a-z0-9.]/g, "").slice(0, 20);
    throw new FileValidationError(
      `File type '${safeExt}' is not allowed`,
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
 * Text-based extensions (.txt, .csv, .md, .log) are skipped because
 * they have no reliable magic bytes — `file-type` returns undefined for them.
 *
 * SECURITY: SVG files get content scanning instead of MIME detection — they are
 * XML-based text files that can contain embedded JavaScript. See validateSvgContent().
 */
export async function validateMimeType(
  buffer: Buffer,
  extension: string
): Promise<void> {
  // SVG files need content-level scanning, not magic-byte detection
  if (extension === ".svg") {
    validateSvgContent(buffer);
    return;
  }

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

  // SECURITY: Use exact MIME match only — no prefix matching.
  // Previous code used `detected.mime.startsWith(mime.split("/")[0] + "/")`
  // which allowed type confusion (e.g., image/svg+xml passing for image/png).
  const matches = expectedMimes.some((mime) => detected.mime === mime);

  if (!matches) {
    throw new FileValidationError(
      `File content (${detected.mime}) does not match claimed type '${extension}'`,
      400
    );
  }
}

/**
 * Scan SVG file content for dangerous patterns.
 *
 * SVG is XML-based and can contain embedded JavaScript via <script> tags,
 * event handler attributes (onload, onclick, etc.), and other XSS vectors.
 * This function rejects SVGs containing known dangerous patterns.
 *
 * SECURITY: This is a defense-in-depth measure. The primary defense is serving
 * all downloads with Content-Type: application/octet-stream and
 * Content-Disposition: attachment, which prevents browser rendering.
 */
export function validateSvgContent(buffer: Buffer): void {
  const content = buffer.toString("utf-8").toLowerCase();

  // Patterns that indicate embedded scripting in SVG files
  const dangerousPatterns = [
    /<script[\s>]/,           // <script> tags
    /\bon\w+\s*=/,            // Event handlers: onload=, onclick=, onerror=, etc.
    /javascript\s*:/,         // javascript: protocol in href/xlink:href
    /data\s*:\s*text\/html/,  // data: URIs with HTML content
    /<iframe[\s>]/,           // Embedded iframes
    /<object[\s>]/,           // Embedded objects
    /<embed[\s>]/,            // Embedded content
    /<foreignobject[\s>]/,    // foreignObject can contain arbitrary HTML
  ];

  for (const pattern of dangerousPatterns) {
    if (pattern.test(content)) {
      throw new FileValidationError(
        "SVG file contains potentially dangerous content",
        400
      );
    }
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
