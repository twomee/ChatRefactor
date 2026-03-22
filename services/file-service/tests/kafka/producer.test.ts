// tests/kafka/producer.test.ts — Unit tests for Kafka producer
//
// Tests initProducer, produce, shutdownProducer, and isKafkaAvailable
// from src/kafka/producer.ts with a mocked KafkaJS client.

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

describe("kafka/producer", () => {
  let initProducer: typeof import("../../src/kafka/producer.js").initProducer;
  let produce: typeof import("../../src/kafka/producer.js").produce;
  let shutdownProducer: typeof import("../../src/kafka/producer.js").shutdownProducer;
  let isKafkaAvailable: typeof import("../../src/kafka/producer.js").isKafkaAvailable;

  beforeAll(async () => {
    const mod = await import("../../src/kafka/producer.js");
    initProducer = mod.initProducer;
    produce = mod.produce;
    shutdownProducer = mod.shutdownProducer;
    isKafkaAvailable = mod.isKafkaAvailable;
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should connect successfully and mark kafka as available", async () => {
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();
    expect(isKafkaAvailable()).toBe(true);
  });

  it("should handle connection failure gracefully", async () => {
    mockProducerConnect.mockRejectedValueOnce(new Error("Connection refused"));
    await initProducer();
    expect(isKafkaAvailable()).toBe(false);
  });

  it("should produce a message successfully when connected", async () => {
    // First ensure kafka is connected
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();

    mockProducerSend.mockResolvedValueOnce(undefined);
    const result = await produce("test-topic", "key1", { data: "value" });
    expect(result).toBe(true);
    expect(mockProducerSend).toHaveBeenCalledWith({
      topic: "test-topic",
      messages: [{ key: "key1", value: JSON.stringify({ data: "value" }) }],
    });
  });

  it("should return false when produce fails", async () => {
    // First ensure kafka is connected
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();

    mockProducerSend.mockRejectedValueOnce(new Error("Broker not available"));
    const result = await produce("test-topic", "key1", { data: "value" });
    expect(result).toBe(false);
  });

  it("should return false when kafka is not available", async () => {
    // Simulate failed connection
    mockProducerConnect.mockRejectedValueOnce(new Error("Connection refused"));
    await initProducer();

    const result = await produce("test-topic", "key1", { data: "value" });
    expect(result).toBe(false);
  });

  it("should disconnect gracefully during shutdown", async () => {
    // First connect
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();
    expect(isKafkaAvailable()).toBe(true);

    // Then shutdown
    mockProducerDisconnect.mockResolvedValueOnce(undefined);
    await shutdownProducer();
    expect(isKafkaAvailable()).toBe(false);
  });

  it("should handle disconnect error gracefully during shutdown", async () => {
    // First connect
    mockProducerConnect.mockResolvedValueOnce(undefined);
    await initProducer();

    // Disconnect throws
    mockProducerDisconnect.mockRejectedValueOnce(new Error("Disconnect error"));
    await shutdownProducer();
    // Should not throw, just log warning
    expect(isKafkaAvailable()).toBe(false);
  });

  it("should handle shutdown when producer is null (never connected)", async () => {
    // Simulate failed connection so producer stays null
    mockProducerConnect.mockRejectedValueOnce(new Error("Connection refused"));
    await initProducer();

    // Shutdown should not throw even with null producer
    await shutdownProducer();
    expect(isKafkaAvailable()).toBe(false);
  });
});
