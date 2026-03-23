// types/kafka.types.ts — Kafka event type definitions
// Matches contracts/events/file.uploaded.schema.json

/** file.uploaded event produced to file.events topic */
export interface FileUploadedEvent {
  file_id: number;
  filename: string;
  size: number;
  from: string; // username of uploader
  room_id: number;
  timestamp: string; // ISO 8601 UTC
}
