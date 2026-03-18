// src/services/roomApi.js — Room API calls
import http from '../api/http';

export function listRooms(etag) {
  const headers = etag ? { 'If-None-Match': etag } : {};
  return http.get('/rooms/', { headers, validateStatus: s => s < 500 });
}

export function createRoom(name) {
  return http.post('/rooms/', { name });
}

export function getRoomUsers(roomId, etag) {
  const headers = etag ? { 'If-None-Match': etag } : {};
  return http.get(`/rooms/${roomId}/users`, { headers, validateStatus: s => s < 500 });
}
