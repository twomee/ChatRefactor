// src/components/FileProgress.jsx
import { useState, useRef } from 'react';
import { uploadFile } from '../services/fileApi';

export default function FileUpload({ roomId }) {
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);

  async function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;

    setError('');
    setUploading(true);
    setProgress(0);

    try {
      await uploadFile(roomId, file, (evt) => {
        if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100));
      });
      if (inputRef.current) inputRef.current.value = '';
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }

  return (
    <div className="file-upload-wrapper">
      <label className={`file-upload-label ${uploading ? 'disabled' : ''}`}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
        </svg>
        Attach file
        <input
          ref={inputRef}
          className="file-upload-input"
          type="file"
          onChange={handleFileChange}
          disabled={uploading}
        />
      </label>

      {uploading && (
        <>
          <div className="file-progress-bar">
            <div className="file-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <span className="file-progress-text">{progress}%</span>
        </>
      )}
      {error && <span className="file-error">{error}</span>}
    </div>
  );
}
