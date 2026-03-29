// src/services/searchApi.js — Message search API
import http from './http';

/**
 * Full-text search across messages.
 *
 * @param {string} query   - Search terms (1-200 chars)
 * @param {number|null} roomId - Optional room filter
 * @param {number} limit   - Max results (1-100, default 50)
 * @returns {Promise<Array<{message_id, sender_name, content, room_id, sent_at}>>}
 */
export function searchMessages(query, roomId = null, limit = 50) {
  const params = { q: query, limit };
  if (roomId) params.room_id = roomId;
  return http.get('/messages/search', { params });
}
