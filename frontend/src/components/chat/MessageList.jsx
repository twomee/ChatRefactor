// src/components/chat/MessageList.jsx
import { useEffect, useRef, useCallback, useState } from 'react';
import { formatSize } from '../../utils/formatting';
import { isImageFile } from '../../utils/fileHelpers';
import { downloadFile } from '../../services/fileApi';
import MarkdownMessage from './MarkdownMessage';
import { API_BASE } from '../../config/constants';
import data from '@emoji-mart/data';
import Picker from '@emoji-mart/react';

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

function renderMessageText(text, currentUser) {
  if (!text) return text;
  const parts = text.split(/(@\w+)/g);
  return parts.map((part, i) => {
    if (part.startsWith('@')) {
      const isSelf = part.toLowerCase() === `@${currentUser?.toLowerCase()}`;
      return (
        <span key={i} className={`mention ${isSelf ? 'mention-self' : ''}`}>
          {part}
        </span>
      );
    }
    return part;
  });
}

/**
 * Group reactions by emoji, producing an array of { emoji, count, users, userReacted }
 * where userReacted is true if currentUser is among the reactors.
 */
function groupReactions(reactions, currentUser) {
  if (!reactions || reactions.length === 0) return [];
  const map = {};
  for (const r of reactions) {
    if (!map[r.emoji]) {
      map[r.emoji] = { emoji: r.emoji, count: 0, users: [], userReacted: false };
    }
    map[r.emoji].count++;
    map[r.emoji].users.push(r.username);
    if (r.username === currentUser) {
      map[r.emoji].userReacted = true;
    }
  }
  return Object.values(map);
}

export default function MessageList({ messages, onScrollToBottom, currentUser, onEditMessage, onDeleteMessage, onAddReaction, onRemoveReaction }) {
  const endRef = useRef(null);
  const containerRef = useRef(null);
  const [pickerMsgId, setPickerMsgId] = useState(null);

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

  // Close picker when clicking outside
  useEffect(() => {
    if (pickerMsgId === null) return;
    function handleClickOutside(e) {
      if (!e.target.closest('.emoji-picker-popover') && !e.target.closest('.reaction-add-btn')) {
        setPickerMsgId(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [pickerMsgId]);

  function handleReactionChipClick(msgId, emoji, userReacted) {
    if (userReacted) {
      onRemoveReaction?.(msgId, emoji);
    } else {
      onAddReaction?.(msgId, emoji);
    }
  }

  function handlePickerSelect(msgId, emojiData) {
    onAddReaction?.(msgId, emojiData.native);
    setPickerMsgId(null);
  }

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
                <div className="msg-file-content">
                  {isImageFile(msg.text) ? (
                    <div className="msg-image-preview">
                      <img
                        src={`${API_BASE}/files/download/${msg.fileId}?token=${encodeURIComponent(sessionStorage.getItem('token'))}`}
                        alt={msg.text}
                        className="msg-inline-image"
                        loading="lazy"
                        onClick={() => window.open(
                          `${API_BASE}/files/download/${msg.fileId}?token=${encodeURIComponent(sessionStorage.getItem('token'))}`,
                          '_blank',
                        )}
                        onError={(e) => {
                          e.target.style.display = 'none';
                          e.target.nextSibling?.classList?.add('show-fallback');
                        }}
                      />
                      <div className="msg-image-fallback">
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
                      </div>
                      <span className="msg-image-filename">
                        {msg.text}{msg.fileSize ? ` (${formatSize(msg.fileSize)})` : ''}
                      </span>
                    </div>
                  ) : (
                    <>
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
                    </>
                  )}
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
                <div className="msg-text"><span className="msg-text-content"><MarkdownMessage text={msg.text} /></span></div>
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
        const grouped = groupReactions(msg.reactions, currentUser);

        return (
          <div key={i} className="msg">
            <div className="msg-avatar">{getInitials(msg.from)}</div>
            <div className="msg-body">
              <span className="msg-author">{msg.from}</span>
              {msg.edited_at && <span className="msg-edited-badge">(edited)</span>}
              <div className="msg-text"><span className="msg-text-content">{renderMessageText(msg.text, currentUser)}</span></div>
              {/* Reaction chips */}
              {(grouped.length > 0 || msg.msg_id) && (
                <div className="msg-reactions">
                  {grouped.map(g => (
                    <button
                      key={g.emoji}
                      className={`reaction-chip${g.userReacted ? ' reaction-mine' : ''}`}
                      onClick={() => handleReactionChipClick(msg.msg_id, g.emoji, g.userReacted)}
                      title={g.users.join(', ')}
                    >
                      <span>{g.emoji}</span>
                      <span className="reaction-count">{g.count}</span>
                    </button>
                  ))}
                  {msg.msg_id && onAddReaction && (
                    <div style={{ position: 'relative', display: 'inline-block' }}>
                      <button
                        className="reaction-add-btn"
                        onClick={() => setPickerMsgId(pickerMsgId === msg.msg_id ? null : msg.msg_id)}
                        title="Add reaction"
                      >
                        +
                      </button>
                      {pickerMsgId === msg.msg_id && (
                        <div className="emoji-picker-popover">
                          <Picker
                            data={data}
                            onEmojiSelect={(emoji) => handlePickerSelect(msg.msg_id, emoji)}
                            theme="dark"
                            previewPosition="none"
                            skinTonePosition="none"
                            maxFrequentRows={1}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
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
