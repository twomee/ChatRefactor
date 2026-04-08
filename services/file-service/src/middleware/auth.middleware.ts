// middleware/auth.middleware.ts — JWT authentication middleware
//
// Validates JWT locally using the same SECRET_KEY and HS256 algorithm as the
// Auth Service. Also checks the Redis token blacklist (if Redis is configured)
// so that tokens revoked by the auth-service on logout are rejected here too.
// Token format: { sub: "user_id", username: "alice", exp: ... }

import type { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";
import { config } from "../config/env.config.js";
import { getRedisClient } from "../clients/redis.client.js";
import type { AuthenticatedRequest, JwtPayload } from "../types/file.types.js";
import { logger } from "../kafka/logger.js";

/**
 * Express middleware that:
 * 1. Extracts JWT from Authorization: Bearer header OR ?token= query param
 * 2. Verifies with HS256 + shared SECRET_KEY
 * 3. Checks the Redis blacklist for revoked tokens (if Redis is configured)
 * 4. Attaches { userId, username } to req.user
 * 5. Returns 401 if missing, invalid, or revoked
 *
 * The ?token= query param is needed for file downloads where the browser
 * navigates via <a href> — no way to set Authorization header in a link.
 *
 * Redis unavailability behavior:
 *   - production  → fail closed (reject with 503)
 *   - development → fail open  (skip blacklist check, log a warning)
 */
export async function authMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
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

  let decoded: JwtPayload;
  try {
    decoded = jwt.verify(token, config.secretKey, {
      algorithms: [config.algorithm],
    }) as JwtPayload;

    if (!decoded.sub || !decoded.username) {
      res.status(401).json({ error: "Invalid token payload" });
      return;
    }

    const userId = parseInt(decoded.sub, 10);
    if (isNaN(userId)) {
      res.status(401).json({ error: "Invalid token payload" });
      return;
    }

    authReq.user = { userId, username: decoded.username };
  } catch (error) {
    logger.debug("JWT verification failed", {
      error: error instanceof Error ? error.message : String(error),
      correlationId: authReq.correlationId,
    });
    res.status(401).json({ error: "Invalid or expired token" });
    return;
  }

  // Check Redis blacklist for revoked tokens
  const rdb = getRedisClient();
  if (rdb) {
    try {
      const revoked = await rdb.get(`blacklist:${token}`);
      if (revoked !== null) {
        res.status(401).json({ error: "Token has been revoked" });
        return;
      }
    } catch (err) {
      logger.warn("Redis blacklist check failed", {
        error: err instanceof Error ? err.message : String(err),
        correlationId: authReq.correlationId,
      });
      if (config.nodeEnv === "production") {
        res.status(503).json({ error: "Authentication service unavailable" });
        return;
      }
      // dev/test: fail open — skip blacklist check
    }
  }

  next();
}
