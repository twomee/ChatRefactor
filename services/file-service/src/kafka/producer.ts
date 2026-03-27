// kafka/producer.ts — KafkaJS producer with graceful degradation
//
// Design decision: if Kafka is unavailable, the upload still succeeds (file is
// stored + metadata in DB), but the real-time broadcast to the chat room won't
// happen. The log warning gives ops visibility. This matches the monolith
// pattern where Kafka failure doesn't block the primary write path.

import { Kafka, Producer, logLevel } from "kafkajs";
import { config } from "../config/env.config.js";
import { logger } from "./logger.js";
import { kafkaProduceTotal } from "../middleware/metrics.middleware.js";

let producer: Producer | null = null;
let kafkaAvailable = false;

/**
 * Initialize and connect the Kafka producer.
 * Called once at application startup.
 */
export async function initProducer(): Promise<void> {
  try {
    const kafka = new Kafka({
      clientId: "file-service",
      brokers: config.kafkaBootstrapServers.split(","),
      logLevel: logLevel.WARN,
      retry: {
        initialRetryTime: 300,
        retries: 5,
      },
    });

    producer = kafka.producer({
      allowAutoTopicCreation: true,
    });

    await producer.connect();
    kafkaAvailable = true;
    logger.info("Kafka producer connected");
  } catch (error) {
    kafkaAvailable = false;
    producer = null;
    logger.warn("Kafka producer failed to connect — file uploads will still work but real-time events won't fire", {
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

/**
 * Produce a message to a Kafka topic.
 * Returns true if sent successfully, false if Kafka is unavailable.
 */
export async function produce(
  topic: string,
  key: string,
  value: Record<string, unknown>
): Promise<boolean> {
  if (!kafkaAvailable || !producer) {
    logger.warn("Kafka unavailable — skipping event production", { topic, key });
    return false;
  }

  try {
    await producer.send({
      topic,
      messages: [
        {
          key,
          value: JSON.stringify(value),
        },
      ],
    });
    kafkaProduceTotal.inc({ topic, status: "success" });
    return true;
  } catch (error) {
    kafkaProduceTotal.inc({ topic, status: "failed" });
    logger.warn("Kafka produce failed", {
      topic,
      key,
      error: error instanceof Error ? error.message : String(error),
    });
    return false;
  }
}

/**
 * Gracefully disconnect the Kafka producer.
 * Called during application shutdown.
 */
export async function shutdownProducer(): Promise<void> {
  if (producer) {
    try {
      await producer.disconnect();
      logger.info("Kafka producer disconnected");
    } catch (error) {
      logger.warn("Error disconnecting Kafka producer", {
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
  producer = null;
  kafkaAvailable = false;
}

/**
 * Check if Kafka is available (used by readiness health check).
 */
export function isKafkaAvailable(): boolean {
  return kafkaAvailable;
}
