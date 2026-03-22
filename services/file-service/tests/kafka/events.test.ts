// tests/kafka/events.test.ts — Unit tests for Kafka event producers
//
// Tests produceFileUploadedEvent from src/kafka/events.ts.
// Requires the same KafkaJS mock as producer.test.ts because events.ts
// depends on the producer module.

import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";

// ── Hoisted Kafka mocks ──────────────────────────────────────────────────
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
    Kafka: vi.fn().mockImplementation(() => ({
      producer: vi.fn().mockReturnValue(mockProducer),
    })),
    logLevel: { WARN: 4 },
  };
});

describe("kafka/events", () => {
  let produceFileUploadedEvent: typeof import("../../src/kafka/events.js").produceFileUploadedEvent;
  let initProducer: typeof import("../../src/kafka/producer.js").initProducer;

  beforeAll(async () => {
    const events = await import("../../src/kafka/events.js");
    const producer = await import("../../src/kafka/producer.js");
    produceFileUploadedEvent = events.produceFileUploadedEvent;
    initProducer = producer.initProducer;
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should produce event successfully and return true", async () => {
    // Connect kafka first
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();
    mockProducerSend.mockResolvedValueOnce(undefined);

    const event = {
      file_id: 1,
      filename: "test.txt",
      size: 1024,
      from: "testuser",
      room_id: 5,
      timestamp: new Date().toISOString(),
    };

    const result = await produceFileUploadedEvent(event);
    expect(result).toBe(true);
  });

  it("should return false when kafka is unavailable", async () => {
    // Kafka not connected
    mockProducerConnect.mockRejectedValueOnce(new Error("Connection refused"));
    await initProducer();

    const event = {
      file_id: 2,
      filename: "report.pdf",
      size: 2048,
      from: "alice",
      room_id: 3,
      timestamp: new Date().toISOString(),
    };

    const result = await produceFileUploadedEvent(event);
    expect(result).toBe(false);
  });
});
