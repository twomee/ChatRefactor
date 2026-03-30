// routes/file.route.ts — Thin controller layer for file endpoints
//
// This is a thin controller — it extracts data from the HTTP request,
// delegates to the file service for business logic, and formats the response.
// No business logic lives here.

import { Router } from "express";
import type { Request, Response } from "express";
import fs from "node:fs";

import { authMiddleware } from "../middleware/auth.middleware.js";
import {
  uploadFile,
  getFile,
  listRoomFiles,
  FileValidationError,
} from "../services/file.service.js";
import { getUserByUsername } from "../clients/auth.client.js";
import type { AuthenticatedRequest } from "../types/file.types.js";
import { logger } from "../kafka/logger.js";

export const fileRouter = Router();

/**
 * POST /files/upload?room_id=X
 *
 * Multipart file upload. Multer processes the file and attaches it to req.file.
 * The multer middleware is configured in the entry point (index.ts) and applied
 * before this route.
 */
fileRouter.post(
  "/upload",
  authMiddleware as never,
  async (req: Request, res: Response): Promise<void> => {
    const authReq = req as AuthenticatedRequest;
    try {
      const roomIdParam = req.query.room_id as string | undefined;
      const recipientParam = req.query.recipient as string | undefined;

      // Exactly one of room_id or recipient is required
      if (roomIdParam && recipientParam) {
        res.status(400).json({ error: "room_id and recipient are mutually exclusive" });
        return;
      }
      if (!roomIdParam && !recipientParam) {
        res.status(400).json({ error: "Either room_id or recipient is required" });
        return;
      }

      const file = req.file;
      if (!file) {
        res.status(400).json({ error: "No file provided" });
        return;
      }

      const senderId = authReq.user.userId;
      const senderName = authReq.user.username;

      let roomId: number | undefined;
      let recipientId: number | undefined;
      let recipientName: string | undefined;

      if (roomIdParam) {
        roomId = parseInt(roomIdParam, 10);
        if (isNaN(roomId)) {
          res.status(400).json({ error: "Invalid room_id: must be a number" });
          return;
        }
      } else {
        // PM file upload: resolve recipient username to numeric ID via auth service
        const recipient = await getUserByUsername(recipientParam!);
        if (!recipient) {
          res.status(404).json({ error: "Recipient not found" });
          return;
        }
        recipientId = recipient.id;
        recipientName = recipient.username;
      }

      const result = await uploadFile({
        file,
        senderId,
        senderName,
        roomId,
        recipientId,
        recipientName,
        isPrivate: !!recipientId,
      });

      res.status(201).json(result);
    } catch (error) {
      handleServiceError(error, res, authReq.correlationId);
    }
  }
);

/**
 * GET /files/download/:fileId
 *
 * Stream file download. Accepts JWT via Authorization header or ?token= query.
 */
fileRouter.get(
  "/download/:fileId",
  authMiddleware as never,
  async (req: Request, res: Response): Promise<void> => {
    const authReq = req as AuthenticatedRequest;
    try {
      const fileId = parseInt(req.params.fileId as string, 10);
      if (isNaN(fileId)) {
        res.status(400).json({ error: "fileId must be a number" });
        return;
      }

      const record = await getFile(fileId);

      // Authorization: private files are only accessible to sender and recipient
      if (record.isPrivate) {
        const currentUserId: number = authReq.user.userId;
        if (record.senderId !== currentUserId && record.recipientId !== currentUserId) {
          res.status(403).json({ error: "Forbidden" });
          return;
        }
      }

      // Stream the file back to the client
      // SECURITY: Use RFC 5987 filename* for safe encoding of the original name,
      // and strip any characters that could break the header value from the ASCII fallback.
      const safeName = record.originalName.replace(/["\\\r\n]/g, "");
      res.setHeader(
        "Content-Disposition",
        `attachment; filename="${safeName}"; filename*=UTF-8''${encodeURIComponent(record.originalName)}`
      );
      res.setHeader("Content-Type", "application/octet-stream");
      res.setHeader("Content-Length", record.fileSize);

      // SECURITY: Defense-in-depth headers to prevent XSS if files are ever
      // served inline or opened in the browser context
      res.setHeader("X-Content-Type-Options", "nosniff");
      res.setHeader("Content-Security-Policy", "default-src 'none'");
      res.setHeader("X-Frame-Options", "DENY");

      const fileStream = fs.createReadStream(record.storedPath);
      fileStream.pipe(res);

      fileStream.on("error", (err) => {
        logger.error("Error streaming file", {
          fileId,
          error: err.message,
          correlationId: authReq.correlationId,
        });
        // Only send error if headers haven't been sent yet
        if (!res.headersSent) {
          res.status(500).json({ error: "Error reading file" });
        }
      });
    } catch (error) {
      handleServiceError(error, res, authReq.correlationId);
    }
  }
);

/**
 * GET /files/room/:roomId
 *
 * List all files uploaded to a room. Returns metadata only (no file content).
 */
fileRouter.get(
  "/room/:roomId",
  authMiddleware as never,
  async (req: Request, res: Response): Promise<void> => {
    const authReq = req as AuthenticatedRequest;
    try {
      const roomId = parseInt(req.params.roomId as string, 10);
      if (isNaN(roomId)) {
        res.status(400).json({ error: "roomId must be a number" });
        return;
      }

      const files = await listRoomFiles(roomId);
      res.status(200).json(files);
    } catch (error) {
      handleServiceError(error, res, authReq.correlationId);
    }
  }
);

/**
 * Map service-layer errors to HTTP responses.
 * FileValidationError carries a status code; everything else is a 500.
 */
function handleServiceError(
  error: unknown,
  res: Response,
  correlationId?: string
): void {
  if (error instanceof FileValidationError) {
    res.status(error.statusCode).json({ error: error.message });
    return;
  }

  logger.error("Unhandled error in file route", {
    error: error instanceof Error ? error.message : String(error),
    stack: error instanceof Error ? error.stack : undefined,
    correlationId,
  });
  res.status(500).json({ error: "Internal server error" });
}
