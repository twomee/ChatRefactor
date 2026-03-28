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

// Global 401 handler — clear stale session so the user is redirected to login.
// This catches the case where the backend SECRET_KEY changed (e.g., after a
// Docker rebuild) and the stored token is no longer valid.
http.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      sessionStorage.removeItem('token');
      sessionStorage.removeItem('user');
      // Redirect to login if not already there
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default http;
