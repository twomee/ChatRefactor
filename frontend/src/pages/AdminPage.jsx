// src/pages/AdminPage.jsx
import { Fragment, useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as adminApi from '../services/adminApi';
import { createRoom } from '../services/roomApi';
import { listRoomFiles, downloadFile } from '../services/fileApi';
import { formatSize } from '../utils/formatting';

import { Responsive as ResponsiveGridLayout } from 'react-grid-layout';
import { WidthProvider } from 'react-grid-layout/legacy';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

const Responsive = WidthProvider(ResponsiveGridLayout);

const defaultLayouts = {
  lg: [
    { i: 'global',   x: 0, y: 0,  w: 12, h: 6,  minH: 4  },
    { i: 'add-room', x: 0, y: 6,  w: 12, h: 5,  minH: 4  },
    { i: 'promote',  x: 0, y: 11, w: 12, h: 5,  minH: 4  },
    { i: 'users',    x: 0, y: 16, w: 12, h: 6,  minH: 4  },
    { i: 'rooms',    x: 0, y: 22, w: 12, h: 12, minH: 6  },
  ]
};

const ADMIN_LAYOUT_KEY = 'chatbox-admin-layouts';

function loadAdminLayouts() {
  try {
    const saved = localStorage.getItem(ADMIN_LAYOUT_KEY);
    return saved ? JSON.parse(saved) : defaultLayouts;
  } catch {
    return defaultLayouts;
  }
}

export default function AdminPage() {
  const [rooms, setRooms] = useState([]);
  const [onlineUsers, setOnlineUsers] = useState([]);
  const [roomUsers, setRoomUsers] = useState({});
  const [roomFiles, setRoomFiles] = useState({});
  const [status, setStatus] = useState('');
  const [promoteUsername, setPromoteUsername] = useState('');
  const [newRoomName, setNewRoomName] = useState('');
  const [expandedRoomFiles, setExpandedRoomFiles] = useState(null);
  const [layouts, setLayouts] = useState(loadAdminLayouts);
  const navigate = useNavigate();

  // Add page-active class on mount so the one-shot aurora animation plays,
  // and remove it on unmount so the login page returns to the static gradient.
  useEffect(() => {
    document.body.classList.add('page-active');
    return () => document.body.classList.remove('page-active');
  }, []);

  function handleLayoutChange(_current, allLayouts) {
    setLayouts(allLayouts);
    try { localStorage.setItem(ADMIN_LAYOUT_KEY, JSON.stringify(allLayouts)); } catch { /* storage full */ }
  }

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
    loadData(); // eslint-disable-line react-hooks/set-state-in-effect -- initial data fetch is intentional
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
      {/* Header — mirrors the chat page header: title left, actions right */}
      <div className="admin-header glass-panel" style={{ padding: '0 24px', height: 'var(--header-height)', borderRadius: 'var(--radius-lg)', marginBottom: '24px', flexShrink: 0 }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700 }}>⚙ Admin Panel</h2>
        <div className="chat-header-actions">
          <button onClick={() => navigate('/chat')} className="btn-ghost">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"/>
              <polyline points="12 19 5 12 12 5"/>
            </svg>
            Back to Chat
          </button>
        </div>
      </div>

      {status && <div className="admin-status">{status}</div>}

      {/* Grid Dashboard */}
      <div style={{ flex: 1, padding: '0', overflowY: 'auto' }}>
        <Responsive
          className="layout"
          layouts={layouts}
          onLayoutChange={handleLayoutChange}
          breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
          cols={{ lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }}
          rowHeight={40}
          draggableHandle=".drag-handle"
          margin={[16, 16]}
        >
          {/* Global controls */}
          <div key="global" className="glass-panel">
            <div className="drag-handle">≡ Global Controls</div>
            <section className="admin-section" style={{ flex: 1, overflow: 'auto', border: 'none', background: 'transparent', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '16px 24px' }}>
              <div className="actions" style={{ display: 'flex', flexDirection: 'column', width: '100%', maxWidth: '360px', gap: '12px' }}>
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
          </div>

          {/* Add Room */}
          <div key="add-room" className="glass-panel">
             <div className="drag-handle">≡ Add Room</div>
             <section className="admin-section" style={{ flex: 1, overflow: 'auto', border: 'none', background: 'transparent', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '16px 24px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', width: '100%', maxWidth: '360px', gap: '12px' }}>
                  <input
                    type="text"
                    style={{ width: '100%', padding: '12px 14px', fontSize: '0.95rem' }}
                    placeholder="Room name..."
                    value={newRoomName}
                    onChange={e => setNewRoomName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && newRoomName.trim() && run(
                      () => createRoom(newRoomName.trim()),
                      `Room "${newRoomName}" created`
                    ) && setNewRoomName('')}
                  />
                  <button
                    className="btn-primary"
                    style={{ width: '100%', padding: '12px', fontSize: '0.95rem' }}
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
          </div>

          {/* Promote User */}
          <div key="promote" className="glass-panel">
            <div className="drag-handle">≡ Promote User</div>
            <section className="admin-section" style={{ flex: 1, overflow: 'auto', border: 'none', background: 'transparent', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '16px 24px' }}>
               <div style={{ display: 'flex', flexDirection: 'column', width: '100%', maxWidth: '360px', gap: '12px' }}>
                 <input
                   type="text"
                   style={{ width: '100%', padding: '12px 14px', fontSize: '0.95rem' }}
                   placeholder="Username..."
                   value={promoteUsername}
                   onChange={e => setPromoteUsername(e.target.value)}
                   onKeyDown={e => e.key === 'Enter' && promoteUsername.trim() && run(
                     () => adminApi.promoteUser(promoteUsername.trim()),
                     `${promoteUsername} promoted`
                   ) && setPromoteUsername('')}
                 />
                 <button
                   className="btn-primary"
                   style={{ width: '100%', padding: '12px', fontSize: '0.95rem' }}
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
          </div>

          {/* Connected Users */}
          <div key="users" className="glass-panel">
            <div className="drag-handle">≡ Connected Users ({onlineUsers.length})</div>
            <section className="admin-section" style={{ flex: 1, overflow: 'auto', border: 'none', background: 'transparent', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
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
          </div>

          {/* Rooms table */}
          <div key="rooms" className="glass-panel">
             <div className="drag-handle">≡ Rooms Control</div>
             <section className="admin-section" style={{ flex: 1, overflow: 'visible', overflowY: 'auto', overflowX: 'auto', border: 'none', background: 'transparent' }}>
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
                                      <td>{f.originalName}</td>
                                      <td>{f.senderName}</td>
                                      <td>{formatSize(f.fileSize)}</td>
                                      <td>{new Date(f.uploadedAt).toLocaleString()}</td>
                                      <td>
                                        <a href="#" onClick={(e) => { e.preventDefault(); downloadFile(f.id, f.originalName); }}>
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
        </Responsive>
      </div>
    </div>
  );
}
