// kafka/events.ts — Event type definitions and helpers for file events
// Matches contracts/events/file.uploaded.schema.json

import type { FileUploadedEvent } from "../types/kafka.types.js";
import { produce } from "./producer.js";
import { logger } from "./logger.js";

const FILE_EVENTS_TOPIC = "file.events";

/**
 * Produce a file.uploaded event to the file.events Kafka topic.
 *
 * Key is room_id (as string) so all events for the same room go to the same
 * partition — this preserves ordering per-room for consumers.
 */
export async function produceFileUploadedEvent(
  event: FileUploadedEvent
): Promise<boolean> {
  const key = String(event.room_id);

  const sent = await produce(FILE_EVENTS_TOPIC, key, event as unknown as Record<string, unknown>);

  if (sent) {
    logger.info("Produced file.uploaded event", {
      fileId: event.file_id,
      roomId: event.room_id,
      filename: event.filename,
    });
  } else {
    logger.warn("Failed to produce file.uploaded event — Kafka unavailable", {
      fileId: event.file_id,
      roomId: event.room_id,
    });
  }

  return sent;
}
