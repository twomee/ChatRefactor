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
