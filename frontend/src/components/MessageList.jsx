// src/components/MessageList.jsx
import { useEffect, useRef } from 'react';

const API_BASE = 'http://localhost:8000';

function formatSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function MessageList({ messages }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
      {(messages || []).map((msg, i) => {
        // System message (join/leave/admin/mute/kick events)
        if (msg.isSystem) {
          return (
            <div key={i} style={{ marginBottom: 4, color: '#888', fontStyle: 'italic', fontSize: '0.85em', textAlign: 'center' }}>
              — {msg.text} —
            </div>
          );
        }

        // File shared message
        if (msg.isFile) {
          const token = sessionStorage.getItem('token');
          return (
            <div key={i} style={{ marginBottom: 6 }}>
              <strong>{msg.from}: </strong>
              <a
                href={`${API_BASE}/files/download/${msg.fileId}?token=${token}`}
                target="_blank"
                rel="noreferrer"
                style={{ color: '#1976d2' }}
              >
                📎 {msg.text}
              </a>
              {msg.fileSize ? <span style={{ color: '#999', fontSize: '0.8em' }}> ({formatSize(msg.fileSize)})</span> : null}
            </div>
          );
        }

        // Private message
        if (msg.isPrivate) {
          const label = msg.isSelf ? `[private → ${msg.to}]` : `[private from ${msg.from}]`;
          return (
            <div key={i} style={{ marginBottom: 6, background: '#f3e5f5', borderLeft: '3px solid #9c27b0', padding: '2px 6px', borderRadius: 2 }}>
              <em style={{ color: '#7b1fa2' }}>{label} </em>
              {msg.isSelf ? msg.text : <><strong>{msg.from}: </strong>{msg.text}</>}
            </div>
          );
        }

        // Normal chat message
        return (
          <div key={i} style={{ marginBottom: 6 }}>
            <strong>{msg.from}: </strong>{msg.text}
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
