// src/components/MessageList.jsx
import { useEffect, useRef } from 'react';

export default function MessageList({ messages }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
      {(messages || []).map((msg, i) => (
        <div key={i} style={{ marginBottom: 6 }}>
          {msg.isPrivate && <em style={{ color: '#888' }}>[private] </em>}
          <strong>{msg.from}: </strong>{msg.text}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
