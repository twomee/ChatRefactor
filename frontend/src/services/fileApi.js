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
 * Upload a file into a PM conversation.
 * @param {string} recipientUsername - The recipient's username
 * @param {File} file - The file to upload
 * @param {function} onProgress - Progress callback (optional)
 */
export function uploadPMFile(recipientUsername, file, onProgress) {
  const form = new FormData();
  form.append('file', file);
  return http.post(`/files/upload?recipient=${encodeURIComponent(recipientUsername)}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
  });
}

/**
 * Download a file via Authorization header (not URL query param).
 * Creates a temporary blob URL and triggers the browser save dialog.
 * This avoids leaking the JWT in browser history and server logs.
 */
export async function downloadFile(fileId, filename) {
  try {
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
    setTimeout(() => URL.revokeObjectURL(url), 100);
  } catch (err) {
    const status = err.response?.status;
    if (status === 403) throw new Error('You do not have permission to download this file.');
    if (status === 404) throw new Error('File not found.');
    throw new Error('Download failed. Please try again.');
  }
}
