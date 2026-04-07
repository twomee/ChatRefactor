// tests/middleware/metrics.middleware.test.ts — Integration tests for Prometheus metrics middleware
//
// Tests GET /metrics endpoint, metric skip logic for infrastructure paths,
// metric tracking for application routes, and exported metric definitions.

import { describe, it, expect, vi, beforeEach } from "vitest";
import request from "supertest";

// ── Hoisted mocks (must be declared with vi.hoisted before vi.mock) ────────
const { mockPrismaFile, mockQueryRaw } = vi.hoisted(() => ({
  mockPrismaFile: {
    create: vi.fn(),
    findUnique: vi.fn(),
    findMany: vi.fn(),
  },
  mockQueryRaw: vi.fn().mockResolvedValue([{ "?column?": 1 }]),
}));

const { mockExistsSync, mockCreateReadStream, mockWriteFileSync, mockMkdirSync } = vi.hoisted(() => ({
  mockExistsSync: vi.fn().mockReturnValue(true),
  mockCreateReadStream: vi.fn(),
  mockWriteFileSync: vi.fn(),
  mockMkdirSync: vi.fn(),
}));

// ── Mock Prisma ────────────────────────────────────────────────────────────
vi.mock("@prisma/client", () => {
  return {
    PrismaClient: vi.fn().mockImplementation(function () {
      return { file: mockPrismaFile, $queryRaw: mockQueryRaw };
    }),
  };
});

// ── Mock Kafka ─────────────────────────────────────────────────────────────
const mockProducerSend = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockProducerConnect = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockProducerDisconnect = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

vi.mock("kafkajs", () => {
  const mockProducer = {
    connect: mockProducerConnect,
    send: mockProducerSend,
    disconnect: mockProducerDisconnect,
  };
  return {
    Kafka: vi.fn().mockImplementation(function () {
      return { producer: vi.fn().mockReturnValue(mockProducer) };
    }),
    logLevel: { WARN: 4 },
  };
});

// ── Mock fs to avoid actual disk writes in tests ───────────────────────────
vi.mock("node:fs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs")>();
  const { Readable: ReadableStream } = await import("node:stream");

  const makeFakeStream = () =>
    new ReadableStream({
      read() {
        this.push(Buffer.from("file content"));
        this.push(null);
      },
    });

  mockCreateReadStream.mockImplementation(() => makeFakeStream());

  return {
    ...actual,
    default: {
      ...actual,
      writeFileSync: mockWriteFileSync,
      mkdirSync: mockMkdirSync,
      existsSync: mockExistsSync,
      createReadStream: mockCreateReadStream,
    },
    writeFileSync: mockWriteFileSync,
    mkdirSync: mockMkdirSync,
    existsSync: mockExistsSync,
    createReadStream: mockCreateReadStream,
  };
});

// Now import the app and metrics after mocks are in place
import { app } from "../../src/index.js";
import {
  register,
  httpRequestsTotal,
  httpRequestDuration,
  httpRequestsInFlight,
  filesUploadedTotal,
  fileUploadSizeBytes,
  filesDownloadedTotal,
  kafkaProduceTotal,
  metricsMiddleware,
} from "../../src/middleware/metrics.middleware.js";

// ── Tests ──────────────────────────────────────────────────────────────────

