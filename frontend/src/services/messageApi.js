// src/services/messageApi.js — Message-service API calls
import http from './http';

/**
 * Fetch Open Graph link preview metadata for a URL.
 * Returns { url, title, description, image } on success.
 *
 * @param {string} url - The URL to preview
 * @returns {Promise<import('axios').AxiosResponse>}
 */
export function fetchLinkPreview(url) {
  return http.get('/messages/preview', { params: { url } });
}

/**
 * Fetch messages surrounding a specific message for scroll-to-message.
 * Returns a window of messages around the target (before + after).
 *
 * @param {string|number} roomId    - The room containing the message
 * @param {string}        messageId - The target message ID
 * @param {number}        before    - Number of messages before the target (default 25)
 * @param {number}        after     - Number of messages after the target (default 25)
 * @returns {Promise<import('axios').AxiosResponse>}
 */
export function getMessageContext(roomId, messageId, before = 25, after = 25) {
  return http.get(`/messages/rooms/${roomId}/context`, {
    params: { message_id: messageId, before, after },
  });
}

/**
 * Clear all messages for the current user in a room or PM thread.
 * @param {'room'|'pm'} contextType
 * @param {number} contextId - room_id or partner's user_id
 */
export function clearHistory(contextType, contextId) {
  return http.post('/messages/clear', { context_type: contextType, context_id: contextId });
}
