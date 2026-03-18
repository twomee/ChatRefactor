// src/services/authApi.js — Auth API calls
import http from '../api/http';

export function register(username, password) {
  return http.post('/auth/register', { username, password });
}

export function login(username, password) {
  return http.post('/auth/login', { username, password });
}

export function logout() {
  return http.post('/auth/logout');
}

export function ping() {
  return http.post('/auth/ping');
}
