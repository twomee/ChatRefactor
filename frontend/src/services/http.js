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

export default http;
