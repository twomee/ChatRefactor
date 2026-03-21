// src/services/fileApi.js — File API calls
import http from './http';
import { API_BASE } from '../config/constants';

export function uploadFile(roomId, file, onProgress) {
  const form = new FormData();
  form.append('file', file);
  return http.post(`/files/upload?room_id=${roomId}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
  });
}

export function listRoomFiles(roomId) {
  return http.get(`/files/room/${roomId}`);
}

export function getDownloadUrl(fileId) {
  const token = sessionStorage.getItem('token');
  return `${API_BASE}/files/download/${fileId}?token=${token}`;
}
