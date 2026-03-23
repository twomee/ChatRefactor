// middleware/health.middleware.ts — Kubernetes health check endpoints
//
// GET /health  — Liveness probe: is the process running?
// GET /ready   — Readiness probe: can the service handle traffic?
//                Checks DB connection and Kafka availability.
//
// These are registered before auth middleware so they don't require JWT.

import type { Request, Response } from "express";
import { PrismaClient } from "@prisma/client";
import { isKafkaAvailable } from "../kafka/producer.js";

const prisma = new PrismaClient();

/**
 * Liveness probe — if this responds, the process is alive.
 * Kubernetes restarts the pod if this stops responding.
 */
export function livenessHandler(_req: Request, res: Response): void {
  res.status(200).json({ status: "ok" });
}

/**
 * Readiness probe — can the service handle traffic?
 * Checks that the database is reachable and reports Kafka status.
 *
 * If the DB is down, return 503 so Kubernetes stops routing traffic here.
 * Kafka being down is a warning, not a failure — uploads still work,
 * just real-time events won't fire.
 */
export async function readinessHandler(
  _req: Request,
  res: Response
): Promise<void> {
  const checks: Record<string, string> = {};

  // Check database connectivity
  try {
    await prisma.$queryRaw`SELECT 1`;
    checks.database = "ok";
  } catch {
    checks.database = "unavailable";
    res.status(503).json({ status: "not ready", checks });
    return;
  }

  // Check Kafka connectivity (non-blocking — Kafka down doesn't fail readiness)
  checks.kafka = isKafkaAvailable() ? "ok" : "unavailable";

  res.status(200).json({ status: "ok", checks });
}
