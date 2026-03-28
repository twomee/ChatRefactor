// src/components/MessageInput.jsx
import { useRef, useState, useEffect } from 'react';
import { uploadFile } from '../../services/fileApi';

export default function MessageInput({ onSend, roomName, roomId, isPM = false, editingMessage, onCancelEdit }) {
  const [text, setText] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploadError, setUploadError] = useState('');
  const fileRef = useRef(null);
  const inputRef = useRef(null);

  // When editingMessage changes, pre-fill the input
  useEffect(() => {
    if (editingMessage) {
      setText(editingMessage.text);
      inputRef.current?.focus();
    }
  }, [editingMessage]);

  // Allow Escape key to cancel edit mode
  useEffect(() => {
    if (!editingMessage) return;
    const handler = (e) => { if (e.key === 'Escape') onCancelEdit?.(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [editingMessage, onCancelEdit]);

  function handleSubmit(e) {
    e.preventDefault();
    if (!text.trim()) return;
    if (editingMessage) {
      onSend(text.trim(), editingMessage.msg_id);
    } else {
      onSend(text.trim());
    }
    setText('');
  }

  function handleCancelEdit() {
    setText('');
    if (onCancelEdit) onCancelEdit();
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
      {/* Edit mode banner */}
      {editingMessage && (
        <div className="edit-banner">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
          <span>Editing message</span>
          <button type="button" className="edit-banner-cancel" onClick={handleCancelEdit}>Cancel</button>
        </div>
      )}

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
        {/* File attachment — hidden in PM mode and edit mode */}
        {!isPM && !editingMessage && (
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
          ref={inputRef}
          className="message-input"
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder={editingMessage ? 'Edit your message...' : isPM ? `Message ${roomName}\u2026` : roomName ? `Message #${roomName}...` : 'Type a message...'}
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
        <button type="submit" className="message-send-btn-circle" disabled={!text.trim()} title={editingMessage ? 'Save' : 'Send'}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </form>
    </div>
  );
}
