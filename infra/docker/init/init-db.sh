#!/bin/sh
# migrate-db.sh — One-time database migration for all microservices.
# Runs as the db-init container. Idempotent (CREATE IF NOT EXISTS).
# Expects PGUSER, PGHOST, PGPASSWORD env vars from docker-compose.
set -e

echo "=== Creating per-service databases ==="
for db in chatbox_auth chatbox_chat chatbox_messages chatbox_files; do
  echo "  Creating $db (if not exists)..."
  psql -d chatbox -tc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1 \
    || psql -d chatbox -c "CREATE DATABASE $db"
done

echo "=== Database migrations ==="

echo "  [auth] chatbox_auth..."
psql -d chatbox_auth <<'EOSQL'
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    email VARCHAR(256),
    is_global_admin BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    totp_secret VARCHAR(256),
    is_2fa_enabled BOOLEAN DEFAULT FALSE NOT NULL,
    backup_codes TEXT
);
-- Idempotent column addition for existing databases.
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(256);
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(256);
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_2fa_enabled BOOLEAN DEFAULT FALSE NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS backup_codes TEXT;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token VARCHAR(256) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
EOSQL

echo "  [chat] chatbox_chat..."
psql -d chatbox_chat <<'EOSQL'
CREATE TABLE IF NOT EXISTS rooms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE TABLE IF NOT EXISTS room_admins (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    appointed_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, room_id)
);
CREATE TABLE IF NOT EXISTS muted_users (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    muted_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, room_id)
);
CREATE INDEX IF NOT EXISTS idx_room_admins_room_id ON room_admins(room_id);
CREATE INDEX IF NOT EXISTS idx_muted_users_room_id ON muted_users(room_id);
INSERT INTO rooms (name) VALUES ('politics'), ('sports'), ('movies') ON CONFLICT (name) DO NOTHING;
EOSQL

echo "  [message] chatbox_messages..."
psql -d chatbox_messages <<'EOSQL'
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(36) UNIQUE,
    sender_id INTEGER NOT NULL,
    sender_name VARCHAR(64),
    room_id INTEGER,
    recipient_id INTEGER,
    content TEXT NOT NULL,
    is_private BOOLEAN DEFAULT FALSE NOT NULL,
    sent_at TIMESTAMP DEFAULT NOW() NOT NULL,
    edited_at TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    search_vector tsvector
);
-- Idempotent column addition for existing databases.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_name VARCHAR(64);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE NOT NULL;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS search_vector tsvector;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_file BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_messages_message_id ON messages(message_id);
CREATE INDEX IF NOT EXISTS idx_messages_room_sent ON messages(room_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_messages_search ON messages USING GIN(search_vector);

-- Full-text search trigger
CREATE OR REPLACE FUNCTION messages_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS tsvector_update ON messages;
CREATE TRIGGER tsvector_update BEFORE INSERT OR UPDATE ON messages
    FOR EACH ROW EXECUTE FUNCTION messages_search_trigger();

-- Reactions table
CREATE TABLE IF NOT EXISTS reactions (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(36) NOT NULL,
    user_id INTEGER NOT NULL,
    username VARCHAR(64) NOT NULL,
    emoji VARCHAR(32) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(message_id, user_id, emoji)
);
CREATE INDEX IF NOT EXISTS idx_reactions_message_id ON reactions(message_id);
EOSQL

echo "  [file] chatbox_files..."
psql -d chatbox_files <<'EOSQL'
CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    original_name VARCHAR(256) NOT NULL,
    stored_path VARCHAR(512) NOT NULL,
    file_size INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    sender_name VARCHAR(64),
    room_id INTEGER,
    uploaded_at TIMESTAMP DEFAULT NOW() NOT NULL
);
-- Idempotent column additions for existing databases.
ALTER TABLE files ADD COLUMN IF NOT EXISTS sender_name VARCHAR(64);
-- PM file support: room_id is nullable (PM uploads have no room), recipient_id
-- identifies the target user, is_private distinguishes PM files from room files.
ALTER TABLE files ALTER COLUMN room_id DROP NOT NULL;
ALTER TABLE files ADD COLUMN IF NOT EXISTS recipient_id INTEGER;
ALTER TABLE files ADD COLUMN IF NOT EXISTS is_private BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_files_room_id ON files(room_id);
CREATE INDEX IF NOT EXISTS files_recipient_id_idx ON files(recipient_id);
EOSQL

echo "=== All database migrations complete ==="
