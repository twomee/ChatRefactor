-- CreateTable
CREATE TABLE IF NOT EXISTS "files" (
    "id" SERIAL NOT NULL,
    "original_name" VARCHAR(256) NOT NULL,
    "stored_path" VARCHAR(512) NOT NULL,
    "file_size" INTEGER NOT NULL,
    "sender_id" INTEGER NOT NULL,
    "room_id" INTEGER NOT NULL,
    "uploaded_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "files_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX IF NOT EXISTS "files_room_id_idx" ON "files"("room_id");
