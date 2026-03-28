// index.ts — File Service entry point
//
// Express app setup: CORS, JSON parsing, multer (multipart), correlation ID
// middleware, health endpoints (unauthenticated), file routes (authenticated).
//
// Startup: connect Kafka producer, ensure upload directory exists.
// Shutdown: disconnect Kafka producer, close Prisma connection.

import express from "express";
import cors from "cors";
import multer from "multer";
import fs from "node:fs";

import { config } from "./config/env.config.js";
import { correlationMiddleware } from "./middleware/correlation.middleware.js";
import { metricsMiddleware, register } from "./middleware/metrics.middleware.js";
import {
  livenessHandler,
  readinessHandler,
} from "./middleware/health.middleware.js";
import { fileRouter } from "./routes/file.route.js";
import { initProducer, shutdownProducer } from "./kafka/producer.js";
import { logger } from "./kafka/logger.js";

// ── Express app setup ──────────────────────────────────────────────────────

export const app = express();

// CORS — allow all origins (Kong gateway handles CORS in production)
app.use(cors());

// SECURITY: Global security headers — defense-in-depth even behind Kong
app.use((_req, res, next) => {
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("X-Frame-Options", "DENY");
  next();
});

// Parse JSON bodies (for non-multipart requests)
app.use(express.json());

// Correlation ID middleware — must be before routes so every request gets an ID
app.use(correlationMiddleware);

// Prometheus metrics middleware — tracks HTTP RED metrics for all routes
app.use(metricsMiddleware);

// ── Health endpoints (no auth required) ────────────────────────────────────
// Registered before auth middleware so Kubernetes probes don't need tokens
app.get("/health", livenessHandler);
app.get("/ready", readinessHandler);

// ── Prometheus metrics endpoint ──────────────────────────────────────────
app.get("/metrics", async (_req, res) => {
  res.set("Content-Type", register.contentType);
  res.end(await register.metrics());
});

// ── Multer setup for file uploads ──────────────────────────────────────────
// memoryStorage: keeps file in buffer (not on disk) until service validates it.
// limit: 150MB max — matches monolith config. Multer rejects before our code runs.
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: config.maxFileSizeBytes,
  },
});

// Apply multer to the upload route before the router processes it
app.use("/files/upload", upload.single("file"));

// ── File routes (all require auth) ─────────────────────────────────────────
app.use("/files", fileRouter);

// ── Global error handler ──────────────────────────────────────────────────
// SECURITY: Catch-all error handler to prevent Express from leaking stack
// traces. Express's default error handler includes stack traces when
// NODE_ENV !== 'production', but we suppress them unconditionally.
app.use(
  (
    err: Error,
    _req: express.Request,
    res: express.Response,
    _next: express.NextFunction
  ) => {
    logger.error("Unhandled Express error", {
      error: err.message,
      stack: err.stack,
    });

    if (!res.headersSent) {
      res.status(500).json({ error: "Internal server error" });
    }
  }
);

// ── Startup & shutdown ─────────────────────────────────────────────────────

async function startServer(): Promise<void> {
  // Ensure upload directory exists
  fs.mkdirSync(config.uploadDir, { recursive: true });
  logger.info("Upload directory ready", { path: config.uploadDir });

  // Connect Kafka producer (graceful degradation — failure doesn't block start)
  await initProducer();

  const server = app.listen(config.port, () => {
    logger.info(`File Service listening on port ${config.port}`, {
      env: config.nodeEnv,
    });
  });

  // Graceful shutdown — wait for in-flight requests before exiting
  const shutdown = async (signal: string) => {
    logger.info(`Received ${signal} — shutting down gracefully`);
    await new Promise<void>((resolve) => server.close(() => {
      logger.info("HTTP server closed");
      resolve();
    }));
    await shutdownProducer();
    process.exit(0);
  };

  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

// Only start the server when this module is run directly (not imported by tests)
// tsx sets import.meta.url; when run via `node dist/index.js` it's the file URL
const isMainModule =
  process.argv[1] &&
  (process.argv[1].endsWith("index.ts") ||
    process.argv[1].endsWith("index.js"));

if (isMainModule) {
  startServer().catch((err) => {
    logger.error("Failed to start File Service", {
      error: err instanceof Error ? err.message : String(err),
    });
    process.exit(1);
  });
}
