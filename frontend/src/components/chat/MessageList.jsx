// src/components/MessageList.jsx
import { useEffect, useRef, useCallback } from 'react';
import { formatSize } from '../../utils/formatting';
import { downloadFile } from '../../services/fileApi';

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

export default function MessageList({ messages, onScrollToBottom, currentUser, onEditMessage, onDeleteMessage }) {
  const endRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) {
      endRef.current?.scrollIntoView({ behavior: 'smooth' });
      return;
    }
    // Only auto-scroll if user is near the bottom (within 150px)
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
    if (isNearBottom) {
      endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
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
    <div ref={containerRef} onScroll={handleScroll} className="message-list">
      {(messages || []).map((msg, i) => {
        if (msg.isSystem) {
          return (
            <div key={i} className="msg msg-system">
              <span className="msg-system-text">{msg.text}</span>
            </div>
          );
        }

        if (msg.isFile) {
          return (
            <div key={i} className="msg">
              <div className="msg-avatar">{getInitials(msg.from)}</div>
              <div className="msg-body">
                <span className="msg-author">{msg.from}</span>
                <div>
                  <a
                    href="#"
                    onClick={(e) => { e.preventDefault(); downloadFile(msg.fileId, msg.text); }}
                    className="msg-file-link"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
                    </svg>
                    {msg.text}
                  </a>
                  {msg.fileSize && <span className="msg-file-size">({formatSize(msg.fileSize)})</span>}
                </div>
              </div>
            </div>
          );
        }

        if (msg.isPrivate) {
          const label = msg.isSelf ? `You \u2192 ${msg.to}` : `${msg.from} \u2192 You`;
          return (
            <div key={i} className="msg msg-private">
              <div className="msg-avatar">{getInitials(msg.isSelf ? msg.to : msg.from)}</div>
              <div className="msg-body">
                <div className="msg-private-label">{label}</div>
                <div className="msg-text">{msg.text}</div>
              </div>
            </div>
          );
        }

        // Deleted message — render in muted style
        if (msg.is_deleted) {
          return (
            <div key={i} className="msg">
              <div className="msg-avatar">{getInitials(msg.from)}</div>
              <div className="msg-body">
                <span className="msg-author">{msg.from}</span>
                <div className="msg-text msg-deleted-text">[deleted]</div>
              </div>
            </div>
          );
        }

        const isOwn = currentUser && msg.from === currentUser;

        return (
          <div key={i} className="msg">
            <div className="msg-avatar">{getInitials(msg.from)}</div>
            <div className="msg-body">
              <span className="msg-author">{msg.from}</span>
              {msg.edited_at && <span className="msg-edited-badge">(edited)</span>}
              <div className="msg-text">{msg.text}</div>
            </div>
            {isOwn && msg.msg_id && (
              <div className="msg-actions">
                <button
                  className="msg-action-btn"
                  title="Edit"
                  onClick={() => onEditMessage && onEditMessage(msg)}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
                <button
                  className="msg-action-btn"
                  title="Delete"
                  onClick={() => onDeleteMessage && onDeleteMessage(msg)}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
