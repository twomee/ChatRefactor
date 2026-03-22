// src/services/roomApi.js — Room API calls
import http from './http';

export function listRooms() {
  return http.get('/rooms/', { validateStatus: s => s < 500 });
}

export function createRoom(name) {
  return http.post('/rooms/', { name });
}

/**
 * Fetch messages in a room since a given timestamp (ISO 8601).
 * Used after WebSocket reconnect to fill the gap of missed messages.
 */
export function getMessagesSince(roomId, sinceISO, limit = 200) {
  return http.get(`/rooms/${roomId}/messages`, {
    params: { since: sinceISO, limit },
  });
}
