// src/components/PMView.jsx
import MessageList from '../chat/MessageList';

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

export default function PMView({ username, messages = [], onScrollToBottom, isOnline = true }) {
  return (
    <div className="pm-view">
      {/* Header */}
      <div className="pm-header">
        <div className="pm-header-avatar">{getInitials(username)}</div>
        <div className="pm-header-info">
          <div className="pm-header-name">{username}</div>
          <div className="pm-status">
            <span className={`pm-status-dot ${isOnline ? 'online' : 'offline'}`} />
            {isOnline ? 'Online' : 'Offline'}
          </div>
        </div>
      </div>

      {/* Offline banner */}
      {!isOnline && (
        <div className="pm-offline-banner">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          {username} is offline — messages will be delivered when they&apos;re back
        </div>
      )}

      {/* Message list */}
      <MessageList messages={messages} onScrollToBottom={onScrollToBottom} />
    </div>
  );
}
