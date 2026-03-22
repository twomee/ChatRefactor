-- 001_create_rooms.down.sql
-- Drops the chat-service tables in reverse dependency order.

DROP TABLE IF EXISTS muted_users;
DROP TABLE IF EXISTS room_admins;
DROP TABLE IF EXISTS rooms;
