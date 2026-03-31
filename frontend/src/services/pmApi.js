// src/services/pmApi.js — Private messaging API calls
import http from './http';

export function sendPM(to, text) {
  return http.post('/pm/send', { to, text });
}

export function editPM(msgId, text) {
  return http.patch(`/pm/edit/${msgId}`, { text });
}

export function deletePM(msgId) {
  return http.delete(`/pm/delete/${msgId}`);
}

export function addPMReaction(msgId, emoji) {
  return http.post(`/pm/reaction/${msgId}`, { emoji });
}

export function removePMReaction(msgId, emoji) {
  return http.delete(`/pm/reaction/${msgId}/${encodeURIComponent(emoji)}`);
}

/**
 * Fetch PM history with a specific user from the backend.
 * Loaded lazily — only called when a conversation is opened and not yet in state.
 * @param {string} username - The other participant's username
 * @param {{ limit?: number, before?: string }} options
 */
export function getPMHistory(username, { limit = 50, before } = {}) {
  return http.get(`/messages/pm/history/${encodeURIComponent(username)}`, {
    params: { limit, ...(before && { before }) },
  });
}
