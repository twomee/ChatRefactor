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
    <form onSubmit={handleSubmit} style={{ display: 'flex', padding: 8, borderTop: '1px solid #ccc' }}>
      <input
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder="Type a message..."
        style={{ flex: 1, marginRight: 8, padding: '6px 10px' }}
      />
      <button type="submit">Send</button>
    </form>
  );
}
