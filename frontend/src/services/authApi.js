// src/services/authApi.js — Auth API calls
import http from './http';

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

// ── Two-Factor Authentication ───────────────────────────────────────────

export function setup2FA() {
  return http.post('/auth/2fa/setup');
}

export function verifySetup2FA(code) {
  return http.post('/auth/2fa/verify-setup', { code });
}

export function disable2FA(code) {
  return http.post('/auth/2fa/disable', { code });
}

export function verifyLogin2FA(tempToken, code) {
  return http.post('/auth/2fa/verify-login', { temp_token: tempToken, code });
}

export function get2FAStatus() {
  return http.get('/auth/2fa/status');
}
