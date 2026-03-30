// types/file.types.ts — TypeScript interfaces for file domain

import type { Request } from "express";

/** JWT payload decoded from the token */
export interface JwtPayload {
  sub: string; // user_id as string
  username: string;
  exp: number;
  iat?: number;
}

/** User info attached to the request after JWT auth */
export interface AuthUser {
  userId: number;
  username: string;
}

/** Express Request with authenticated user attached by auth middleware */
export interface AuthenticatedRequest extends Request {
  user: AuthUser;
  correlationId: string;
}

/** Result returned after a successful file upload */
export interface FileUploadResult {
  id: number;
  originalName: string;
  fileSize: number;
  senderId: number;
  roomId: number | null;
  recipientId?: number | null;
  isPrivate?: boolean;
  uploadedAt: Date;
}

/** File record as returned by list/get endpoints */
export interface FileRecord {
  id: number;
  originalName: string;
  storedPath: string;
  fileSize: number;
  senderId: number;
  roomId: number;
  uploadedAt: Date;
}

/** Response shape for file metadata sent to clients */
export interface FileMetadataResponse {
  id: number;
  originalName: string;
  fileSize: number;
  senderId: number;
  roomId: number;
  uploadedAt: string; // ISO 8601
}
