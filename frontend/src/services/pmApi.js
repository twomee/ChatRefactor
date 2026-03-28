// src/services/pmApi.js — Private messaging API calls
import http from './http';

export function sendPM(to, text) {
  return http.post('/pm/send', { to, text });
}
