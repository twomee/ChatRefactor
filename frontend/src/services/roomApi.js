// src/services/roomApi.js — Room API calls
import http from '../api/http';

export function listRooms() {
  return http.get('/rooms/', { validateStatus: s => s < 500 });
}

export function createRoom(name) {
  return http.post('/rooms/', { name });
}
