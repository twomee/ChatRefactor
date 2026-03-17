// src/components/FileProgress.jsx
import { useState, useRef } from 'react';
import http from '../api/http';

export default function FileUpload({ roomId }) {
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);

  async function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;

    setError('');
    const formData = new FormData();
    formData.append('file', file);
    setUploading(true);
    setProgress(0);

    try {
      await http.post(`/files/upload?room_id=${roomId}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100));
        },
      });
      // Reset so the same file can be re-uploaded
      if (inputRef.current) inputRef.current.value = '';
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }

  return (
    <div style={{ padding: '4px 12px', borderTop: '1px solid #eee' }}>
      <input ref={inputRef} type="file" onChange={handleFileChange} disabled={uploading} />
      {uploading && (
        <div style={{ marginTop: 4 }}>
          <div style={{ width: '100%', background: '#eee', borderRadius: 4 }}>
            <div style={{ width: `${progress}%`, background: '#4a9eed', height: 6, borderRadius: 4, transition: 'width 0.2s' }} />
          </div>
          <small style={{ color: '#555' }}>Uploading… {progress}%</small>
        </div>
      )}
      {error && <small style={{ color: 'red' }}>{error}</small>}
    </div>
  );
}
