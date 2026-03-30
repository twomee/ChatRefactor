// src/services/authApi.js — Auth API calls
import http from './http';

export function register(username, password, email) {
  return http.post('/auth/register', { username, password, email });
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

// ── Profile Management ──────────────────────────────────────────────────

export async function getProfile() {
  const res = await http.get('/auth/profile');
  return res.data;
}

export async function updateEmail(newEmail, currentPassword) {
  const res = await http.patch('/auth/profile/email', { new_email: newEmail, current_password: currentPassword });
  return res.data;
}

export async function updatePassword(currentPassword, newPassword) {
  const res = await http.patch('/auth/profile/password', { current_password: currentPassword, new_password: newPassword });
  return res.data;
}

// ── Password Reset ──────────────────────────────────────────────────────

export async function forgotPassword(email) {
  const res = await http.post('/auth/forgot-password', { email });
  return res.data;
}

export async function resetPassword(token, newPassword) {
  const res = await http.post('/auth/reset-password', { token, new_password: newPassword });
  return res.data;
}
