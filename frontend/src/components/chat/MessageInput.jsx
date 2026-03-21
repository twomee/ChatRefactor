// src/components/MessageInput.jsx
import { useState } from 'react';

export default function MessageInput({ onSend }) {
  const [text, setText] = useState('');

  function handleSubmit(e) {
    e.preventDefault();
    if (!text.trim()) return;
    onSend(text.trim());
    setText('');
  }

  return (
    <div className="message-input-wrapper">
      <form onSubmit={handleSubmit} className="message-input-form">
        <input
          className="message-input"
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Type a message..."
        />
        <button type="submit" className="message-send-btn" disabled={!text.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
