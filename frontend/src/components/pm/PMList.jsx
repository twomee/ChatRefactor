// src/components/PMList.jsx

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

export default function PMList({ threads = {}, pmUnread = {}, activePM, onSelectPM, knownOfflineUsers = new Set() }) {
  const usernames = Object.keys(threads);

  return (
    <div>
      <div className="section-title">Direct Messages</div>
      {usernames.length === 0 && (
        <div className="section-empty">No conversations yet</div>
      )}
      {usernames.map(username => {
        const unread = pmUnread[username] || 0;
        const isActive = username === activePM;
        return (
          <div
            key={username}
            className={`pm-item ${isActive ? 'active' : ''}`}
            onClick={() => onSelectPM(username)}
          >
            <div className="pm-avatar" style={{ position: 'relative' }}>
              {getInitials(username)}
              <span
                className={`pm-status-dot ${knownOfflineUsers.has(username) ? 'offline' : 'online'}`}
                style={{ position: 'absolute', bottom: -1, right: -1, width: 8, height: 8, borderRadius: '50%', border: '1.5px solid var(--glass-bg)' }}
              />
            </div>
            <span className="pm-name">{username}</span>
            {unread > 0 && (
              <span className="pm-badge">
                {unread > 99 ? '99+' : unread}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
