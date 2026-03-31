// services/file.service.ts — Business logic for file operations
//
// Separation of concerns: this module contains ALL business logic.
// The route handler (controller) is thin — it just extracts request data,
// calls this service, and formats the HTTP response.
//
// This service knows about:
//   - Filename sanitization and validation
//   - File storage on disk
//   - Prisma for metadata persistence
//   - Kafka events for real-time notifications
//
// It does NOT know about Express request/response objects.

import fs from "node:fs";
import { mkdir, writeFile, unlink } from "node:fs/promises";
import path from "node:path";
import { v4 as uuidv4 } from "uuid";
import { PrismaClient } from "@prisma/client";

import { config } from "../config/env.config.js";
import {
  sanitizeFilename,
  validateExtension,
  validateFileSize,
  validateMimeType,
  FileValidationError,
} from "../utils/format.util.js";
import { produceFileUploadedEvent } from "../kafka/events.js";
import { logger } from "../kafka/logger.js";
import { filesUploadedTotal, fileUploadSizeBytes, filesDownloadedTotal } from "../middleware/metrics.middleware.js";
import type { FileUploadResult, FileRecord, FileMetadataResponse } from "../types/file.types.js";

const prisma = new PrismaClient();

/** Parameters for uploadFile — exactly one of roomId or recipientId must be set. */
export interface UploadFileParams {
  file: Express.Multer.File;
  senderId: number;
  senderName: string;
  roomId?: number;
  recipientId?: number;
  recipientName?: string;
  isPrivate?: boolean;
}

/**
 * Upload a file: sanitize, validate, store to disk, save metadata, produce Kafka event.
 *
 * Accepts either a roomId (room upload) or recipientId + recipientName (PM upload).
 * Throws FileValidationError for invalid extension or oversized files.
 * The caller (route handler) catches these and maps to HTTP status codes.
 *
 * @deprecated positional overload — use params object instead
 */
export async function uploadFile(params: UploadFileParams): Promise<FileUploadResult> {
  const {
    file,
    senderId,
    senderName,
    roomId,
    recipientId,
    recipientName,
    isPrivate = false,
  } = params;

  const fileBuffer = file.buffer;
  const originalFilename = file.originalname;

  try {
    // 1. Sanitize filename (strip path components, null bytes, leading dots)
    const { cleanName, extension } = sanitizeFilename(originalFilename);

    // 2. Validate extension against allowlist
    validateExtension(extension);

    // 3. Validate file size
    validateFileSize(fileBuffer.length);

    // 3b. Validate MIME type matches claimed extension (magic byte check)
    await validateMimeType(fileBuffer, extension);

    // 4. Generate unique stored filename with UUID prefix
    const storedName = `${uuidv4().replace(/-/g, "")}_${cleanName}`;
    const destPath = path.join(config.uploadDir, storedName);

    // 5. Safety check: ensure resolved path is inside upload directory
    //    Prevents any path traversal that survived sanitization
    const resolvedDest = path.resolve(destPath);
    const resolvedUploadDir = path.resolve(config.uploadDir);
    if (!resolvedDest.startsWith(resolvedUploadDir + path.sep) && resolvedDest !== resolvedUploadDir) {
      logger.error("Path traversal blocked during upload", {
        attemptedPath: destPath,
        originalFilename,
      });
      throw new FileValidationError("Invalid filename", 400);
    }

    // 6. Ensure upload directory exists (async to avoid blocking the event loop)
    await mkdir(config.uploadDir, { recursive: true });

    // 7. Write file to disk
    await writeFile(destPath, fileBuffer);

    // 8. Save metadata to database. If DB insert fails, clean up the orphaned file.
    let record;
    try {
      record = await prisma.file.create({
        data: {
          originalName: cleanName,
          storedPath: destPath,
          fileSize: fileBuffer.length,
          senderId,
          senderName,
          roomId: roomId ?? null,
          recipientId: recipientId ?? null,
          isPrivate,
        },
      });
    } catch (dbError) {
      await unlink(destPath).catch((unlinkErr) => {
        logger.warn("Failed to clean up orphaned file after DB error", {
          destPath,
          error: unlinkErr instanceof Error ? unlinkErr.message : String(unlinkErr),
        });
      });
      throw dbError;
    }

    logger.info("File uploaded", {
      fileId: record.id,
      filename: cleanName,
      size: fileBuffer.length,
      roomId: roomId ?? null,
      recipientId: recipientId ?? null,
      isPrivate,
      senderId,
    });

    // 9. Produce Kafka event (fire-and-forget — don't block the upload response)
    produceFileUploadedEvent({
      file_id: record.id,
      filename: cleanName,
      size: fileBuffer.length,
      from: senderName,
      sender_id: senderId,
      room_id: roomId ?? null,
      ...(recipientName !== undefined && { to: recipientName }),
      recipient_id: recipientId ?? null,
      is_private: isPrivate,
      timestamp: new Date().toISOString(),
    }).catch((err) => {
      logger.warn("Failed to produce file.uploaded event", {
        fileId: record.id,
        error: err instanceof Error ? err.message : String(err),
      });
    });

    // Track successful upload metrics
    filesUploadedTotal.inc({ status: "success" });
    fileUploadSizeBytes.observe(fileBuffer.length);

    return {
      id: record.id,
      originalName: record.originalName,
      fileSize: record.fileSize,
      senderId: record.senderId,
      roomId: record.roomId,
      recipientId: record.recipientId,
      isPrivate: record.isPrivate,
      uploadedAt: record.uploadedAt,
    };
  } catch (error) {
    // Track upload failure metrics
    if (error instanceof FileValidationError) {
      filesUploadedTotal.inc({ status: "validation_error" });
    } else {
      filesUploadedTotal.inc({ status: "error" });
    }
    throw error;
  }
}

