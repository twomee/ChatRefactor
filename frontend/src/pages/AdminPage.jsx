// src/pages/AdminPage.jsx
import { useState, useEffect, useCallback, Fragment } from 'react';
import { useNavigate } from 'react-router-dom';
import * as adminApi from '../services/adminApi';
import { createRoom } from '../services/roomApi';
import { listRoomFiles, getDownloadUrl } from '../services/fileApi';
import { formatSize } from '../utils/formatting';

export default function AdminPage() {
  const [rooms, setRooms] = useState([]);
  const [onlineUsers, setOnlineUsers] = useState([]);
  const [roomUsers, setRoomUsers] = useState({});
  const [roomFiles, setRoomFiles] = useState({});
  const [status, setStatus] = useState('');
  const [promoteUsername, setPromoteUsername] = useState('');
  const [newRoomName, setNewRoomName] = useState('');
  const [expandedRoomFiles, setExpandedRoomFiles] = useState(null);
  const navigate = useNavigate();

  const loadData = useCallback(async () => {
    const [roomsRes, usersRes] = await Promise.all([
      adminApi.getRooms().catch(() => ({ data: [] })),
      adminApi.getUsers().catch(() => ({ data: { all_online: [], per_room: {} } })),
    ]);
    setRooms(roomsRes.data);
    setOnlineUsers(usersRes.data.all_online || []);
    setRoomUsers(usersRes.data.per_room || {});
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 3000);
    return () => clearInterval(interval);
  }, [loadData]);

  async function run(fn, msg) {
    try {
      await fn();
      setStatus(msg);
      loadData();
    } catch (e) {
      setStatus(e.response?.data?.detail || 'Error');
    }
  }

  async function handleLoadRoomFiles(roomId) {
    if (expandedRoomFiles === roomId) {
      setExpandedRoomFiles(null);
      return;
    }
    try {
      const res = await listRoomFiles(roomId);
      setRoomFiles(prev => ({ ...prev, [roomId]: res.data }));
      setExpandedRoomFiles(roomId);
    } catch {
      setStatus('Failed to load files');
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
        <h2>Admin Panel</h2>
        <button onClick={() => navigate('/chat')}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"/>
            <polyline points="12 19 5 12 12 5"/>
          </svg>
          Back to Chat
        </button>
      </div>

      {status && <div className="admin-status">{status}</div>}

      {/* Global controls */}
      <section className="admin-section">
        <h3>Global Chat Controls</h3>
        <div className="actions">
          <button onClick={() => run(() => adminApi.closeAllRooms(), 'All rooms closed')}>
            Close All Rooms
          </button>
          <button onClick={() => run(() => adminApi.openAllRooms(), 'All rooms opened')}>
            Open All Rooms
          </button>
          <button
            className="btn-danger"
            onClick={() => {
              if (!confirm('Reset ALL user accounts? This cannot be undone.')) return;
              run(() => adminApi.resetDatabase(), 'Database reset');
            }}
          >
            Reset Database
          </button>
        </div>
      </section>

      {/* Add Room */}
      <section className="admin-section">
        <h3>Add Room</h3>
        <div className="admin-input-row">
          <input
            type="text"
            placeholder="Room name"
            value={newRoomName}
            onChange={e => setNewRoomName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && newRoomName.trim() && run(
              () => createRoom(newRoomName.trim()),
              `Room "${newRoomName}" created`
            ) && setNewRoomName('')}
          />
          <button
            className="btn-primary"
            disabled={!newRoomName.trim()}
            onClick={() => {
              run(() => createRoom(newRoomName.trim()), `Room "${newRoomName}" created`);
              setNewRoomName('');
            }}
          >
            Create Room
          </button>
        </div>
      </section>

      {/* Promote User */}
      <section className="admin-section">
        <h3>Promote User (all rooms)</h3>
        <div className="admin-input-row">
          <input
            type="text"
            placeholder="Username"
            value={promoteUsername}
            onChange={e => setPromoteUsername(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && promoteUsername.trim() && run(
              () => adminApi.promoteUser(promoteUsername.trim()),
              `${promoteUsername} promoted`
            ) && setPromoteUsername('')}
          />
          <button
            className="btn-primary"
            disabled={!promoteUsername.trim()}
            onClick={() => {
              run(
                () => adminApi.promoteUser(promoteUsername.trim()),
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
      <section className="admin-section">
        <h3>Connected Users ({onlineUsers.length})</h3>
        {onlineUsers.length === 0 ? (
          <p className="section-empty">No users connected</p>
        ) : (
          <div className="admin-users-grid">
            {onlineUsers.map(u => (
              <span key={u} className="admin-user-chip">
                <span className="dot" />
                {u}
              </span>
            ))}
          </div>
        )}
      </section>

      {/* Rooms table */}
      <section className="admin-section">
        <h3>Rooms</h3>
        <table className="admin-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Status</th>
              <th>Users in room</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rooms.map(room => (
              <Fragment key={room.id}>
                <tr className={room.is_active ? '' : 'admin-room-closed'}>
                  <td>{room.id}</td>
                  <td style={{ fontWeight: 500 }}>{room.name}</td>
                  <td>
                    <span className="admin-room-status">
                      <span className={`dot ${room.is_active ? 'open' : 'closed'}`} />
                      {room.is_active ? 'Open' : 'Closed'}
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-secondary)' }}>
                    {(roomUsers[room.id] || []).join(', ') || <span style={{ color: 'var(--text-muted)' }}>&mdash;</span>}
                  </td>
                  <td>
                    <div className="actions">
                      {room.is_active ? (
                        <button
                          className="btn-sm"
                          onClick={() => run(() => adminApi.closeRoom(room.id), `Room "${room.name}" closed`)}
                        >
                          Close
                        </button>
                      ) : (
                        <button
                          className="btn-sm btn-primary"
                          onClick={() => run(() => adminApi.openRoom(room.id), `Room "${room.name}" opened`)}
                        >
                          Open
                        </button>
                      )}
                      <button
                        className="btn-sm"
                        onClick={() => handleLoadRoomFiles(room.id)}
                      >
                        {expandedRoomFiles === room.id ? 'Hide Files' : 'Files'}
                      </button>
                    </div>
                  </td>
                </tr>

                {expandedRoomFiles === room.id && (
                  <tr className="admin-files-row">
                    <td colSpan={5}>
                      {(roomFiles[room.id] || []).length === 0 ? (
                        <p className="admin-no-files">No files in this room</p>
                      ) : (
                        <table className="admin-files-table">
                          <thead>
                            <tr>
                              <th>File</th>
                              <th>Sender</th>
                              <th>Size</th>
                              <th>Uploaded</th>
                              <th></th>
                            </tr>
                          </thead>
                          <tbody>
                            {(roomFiles[room.id] || []).map(f => (
                              <tr key={f.id}>
                                <td>{f.original_name}</td>
                                <td>{f.sender}</td>
                                <td>{formatSize(f.file_size)}</td>
                                <td>{new Date(f.uploaded_at).toLocaleString()}</td>
                                <td>
                                  <a href={getDownloadUrl(f.id)} target="_blank" rel="noreferrer">
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
              </Fragment>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