describe("middleware/metrics.middleware", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── GET /metrics endpoint ──────────────────────────────────────────────

  describe("GET /metrics", () => {
    it("should return 200 with Prometheus content type", async () => {
      const res = await request(app).get("/metrics");

      expect(res.status).toBe(200);
      // prom-client sets content type to openmetrics or text/plain with version param
      expect(res.headers["content-type"]).toMatch(
        /^(text\/plain|application\/openmetrics-text)/
      );
    });

    it("should contain http_requests_total metric", async () => {
      const res = await request(app).get("/metrics");

      expect(res.text).toContain("http_requests_total");
    });

    it("should contain http_request_duration_seconds metric", async () => {
      const res = await request(app).get("/metrics");

      expect(res.text).toContain("http_request_duration_seconds");
    });

    it("should contain http_requests_in_flight metric", async () => {
      const res = await request(app).get("/metrics");

      expect(res.text).toContain("http_requests_in_flight");
    });

    it("should contain files_uploaded_total metric", async () => {
      const res = await request(app).get("/metrics");

      expect(res.text).toContain("files_uploaded_total");
    });

    it("should contain file_upload_size_bytes metric", async () => {
      const res = await request(app).get("/metrics");

      expect(res.text).toContain("file_upload_size_bytes");
    });

    it("should contain files_downloaded_total metric", async () => {
      const res = await request(app).get("/metrics");

      expect(res.text).toContain("files_downloaded_total");
    });

    it("should contain kafka_produce_total metric", async () => {
      const res = await request(app).get("/metrics");

      expect(res.text).toContain("kafka_produce_total");
    });

    it("should contain Node.js default metrics", async () => {
      const res = await request(app).get("/metrics");

      // collectDefaultMetrics registers process_cpu_seconds_total among others
      expect(res.text).toContain("process_cpu_seconds_total");
    });
  });

  // ── Skipped endpoints ─────────────────────────────────────────────────

  describe("skip logic for infrastructure endpoints", () => {
    it("should not track /health requests in http_requests_total", async () => {
      // Reset the counter so we start clean
      httpRequestsTotal.reset();

      // Hit /health several times
      await request(app).get("/health");
      await request(app).get("/health");

      // Fetch the metrics output
      const res = await request(app).get("/metrics");

      // There should be no http_requests_total line with route="/health"
      const lines = res.text.split("\n");
      const healthMetricLines = lines.filter(
        (line: string) =>
          line.startsWith("http_requests_total") && line.includes("/health")
      );
      expect(healthMetricLines).toHaveLength(0);
    });

    it("should not track /ready requests in http_requests_total", async () => {
      httpRequestsTotal.reset();

      await request(app).get("/ready");

      const res = await request(app).get("/metrics");
      const lines = res.text.split("\n");
      const readyMetricLines = lines.filter(
        (line: string) =>
          line.startsWith("http_requests_total") && line.includes("/ready")
      );
      expect(readyMetricLines).toHaveLength(0);
    });

    it("should not track /metrics requests in http_requests_total", async () => {
      httpRequestsTotal.reset();

      // Hit /metrics itself (the endpoint we use to scrape)
      await request(app).get("/metrics");
      await request(app).get("/metrics");

      const res = await request(app).get("/metrics");
      const lines = res.text.split("\n");
      const metricsMetricLines = lines.filter(
        (line: string) =>
          line.startsWith("http_requests_total") &&
          line.includes('route="/metrics"')
      );
      expect(metricsMetricLines).toHaveLength(0);
    });
  });

  // ── Tracking for application routes ───────────────────────────────────

  describe("tracking for application routes", () => {
    it("should track requests to non-skipped routes", async () => {
      httpRequestsTotal.reset();
      httpRequestDuration.reset();

      // Hit a route that is not /health, /ready, or /metrics
      // This will return 401 (no auth) but the middleware still tracks it
      await request(app).get("/files/room/1");

      const res = await request(app).get("/metrics");

      // Should see an http_requests_total entry for /files/room/1 or the route pattern
      expect(res.text).toMatch(/http_requests_total\{.*method="GET".*\}/);
    });

    it("should record request duration for tracked routes", async () => {
      httpRequestDuration.reset();

      await request(app).get("/files/room/1");

      const res = await request(app).get("/metrics");

      // Duration histogram should have bucket entries with method="GET"
      expect(res.text).toMatch(
        /http_request_duration_seconds_bucket\{.*method="GET".*\}/
      );
    });

    it("should include status_code label in http_requests_total", async () => {
      httpRequestsTotal.reset();

      // 401 because no auth
      await request(app).get("/files/room/1");

      const res = await request(app).get("/metrics");

      expect(res.text).toMatch(
        /http_requests_total\{.*status_code="401".*\}/
      );
    });
  });

  // ── Exported metric objects ───────────────────────────────────────────

  describe("exported metric definitions", () => {
    it("should export register as a Registry instance", () => {
      expect(register).toBeDefined();
      expect(typeof register.metrics).toBe("function");
      expect(typeof register.contentType).toBe("string");
    });

    it("should export httpRequestsTotal as a Counter", () => {
      expect(httpRequestsTotal).toBeDefined();
      expect(typeof httpRequestsTotal.inc).toBe("function");
      expect(typeof httpRequestsTotal.reset).toBe("function");
    });

    it("should export httpRequestDuration as a Histogram", () => {
      expect(httpRequestDuration).toBeDefined();
      expect(typeof httpRequestDuration.observe).toBe("function");
      expect(typeof httpRequestDuration.startTimer).toBe("function");
    });

    it("should export httpRequestsInFlight as a Gauge", () => {
      expect(httpRequestsInFlight).toBeDefined();
      expect(typeof httpRequestsInFlight.inc).toBe("function");
      expect(typeof httpRequestsInFlight.dec).toBe("function");
      expect(typeof httpRequestsInFlight.set).toBe("function");
    });

    it("should export filesUploadedTotal as a Counter", () => {
      expect(filesUploadedTotal).toBeDefined();
      expect(typeof filesUploadedTotal.inc).toBe("function");
    });

    it("should export fileUploadSizeBytes as a Histogram", () => {
      expect(fileUploadSizeBytes).toBeDefined();
      expect(typeof fileUploadSizeBytes.observe).toBe("function");
    });

    it("should export filesDownloadedTotal as a Counter", () => {
      expect(filesDownloadedTotal).toBeDefined();
      expect(typeof filesDownloadedTotal.inc).toBe("function");
    });

    it("should export kafkaProduceTotal as a Counter", () => {
      expect(kafkaProduceTotal).toBeDefined();
      expect(typeof kafkaProduceTotal.inc).toBe("function");
    });

    it("should export metricsMiddleware as a function", () => {
      expect(metricsMiddleware).toBeDefined();
      expect(typeof metricsMiddleware).toBe("function");
      // Express middleware signature: (req, res, next) => void
      expect(metricsMiddleware.length).toBe(3);
    });
  });
});
