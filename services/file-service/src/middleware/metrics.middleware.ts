// middleware/metrics.middleware.ts — Prometheus metrics instrumentation
//
// Exposes HTTP RED metrics (Rate, Errors, Duration), in-flight gauge,
// business metrics (uploads, downloads, file sizes), and Kafka produce metrics.
// Also collects Node.js default metrics (event loop lag, GC, memory, handles).
//
// The /metrics, /health, and /ready endpoints are excluded from HTTP tracking
// to avoid polluting dashboards with infrastructure noise.

import { Request, Response, NextFunction } from "express";
import {
  Registry,
  Counter,
  Histogram,
  Gauge,
  collectDefaultMetrics,
} from "prom-client";

export const register = new Registry();

// Collect Node.js default metrics: event loop lag, GC, memory, active handles
collectDefaultMetrics({ register });

// ── HTTP RED metrics ─────────────────────────────────────────────────────────

export const httpRequestsTotal = new Counter({
  name: "http_requests_total",
  help: "Total HTTP requests",
  labelNames: ["method", "route", "status_code"] as const,
  registers: [register],
});

export const httpRequestDuration = new Histogram({
  name: "http_request_duration_seconds",
  help: "HTTP request duration in seconds",
  labelNames: ["method", "route"] as const,
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
  registers: [register],
});

export const httpRequestsInFlight = new Gauge({
  name: "http_requests_in_flight",
  help: "HTTP requests currently being processed",
  registers: [register],
});

// ── Business metrics ─────────────────────────────────────────────────────────

export const filesUploadedTotal = new Counter({
  name: "files_uploaded_total",
  help: "Total files uploaded",
  labelNames: ["status"] as const,
  registers: [register],
});

export const fileUploadSizeBytes = new Histogram({
  name: "file_upload_size_bytes",
  help: "Size of uploaded files in bytes",
  buckets: [1024, 10240, 102400, 1048576, 10485760, 52428800, 157286400],
  registers: [register],
});

export const filesDownloadedTotal = new Counter({
  name: "files_downloaded_total",
  help: "Total file downloads",
  labelNames: ["status"] as const,
  registers: [register],
});

// ── Kafka metrics ────────────────────────────────────────────────────────────

export const kafkaProduceTotal = new Counter({
  name: "kafka_produce_total",
  help: "Total Kafka messages produced",
  labelNames: ["topic", "status"] as const,
  registers: [register],
});

// ── Express middleware ───────────────────────────────────────────────────────

export function metricsMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Skip metrics and health endpoints to avoid polluting dashboards
  if (
    req.path === "/metrics" ||
    req.path === "/health" ||
    req.path === "/ready"
  ) {
    next();
    return;
  }

  httpRequestsInFlight.inc();
  const end = httpRequestDuration.startTimer();

  res.on("finish", () => {
    httpRequestsInFlight.dec();
    const route = req.route?.path || req.path;
    end({ method: req.method, route });
    httpRequestsTotal.inc({
      method: req.method,
      route,
      status_code: String(res.statusCode),
    });
  });

  next();
}