/**
 * Get a file record by ID for download.
 *
 * Performs path traversal prevention on the stored path — even though we control
 * what goes into the DB, defense in depth means we verify on read too.
 *
 * Returns the file record with the stored path, or throws an error.
 */
export async function getFile(fileId: number): Promise<FileRecord> {
  try {
    const record = await prisma.file.findUnique({ where: { id: fileId } });

    if (!record) {
      throw new FileValidationError("File not found", 404);
    }

    // SECURITY: Verify stored path is inside upload directory
    const resolvedStored = path.resolve(record.storedPath);
    const resolvedUploadDir = path.resolve(config.uploadDir);
    if (!resolvedStored.startsWith(resolvedUploadDir + path.sep) && resolvedStored !== resolvedUploadDir) {
      logger.error("Path traversal detected on download", {
        fileId,
        storedPath: record.storedPath,
      });
      throw new FileValidationError("Access denied", 403);
    }

    // Verify file exists on disk
    if (!fs.existsSync(record.storedPath)) {
      logger.warn("File missing on disk", {
        fileId,
        storedPath: record.storedPath,
      });
      throw new FileValidationError("File not found on disk", 404);
    }

    filesDownloadedTotal.inc({ status: "success" });

    return {
      id: record.id,
      originalName: record.originalName,
      storedPath: record.storedPath,
      fileSize: record.fileSize,
      senderId: record.senderId,
      roomId: record.roomId,
      recipientId: record.recipientId,
      isPrivate: record.isPrivate ?? false,
      uploadedAt: record.uploadedAt,
    };
  } catch (error) {
    filesDownloadedTotal.inc({ status: "error" });
    throw error;
  }
}

/**
 * List all files in a room. Returns metadata (no file content).
 */
export async function listRoomFiles(roomId: number): Promise<FileMetadataResponse[]> {
  const files = await prisma.file.findMany({
    where: { roomId },
    orderBy: { uploadedAt: "desc" },
  });

  return files.map((f) => ({
    id: f.id,
    originalName: f.originalName,
    fileSize: f.fileSize,
    senderId: f.senderId,
    senderName: f.senderName ?? `User #${f.senderId}`,
    roomId: f.roomId ?? roomId, // roomId is always set here (WHERE clause), but narrowed to number for the response type
    uploadedAt: f.uploadedAt.toISOString(),
  }));
}

// Re-export for route handler error handling
export { FileValidationError };
