// config/env.config.ts — Typed environment configuration with fail-fast in production

import crypto from "node:crypto";
import dotenv from "dotenv";
import path from "node:path";

dotenv.config();

const NODE_ENV = process.env.NODE_ENV || "development";

/**
 * Require an environment variable. In production, exits the process immediately
 * if the variable is missing — fail fast and loud, no silent fallback defaults.
 */
function requireEnv(key: string, fallback?: string): string {
  const value = process.env[key];
  if (value !== undefined && value !== "") {
    return value;
  }
  if (NODE_ENV === "production") {
    // eslint-disable-next-line no-console -- Intentional: fail fast and loud before logger is available
    console.error(`FATAL: Required environment variable '${key}' is not set.`);
    process.exit(1);
  }
  if (fallback !== undefined) {
    return fallback;
  }
  return "";
}

export const config = {
  nodeEnv: NODE_ENV,
  port: parseInt(process.env.PORT || "8005", 10),

  // Database — required in all environments. Set via .env file (see .env.example).
  databaseUrl: requireEnv("DATABASE_URL"),

  // Kafka
  kafkaBootstrapServers: requireEnv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:29092"
  ),

  // JWT — must match Auth Service secret exactly.
  // In dev, generate a random key per process to avoid using a predictable default.
  // This means the file-service won't validate auth-service tokens in dev unless
  // SECRET_KEY is explicitly set in .env (which it should be for local dev).
  secretKey: requireEnv("SECRET_KEY") || crypto.randomBytes(48).toString("base64url"),
  algorithm: "HS256" as const,

  // File storage
  uploadDir: path.resolve(process.env.UPLOAD_DIR || "./uploads"),
  maxFileSizeBytes: parseInt(
    process.env.MAX_FILE_SIZE_BYTES || String(150 * 1024 * 1024),
    10
  ),

  // Downstream service URLs
  authServiceUrl: requireEnv("AUTH_SERVICE_URL"), // NOSONAR — service-mesh internal traffic; TLS terminated at ingress

  // Allowed file extensions for upload.
  // SECURITY: Only safe document/media/archive types — no executable or
  // scriptable extensions (.py, .js, .html, .bin, etc.) to prevent XSS
  // if the upload directory ever becomes web-accessible.
  allowedExtensions: new Set([
    // Documents
    ".txt", ".pdf", ".csv", ".md", ".log",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    // Images
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    // NOTE: .svg intentionally excluded — SVG files can contain embedded
    // JavaScript and are an XSS vector if served with image/svg+xml MIME type
    // Audio/Video
    ".mp4", ".mp3", ".wav", ".ogg",
    // Archives
    ".zip", ".tar", ".gz", ".7z", ".rar",
  ]),
} as const;
