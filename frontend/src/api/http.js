// src/api/http.js
import axios from 'axios';

const http = axios.create({ baseURL: 'http://localhost:8000' });

// Attach JWT to every request automatically
http.interceptors.request.use(config => {
  const token = sessionStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export default http;
