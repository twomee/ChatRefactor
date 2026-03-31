// types/kafka.types.ts — Kafka event type definitions
// Matches services/contracts/events/file.uploaded.schema.json

/** file.uploaded event produced to file.events topic */
export interface FileUploadedEvent {
  file_id: number;
  filename: string;
  size: number;
  from: string; // username of uploader
  sender_id: number; // user ID of uploader — needed so chat-service can notify the sender via SendPersonal
  room_id: number | null;
  to?: string; // recipient username for PM uploads
  recipient_id?: number | null;
  is_private: boolean;
  timestamp: string; // ISO 8601 UTC
}
