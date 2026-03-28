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

// Global 401 handler — clear stale session when an authenticated request fails.
// Only triggers when a token was sent (stale session), NOT on login attempts.
http.interceptors.response.use(
  response => response,
  error => {
    const hadToken = error.config?.headers?.Authorization;
    if (error.response?.status === 401 && hadToken) {
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
