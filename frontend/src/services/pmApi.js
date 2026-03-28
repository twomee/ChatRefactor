// src/services/pmApi.js — Private messaging API calls
import http from './http';

/**
 * Send a private message. Returns { detail, live_delivered }.
 * live_delivered = true means the recipient was online and received it via WebSocket.
 * live_delivered = false means it was persisted but the recipient is offline.
 */
export async function sendPM(to, text) {
  const res = await http.post('/pm/send', { to, text });
  return res.data;
}
