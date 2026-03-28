// src/components/MessageInput.jsx
import { useRef, useState } from 'react';
import { uploadFile } from '../../services/fileApi';

export default function MessageInput({ onSend, roomName, roomId, isPM = false, onTyping }) {
  const [text, setText] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploadError, setUploadError] = useState('');
  const fileRef = useRef(null);
  const typingTimeoutRef = useRef(null);

  function handleChange(e) {
    setText(e.target.value);
    // Debounce typing emission — send at most once every 2 seconds
    if (onTyping && !typingTimeoutRef.current) {
      onTyping();
      typingTimeoutRef.current = setTimeout(() => {
        typingTimeoutRef.current = null;
      }, 2000);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (!text.trim()) return;
    onSend(text.trim());
    setText('');
  }

  async function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploadError('');
    setUploading(true);
    setProgress(0);
    try {
      await uploadFile(roomId, file, (evt) => {
        if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100));
      });
    } catch (err) {
      setUploadError(err.response?.data?.error || err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      setProgress(0);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  return (
    <div className="message-input-wrapper">
      {/* Upload progress bar */}
      {uploading && (
        <div style={{ padding: '0 4px 6px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <div className="file-progress-bar" style={{ flex: 1 }}>
            <div className="file-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <span className="file-progress-text">{progress}%</span>
        </div>
      )}
      {uploadError && (
        <div style={{ padding: '0 4px 4px' }}>
          <span className="file-error">{uploadError}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="message-input-form">
        {/* File attachment — hidden in PM mode (PMs don't support file uploads) */}
        {!isPM && (
          <>
            <input
              ref={fileRef}
              type="file"
              style={{ display: 'none' }}
              onChange={handleFileChange}
              disabled={uploading}
            />
            <button
              type="button"
              className="input-icon-btn"
              title="Attach file"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>
          </>
        )}

        {/* text input */}
        <input
          className="message-input"
          value={text}
          onChange={handleChange}
          placeholder={isPM ? `Message ${roomName}…` : roomName ? `Message #${roomName}...` : 'Type a message...'}
        />

        {/* right-side icon actions */}
        <div className="input-actions">
          <button type="button" className="input-icon-btn" title="Emoji">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
              <line x1="9" y1="9" x2="9.01" y2="9"/>
              <line x1="15" y1="9" x2="15.01" y2="9"/>
            </svg>
          </button>
          <button type="button" className="input-icon-btn" title="GIF" style={{ fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.03em' }}>
            GIF
          </button>
          <button type="button" className="input-icon-btn" title="Voice message">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          </button>
        </div>

        {/* send button */}
        <button type="submit" className="message-send-btn-circle" disabled={!text.trim()} title="Send">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </form>
    </div>
  );
}
