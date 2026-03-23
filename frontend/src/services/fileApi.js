// src/services/fileApi.js — File API calls
import http from './http';

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

/**
 * Download a file via Authorization header (not URL query param).
 * Creates a temporary blob URL and triggers the browser save dialog.
 * This avoids leaking the JWT in browser history and server logs.
 */
export async function downloadFile(fileId, filename) {
  const response = await http.get(`/files/download/${fileId}`, {
    responseType: 'blob',
  });
  const url = URL.createObjectURL(response.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || 'download';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
