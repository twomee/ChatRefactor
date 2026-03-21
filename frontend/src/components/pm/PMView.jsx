// src/components/PMView.jsx
import { useState } from 'react';
import MessageList from '../chat/MessageList';

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

export default function PMView({ username, messages = [], onSend, onScrollToBottom }) {
  const [text, setText] = useState('');

  function handleSend() {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText('');
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="pm-view">
      {/* Header */}
      <div className="pm-header">
        <div className="pm-header-avatar">{getInitials(username)}</div>
        <div className="pm-header-info">
          <div className="pm-header-name">{username}</div>
          <div className="pm-header-label">Private conversation</div>
        </div>
      </div>

      {/* Message list */}
      <MessageList messages={messages} onScrollToBottom={onScrollToBottom} />

      {/* Input */}
      <div className="message-input-wrapper">
        <div className="message-input-form">
          <input
            className="message-input"
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Message ${username}...`}
          />
          <button
            className="message-send-btn"
            onClick={handleSend}
            disabled={!text.trim()}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
