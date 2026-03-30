-- Migration: 0003_add_pm_file_support
-- Extend files table to support private-message (PM) file uploads.
--
-- Changes:
--   1. room_id becomes optional (NULL allowed) — PM uploads have no room context.
--   2. recipient_id added — stores the target user ID for PM file transfers.
--   3. is_private added — flag to distinguish PM files from room files, enabling
--      per-row access-control checks without a JOIN.

-- Make room_id optional (drop NOT NULL constraint)
ALTER TABLE "files" ALTER COLUMN "room_id" DROP NOT NULL;

-- Add recipient_id (nullable — only set for PM files)
ALTER TABLE "files" ADD COLUMN IF NOT EXISTS "recipient_id" INTEGER;

-- Add is_private flag (defaults to false for existing rows, i.e. room files)
ALTER TABLE "files" ADD COLUMN IF NOT EXISTS "is_private" BOOLEAN NOT NULL DEFAULT false;

-- Index recipient_id for efficient lookups of PM files sent to a specific user
CREATE INDEX IF NOT EXISTS "files_recipient_id_idx" ON "files"("recipient_id");
