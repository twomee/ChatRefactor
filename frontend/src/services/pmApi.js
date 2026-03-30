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
