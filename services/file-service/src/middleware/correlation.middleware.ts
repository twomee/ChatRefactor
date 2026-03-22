// middleware/correlation.middleware.ts — Request correlation ID tracking
//
// Reads X-Request-ID from the incoming request (set by Kong or upstream),
// or generates a new UUID if not present. Attaches it to the request object,
// sets it on the response header, and makes it available for structured logging.

import type { Request, Response, NextFunction } from "express";
import { v4 as uuidv4 } from "uuid";
import type { AuthenticatedRequest } from "../types/file.types.js";

/**
 * Correlation ID middleware — ensures every request has a traceable ID
 * that flows through logs, Kafka events, and downstream service calls.
 */
export function correlationMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const correlationId =
    (req.headers["x-request-id"] as string) || uuidv4();

  // Attach to request for downstream use
  (req as AuthenticatedRequest).correlationId = correlationId;

  // Echo back in response headers for client-side debugging
  res.setHeader("X-Request-ID", correlationId);

  next();
}
