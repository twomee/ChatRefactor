// src/pages/AdminPage.jsx
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import http from '../api/http';

export default function AdminPage() {
  const [rooms, setRooms] = useState([]);
  const [connectedUsers, setConnectedUsers] = useState({});
  const [status, setStatus] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    http.get('/admin/rooms').then(res => setRooms(res.data)).catch(() => {});
    http.get('/admin/users').then(res => setConnectedUsers(res.data)).catch(() => {});
  }, []);

  async function handleCloseChat() {
    try {
      await http.post('/admin/chat/close');
      setStatus('Chat closed');
    } catch (e) {
      setStatus(e.response?.data?.detail || 'Error');
    }
  }

  async function handleOpenChat() {
    try {
      await http.post('/admin/chat/open');
      setStatus('Chat opened');
    } catch (e) {
      setStatus(e.response?.data?.detail || 'Error');
    }
  }

  async function handleResetDb() {
    if (!confirm('Reset ALL user accounts? This cannot be undone.')) return;
    try {
      await http.delete('/admin/db');
      setStatus('Database reset');
    } catch (e) {
      setStatus(e.response?.data?.detail || 'Error');
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 800, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2>Admin Panel</h2>
        <button onClick={() => navigate('/chat')}>← Back to Chat</button>
      </div>

      {status && <div style={{ padding: 8, background: '#e8f5e9', borderRadius: 4, marginBottom: 16 }}>{status}</div>}

      {/* Chat controls */}
      <div style={{ marginBottom: 24 }}>
        <h3>Chat Controls</h3>
        <button onClick={handleCloseChat} style={{ marginRight: 8 }}>Close Chat</button>
        <button onClick={handleOpenChat} style={{ marginRight: 8 }}>Open Chat</button>
        <button onClick={handleResetDb} style={{ background: '#f44', color: '#fff' }}>Reset Database</button>
      </div>

      {/* Rooms */}
      <div style={{ marginBottom: 24 }}>
        <h3>Rooms</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              <th style={{ padding: 8, textAlign: 'left' }}>ID</th>
              <th style={{ padding: 8, textAlign: 'left' }}>Name</th>
              <th style={{ padding: 8, textAlign: 'left' }}>Active</th>
              <th style={{ padding: 8, textAlign: 'left' }}>Connected</th>
            </tr>
          </thead>
          <tbody>
            {rooms.map(room => (
              <tr key={room.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: 8 }}>{room.id}</td>
                <td style={{ padding: 8 }}>{room.name}</td>
                <td style={{ padding: 8 }}>{room.is_active ? '✓' : '✗'}</td>
                <td style={{ padding: 8 }}>{(connectedUsers[room.id] || []).join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
