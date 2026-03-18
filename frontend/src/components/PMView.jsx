// src/components/PMView.jsx
import { useState } from 'react';
import MessageList from './MessageList';

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
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontWeight: 'bold', color: '#7b1fa2' }}>
        💬 Private chat with {username}
      </div>

      {/* Message list */}
      <MessageList messages={messages} onScrollToBottom={onScrollToBottom} />

      {/* Input */}
      <div style={{ display: 'flex', padding: 8, borderTop: '1px solid #ccc', gap: 8 }}>
        <input
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`Message ${username}...`}
          style={{ flex: 1, padding: '6px 10px', borderRadius: 4, border: '1px solid #ccc' }}
        />
        <button
          onClick={handleSend}
          disabled={!text.trim()}
          style={{ padding: '6px 14px', background: '#9c27b0', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
