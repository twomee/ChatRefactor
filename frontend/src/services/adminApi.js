// src/services/adminApi.js — Admin API calls
import http from '../api/http';

export function getRooms() {
  return http.get('/admin/rooms');
}

export function getUsers() {
  return http.get('/admin/users');
}

export function closeAllRooms() {
  return http.post('/admin/chat/close');
}

export function openAllRooms() {
  return http.post('/admin/chat/open');
}

export function closeRoom(roomId) {
  return http.post(`/admin/rooms/${roomId}/close`);
}

export function openRoom(roomId) {
  return http.post(`/admin/rooms/${roomId}/open`);
}

export function resetDatabase() {
  return http.delete('/admin/db');
}

export function promoteUser(username) {
  return http.post(`/admin/promote?username=${encodeURIComponent(username)}`);
}
