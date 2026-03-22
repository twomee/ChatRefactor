// middleware/auth.middleware.ts — JWT authentication middleware
//
// Validates JWT locally using the same SECRET_KEY and HS256 algorithm as the
// Auth Service. No Redis blacklist check — microservice boundary means we trust
// Kong gateway for rate limiting and the Auth Service for token issuance.
// Token format: { sub: "user_id", username: "alice", exp: ... }

import type { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";
import { config } from "../config/env.config.js";
import type { AuthenticatedRequest, JwtPayload } from "../types/file.types.js";
import { logger } from "../kafka/logger.js";

/**
 * Express middleware that:
 * 1. Extracts JWT from Authorization: Bearer header OR ?token= query param
 * 2. Verifies with HS256 + shared SECRET_KEY
 * 3. Attaches { userId, username } to req.user
 * 4. Returns 401 if missing or invalid
 *
 * The ?token= query param is needed for file downloads where the browser
 * navigates via <a href> — no way to set Authorization header in a link.
 */
export function authMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const authReq = req as AuthenticatedRequest;
  let token: string | undefined;

  // Try Authorization header first
  const authHeader = req.headers.authorization;
  if (authHeader && authHeader.toLowerCase().startsWith("bearer ")) {
    token = authHeader.slice(7);
  }

  // Fall back to ?token= query param (used by download endpoint)
  if (!token && typeof req.query.token === "string") {
    token = req.query.token;
  }

  if (!token) {
    res.status(401).json({ error: "Authentication required" });
    return;
  }

  try {
    const decoded = jwt.verify(token, config.secretKey, {
      algorithms: [config.algorithm],
    }) as JwtPayload;

    if (!decoded.sub || !decoded.username) {
      res.status(401).json({ error: "Invalid token payload" });
      return;
    }

    authReq.user = {
      userId: parseInt(decoded.sub, 10),
      username: decoded.username,
    };

    next();
  } catch (error) {
    logger.debug("JWT verification failed", {
      error: error instanceof Error ? error.message : String(error),
      correlationId: authReq.correlationId,
    });
    res.status(401).json({ error: "Invalid or expired token" });
    return;
  }
}
