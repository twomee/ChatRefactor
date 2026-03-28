// src/components/chat/MessageList.jsx
import { useEffect, useRef, useCallback, useState } from 'react';
import { formatSize } from '../../utils/formatting';
import { downloadFile } from '../../services/fileApi';
import data from '@emoji-mart/data';
import Picker from '@emoji-mart/react';

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
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

export default function MessageList({ messages, onScrollToBottom, onAddReaction, onRemoveReaction, currentUser }) {
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

        const grouped = groupReactions(msg.reactions, currentUser);

        return (
          <div key={i} className="msg">
            <div className="msg-avatar">{getInitials(msg.from)}</div>
            <div className="msg-body">
              <span className="msg-author">{msg.from}</span>
              <div className="msg-text">{msg.text}</div>
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
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
