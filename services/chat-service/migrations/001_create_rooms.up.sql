-- 001_create_rooms.up.sql
-- Creates the core tables for the chat-service: rooms, room_admins, muted_users.
-- Database: chatbox_chat

CREATE TABLE IF NOT EXISTS rooms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS room_admins (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    appointed_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE (user_id, room_id)
);

CREATE TABLE IF NOT EXISTS muted_users (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    muted_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE (user_id, room_id)
);

-- Indexes for common query patterns.
CREATE INDEX IF NOT EXISTS idx_room_admins_room_id ON room_admins(room_id);
CREATE INDEX IF NOT EXISTS idx_room_admins_user_id ON room_admins(user_id);
CREATE INDEX IF NOT EXISTS idx_muted_users_room_id ON muted_users(room_id);
CREATE INDEX IF NOT EXISTS idx_muted_users_user_id ON muted_users(user_id);
