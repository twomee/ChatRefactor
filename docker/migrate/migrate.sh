#!/bin/bash
# migrate.sh — One-time database migration for all microservices.
# Runs as a Docker init container before services start.
# Idempotent: safe to re-run (CREATE IF NOT EXISTS, ON CONFLICT DO NOTHING).
set -e

echo "=== Running database migrations ==="

# Auth Service: chatbox_auth
echo "  [auth] Applying migrations..."
PGPASSWORD="$POSTGRES_PASSWORD" psql -h postgres -U chatbox chatbox_auth <<'EOSQL'
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    is_global_admin BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
EOSQL
echo "  [auth] Done."

# Chat Service: chatbox_chat
echo "  [chat] Applying migrations..."
PGPASSWORD="$POSTGRES_PASSWORD" psql -h postgres -U chatbox chatbox_chat <<'EOSQL'
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
echo "  [chat] Done."

# Message Service: chatbox_messages
echo "  [message] Applying migrations..."
PGPASSWORD="$POSTGRES_PASSWORD" psql -h postgres -U chatbox chatbox_messages <<'EOSQL'
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(36) UNIQUE,
    sender_id INTEGER NOT NULL,
    room_id INTEGER,
    recipient_id INTEGER,
    content TEXT NOT NULL,
    is_private BOOLEAN DEFAULT FALSE NOT NULL,
    sent_at TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_message_id ON messages(message_id);
CREATE INDEX IF NOT EXISTS idx_messages_room_sent ON messages(room_id, sent_at);
EOSQL
echo "  [message] Done."

# File Service: chatbox_files
echo "  [file] Applying migrations..."
PGPASSWORD="$POSTGRES_PASSWORD" psql -h postgres -U chatbox chatbox_files <<'EOSQL'
CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    original_name VARCHAR(256) NOT NULL,
    stored_path VARCHAR(512) NOT NULL,
    file_size INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL,
    uploaded_at TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_files_room_id ON files(room_id);
EOSQL
echo "  [file] Done."

# Create Kafka topics
echo "  [kafka] Creating topics..."
for topic in chat.messages:6 chat.private:3 chat.events:3 chat.dlq:1 file.events:3 auth.events:3; do
    name="${topic%%:*}"
    parts="${topic##*:}"
    /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 \
        --create --topic "$name" --partitions "$parts" --replication-factor 1 \
        --if-not-exists 2>/dev/null || true
done
echo "  [kafka] Done."

echo "=== All migrations complete ==="
