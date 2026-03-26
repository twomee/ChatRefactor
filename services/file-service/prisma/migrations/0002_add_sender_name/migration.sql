-- Migration: 0002_add_sender_name
-- Add sender_name column to files table.
-- The Prisma schema defines senderName as String? (optional VARCHAR 64)
-- for denormalized display of the uploader's username in file listings
-- without requiring cross-service auth lookups.

ALTER TABLE "files" ADD COLUMN IF NOT EXISTS "sender_name" VARCHAR(64);
