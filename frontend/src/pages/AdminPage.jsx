// src/pages/AdminPage.jsx
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import http from '../api/http';

export default function AdminPage() {
  const [rooms, setRooms] = useState([]);
  const [connectedUsers, setConnectedUsers] = useState({});
  const [roomFiles, setRoomFiles] = useState({});
  const [status, setStatus] = useState('');
  const [promoteUsername, setPromoteUsername] = useState('');
  const [newRoomName, setNewRoomName] = useState('');
  const [expandedRoomFiles, setExpandedRoomFiles] = useState(null);
  const navigate = useNavigate();

  const API_BASE = 'http://localhost:8000';

  const loadData = useCallback(async () => {
    const [roomsRes, usersRes] = await Promise.all([
      http.get('/admin/rooms').catch(() => ({ data: [] })),
      http.get('/admin/users').catch(() => ({ data: {} })),
    ]);
    setRooms(roomsRes.data);
    setConnectedUsers(usersRes.data);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  async function run(fn, msg) {
    try {
      await fn();
      setStatus(msg);
      loadData();
    } catch (e) {
      setStatus(e.response?.data?.detail || 'Error');
    }
  }

  async function loadRoomFiles(roomId) {
    if (expandedRoomFiles === roomId) {
      setExpandedRoomFiles(null);
      return;
    }
    try {
      const res = await http.get(`/files/room/${roomId}`);
      setRoomFiles(prev => ({ ...prev, [roomId]: res.data }));
      setExpandedRoomFiles(roomId);
    } catch (e) {
      setStatus('Failed to load files');
    }
  }

  const token = sessionStorage.getItem('token');

  // Count all connected users across all rooms (deduplicated)
  const allConnected = [...new Set(Object.values(connectedUsers).flat())];

  return (
    <div style={{ padding: 24, maxWidth: 960, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2>Admin Panel</h2>
        <button onClick={() => navigate('/chat')}>← Back to Chat</button>
      </div>

      {status && (
        <div style={{ padding: 8, background: '#e8f5e9', borderRadius: 4, marginBottom: 16 }}>
          {status}
        </div>
      )}

      {/* Global controls */}
      <section style={{ marginBottom: 24 }}>
        <h3>Global Chat Controls</h3>
        <button onClick={() => run(() => http.post('/admin/chat/close'), 'All rooms closed')} style={{ marginRight: 8 }}>
          Close All Rooms
        </button>
        <button onClick={() => run(() => http.post('/admin/chat/open'), 'All rooms opened')} style={{ marginRight: 8 }}>
          Open All Rooms
        </button>
        <button
          onClick={() => {
            if (!confirm('Reset ALL user accounts? This cannot be undone.')) return;
            run(() => http.delete('/admin/db'), 'Database reset');
          }}
          style={{ background: '#f44', color: '#fff' }}
        >
          Reset Database
        </button>
      </section>

      {/* Add Room */}
      <section style={{ marginBottom: 24 }}>
        <h3>Add Room</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            placeholder="Room name"
            value={newRoomName}
            onChange={e => setNewRoomName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && newRoomName.trim() && run(
              () => http.post('/rooms/', { name: newRoomName.trim() }),
              `Room "${newRoomName}" created`
            ) && setNewRoomName('')}
            style={{ padding: '4px 8px', flex: 1, maxWidth: 240 }}
          />
          <button
            disabled={!newRoomName.trim()}
            onClick={() => {
              run(() => http.post('/rooms/', { name: newRoomName.trim() }), `Room "${newRoomName}" created`);
              setNewRoomName('');
            }}
          >
            Create Room
          </button>
        </div>
      </section>

      {/* Promote User */}
      <section style={{ marginBottom: 24 }}>
        <h3>Promote User (all rooms)</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            placeholder="Username"
            value={promoteUsername}
            onChange={e => setPromoteUsername(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && promoteUsername.trim() && run(
              () => http.post(`/admin/promote?username=${encodeURIComponent(promoteUsername.trim())}`),
              `${promoteUsername} promoted`
            ) && setPromoteUsername('')}
            style={{ padding: '4px 8px', flex: 1, maxWidth: 240 }}
          />
          <button
            disabled={!promoteUsername.trim()}
            onClick={() => {
              run(
                () => http.post(`/admin/promote?username=${encodeURIComponent(promoteUsername.trim())}`),
                `${promoteUsername} promoted to admin in all rooms`
              );
              setPromoteUsername('');
            }}
          >
            Promote
          </button>
        </div>
      </section>

      {/* Connected Users */}
      <section style={{ marginBottom: 24 }}>
        <h3>Connected Users ({allConnected.length})</h3>
        {allConnected.length === 0 ? (
          <p style={{ color: '#999' }}>No users connected</p>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {allConnected.map(u => (
              <span key={u} style={{ padding: '2px 8px', background: '#e3f2fd', borderRadius: 12, fontSize: 13 }}>
                {u}
              </span>
            ))}
          </div>
        )}
      </section>

      {/* Rooms table */}
      <section>
        <h3>Rooms</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              <th style={{ padding: 8, textAlign: 'left' }}>ID</th>
              <th style={{ padding: 8, textAlign: 'left' }}>Name</th>
              <th style={{ padding: 8, textAlign: 'left' }}>Status</th>
              <th style={{ padding: 8, textAlign: 'left' }}>Users in room</th>
              <th style={{ padding: 8, textAlign: 'left' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rooms.map(room => (
              <>
                <tr key={room.id} style={{ borderBottom: '1px solid #eee', background: room.is_active ? 'inherit' : '#fff3f3' }}>
                  <td style={{ padding: 8 }}>{room.id}</td>
                  <td style={{ padding: 8 }}>{room.name}</td>
                  <td style={{ padding: 8 }}>{room.is_active ? '🟢 Open' : '🔴 Closed'}</td>
                  <td style={{ padding: 8, color: '#555' }}>
                    {(connectedUsers[room.id] || []).join(', ') || <span style={{ color: '#bbb' }}>—</span>}
                  </td>
                  <td style={{ padding: 8 }}>
                    {room.is_active ? (
                      <button
                        onClick={() => run(() => http.post(`/admin/rooms/${room.id}/close`), `Room "${room.name}" closed`)}
                        style={{ fontSize: '0.8em', marginRight: 4 }}
                      >
                        Close
                      </button>
                    ) : (
                      <button
                        onClick={() => run(() => http.post(`/admin/rooms/${room.id}/open`), `Room "${room.name}" opened`)}
                        style={{ fontSize: '0.8em', marginRight: 4 }}
                      >
                        Open
                      </button>
                    )}
                    <button
                      onClick={() => loadRoomFiles(room.id)}
                      style={{ fontSize: '0.8em' }}
                    >
                      {expandedRoomFiles === room.id ? 'Hide Files' : 'Files'}
                    </button>
                  </td>
                </tr>

                {/* Expandable files section per room */}
                {expandedRoomFiles === room.id && (
                  <tr key={`files-${room.id}`}>
                    <td colSpan={5} style={{ padding: '0 16px 12px 16px', background: '#fafafa' }}>
                      {(roomFiles[room.id] || []).length === 0 ? (
                        <p style={{ color: '#999', margin: '8px 0' }}>No files in this room</p>
                      ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                          <thead>
                            <tr style={{ borderBottom: '1px solid #ddd' }}>
                              <th style={{ padding: '4px 8px', textAlign: 'left' }}>File</th>
                              <th style={{ padding: '4px 8px', textAlign: 'left' }}>Sender</th>
                              <th style={{ padding: '4px 8px', textAlign: 'left' }}>Size</th>
                              <th style={{ padding: '4px 8px', textAlign: 'left' }}>Uploaded</th>
                              <th style={{ padding: '4px 8px' }}></th>
                            </tr>
                          </thead>
                          <tbody>
                            {(roomFiles[room.id] || []).map(f => (
                              <tr key={f.id} style={{ borderBottom: '1px solid #eee' }}>
                                <td style={{ padding: '4px 8px' }}>📎 {f.original_name}</td>
                                <td style={{ padding: '4px 8px' }}>{f.sender}</td>
                                <td style={{ padding: '4px 8px', color: '#888' }}>{formatSize(f.file_size)}</td>
                                <td style={{ padding: '4px 8px', color: '#888' }}>{new Date(f.uploaded_at).toLocaleString()}</td>
                                <td style={{ padding: '4px 8px' }}>
                                  <a
                                    href={`${API_BASE}/files/download/${f.id}?token=${token}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{ color: '#1976d2' }}
                                  >
                                    Download
                                  </a>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function formatSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
