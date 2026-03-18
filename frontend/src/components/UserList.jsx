// src/components/UserList.jsx
import { useState } from 'react';
import ContextMenu from './ContextMenu';

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

export default function UserList({
  users,
  admins,
  mutedUsers,
  currentUser,
  isCurrentUserAdmin,
  onKick,
  onMute,
  onUnmute,
  onPromote,
  onStartPM,
}) {
  const [menu, setMenu] = useState(null);

  function handleRightClick(e, username) {
    if (username === currentUser) return;
    if (!isCurrentUserAdmin) return;
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, target: username });
  }

  function handleLeftClick(username) {
    if (username === currentUser) return;
    if (onStartPM) onStartPM(username);
  }

  const isAdmin = (u) => (admins || []).includes(u);
  const isMuted = (u) => (mutedUsers || []).includes(u);

  return (
    <div className="user-list-panel">
      <div className="user-list-header">
        <span className="user-list-title">
          Online
          <span className="user-list-count">({(users || []).length})</span>
        </span>
      </div>
      <div className="user-list-content">
        {(users || []).map(u => (
          <div
            key={u}
            className={`user-item ${u === currentUser ? 'is-self' : ''}`}
            onClick={() => handleLeftClick(u)}
            onContextMenu={e => handleRightClick(e, u)}
            title={u !== currentUser ? 'Click to send private message' : undefined}
          >
            <div className="user-item-avatar">
              {getInitials(u)}
              <span className="user-online-dot" />
            </div>
            <div className="user-item-info">
              <div className="user-item-name">{u}</div>
              {isAdmin(u) && <div className="user-item-role">Admin</div>}
              {isMuted(u) && <div className="user-item-role" style={{ color: 'var(--danger)' }}>Muted</div>}
            </div>
            {isAdmin(u) && <span className="user-admin-star" title="Room admin">&#9733;</span>}
            {isMuted(u) && <span className="user-muted-icon" title="Muted">&#128263;</span>}
          </div>
        ))}
      </div>
      {menu && (
        <ContextMenu
          x={menu.x} y={menu.y} target={menu.target}
          isMuted={isMuted(menu.target)}
          isTargetAdmin={isAdmin(menu.target)}
          onKick={onKick}
          onMute={onMute}
          onUnmute={onUnmute}
          onPromote={onPromote}
          onClose={() => setMenu(null)}
        />
      )}
    </div>
  );
}
