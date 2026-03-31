// src/components/PMList.jsx
import PropTypes from 'prop-types';

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

export default function PMList({ threads = {}, pmUnread = {}, activePM, onSelectPM, onDeletePM }) {
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
            <div className="pm-avatar">{getInitials(username)}</div>
            <span className="pm-name">{username}</span>
            {unread > 0 && (
              <span className="pm-badge">
                {unread > 99 ? '99+' : unread}
              </span>
            )}
            <button
              className="pm-close-btn"
              title="Remove conversation"
              data-testid={`pm-close-${username}`}
              onClick={e => {
                e.stopPropagation();
                onDeletePM?.(username);
              }}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        );
      })}
    </div>
  );
}

PMList.propTypes = {
  threads: PropTypes.object,
  pmUnread: PropTypes.object,
  activePM: PropTypes.string,
  onSelectPM: PropTypes.func,
  onDeletePM: PropTypes.func,
};
