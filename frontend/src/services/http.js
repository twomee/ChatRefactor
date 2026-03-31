// src/services/http.js
import axios from 'axios';
import { API_BASE } from '../config/constants';

const http = axios.create({ baseURL: API_BASE });

// Attach JWT to every request automatically
http.interceptors.request.use(config => {
  const token = sessionStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Endpoints where a 401 means "wrong current password", not "expired token".
// Auto-logout must NOT fire for these — the caller handles the error locally.
const NO_AUTO_LOGOUT = ['/auth/profile/email', '/auth/profile/password', '/auth/2fa/disable'];

// Global 401 handler — clear stale session when an authenticated request fails.
// Only triggers when a token was sent (stale session), NOT on login attempts or
// password-verification endpoints listed in NO_AUTO_LOGOUT.
http.interceptors.response.use(
  response => response,
  error => {
    const hadToken = error.config?.headers?.Authorization;
    const url = error.config?.url || '';
    const isPasswordVerification = NO_AUTO_LOGOUT.some(path => url.includes(path));
    if (error.response?.status === 401 && hadToken && !isPasswordVerification) {
      sessionStorage.removeItem('token');
      sessionStorage.removeItem('user');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default http;
