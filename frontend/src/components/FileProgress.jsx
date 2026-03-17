// src/components/FileProgress.jsx
import { useState } from 'react';
import http from '../api/http';

export default function FileUpload({ roomId }) {
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);

  async function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;

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
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }

  return (
    <div>
      <input type="file" onChange={handleFileChange} disabled={uploading} />
      {uploading && (
        <div style={{ marginTop: 8 }}>
          <div style={{ width: '100%', background: '#eee', borderRadius: 4 }}>
            <div style={{ width: `${progress}%`, background: '#4a9eed', height: 8, borderRadius: 4, transition: 'width 0.2s' }} />
          </div>
          <small>{progress}%</small>
        </div>
      )}
    </div>
  );
}
