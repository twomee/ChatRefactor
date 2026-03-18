// src/components/MessageList.jsx
import { useEffect, useRef, useCallback } from 'react';
import { formatSize } from '../utils/formatting';
import { getDownloadUrl } from '../services/fileApi';

export default function MessageList({ messages, onScrollToBottom }) {
  const endRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleScroll = useCallback(() => {
    if (!onScrollToBottom) return;
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom <= 50) {
      onScrollToBottom();
    }
  }, [onScrollToBottom]);

  useEffect(() => {
    handleScroll();
  }, [messages, handleScroll]);

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      style={{ flex: 1, overflowY: 'auto', padding: 12 }}
    >
      {(messages || []).map((msg, i) => {
        if (msg.isSystem) {
          return (
            <div key={i} style={{ marginBottom: 4, color: '#888', fontStyle: 'italic', fontSize: '0.85em', textAlign: 'center' }}>
              — {msg.text} —
            </div>
          );
        }
        if (msg.isFile) {
          return (
            <div key={i} style={{ marginBottom: 6 }}>
              <strong>{msg.from}: </strong>
              <a
                href={getDownloadUrl(msg.fileId)}
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
        if (msg.isPrivate) {
          const label = msg.isSelf ? `[private → ${msg.to}]` : `[private from ${msg.from}]`;
          return (
            <div key={i} style={{ marginBottom: 6, background: '#f3e5f5', borderLeft: '3px solid #9c27b0', padding: '2px 6px', borderRadius: 2 }}>
              <em style={{ color: '#7b1fa2' }}>{label} </em>
              {msg.isSelf ? msg.text : <><strong>{msg.from}: </strong>{msg.text}</>}
            </div>
          );
        }
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
