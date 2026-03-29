-- 002_create_read_positions.up.sql
-- Creates the read_positions table for tracking each user's last-read message
-- per room. Used by the "New messages" divider on the frontend.
-- Database: chatbox_chat

CREATE TABLE IF NOT EXISTS read_positions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL,
    last_read_message_id VARCHAR(36),
    last_read_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, room_id)
);

CREATE INDEX IF NOT EXISTS ix_read_positions_user_room ON read_positions(user_id, room_id);
