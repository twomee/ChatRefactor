// src/components/PMView.jsx
import { useState } from 'react';
import PropTypes from 'prop-types';
import MessageList from '../chat/MessageList';

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

export default function PMView({
  username, messages = [], onScrollToBottom, isOnline = true, currentUser,
  onEditMessage, onDeleteMessage, onAddReaction, onRemoveReaction,
  onClearHistory, highlightMessageId,
}) {
  const [confirmClear, setConfirmClear] = useState(false);

  function handleClearClick() {
    setConfirmClear(true);
  }

  function handleConfirmClear() {
    setConfirmClear(false);
    onClearHistory?.();
  }

  function handleCancelClear() {
    setConfirmClear(false);
  }

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
        {confirmClear ? (
          <div className="clear-history-confirm" data-testid="clear-pm-confirm">
            <span className="clear-history-label">Clear all history?</span>
            <button className="btn-danger-xs" onClick={handleConfirmClear} data-testid="clear-pm-yes">Yes</button>
            <button className="btn-ghost-xs" onClick={handleCancelClear} data-testid="clear-pm-no">Cancel</button>
          </div>
        ) : (
          <button
            className="btn-icon-sm clear-history-btn"
            onClick={handleClearClick}
            title="Clear conversation history"
            data-testid="clear-pm-history"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6l-1 14H6L5 6"/>
              <path d="M10 11v6M14 11v6"/>
              <path d="M9 6V4h6v2"/>
            </svg>
          </button>
        )}
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
      <MessageList
        messages={messages}
        onScrollToBottom={onScrollToBottom}
        currentUser={currentUser}
        onEditMessage={onEditMessage}
        onDeleteMessage={onDeleteMessage}
        onAddReaction={onAddReaction}
        onRemoveReaction={onRemoveReaction}
        highlightMessageId={highlightMessageId}
      />
    </div>
  );
}

PMView.propTypes = {
  username: PropTypes.string,
  messages: PropTypes.array,
  onScrollToBottom: PropTypes.func,
  isOnline: PropTypes.bool,
  currentUser: PropTypes.string,
  onEditMessage: PropTypes.func,
  onDeleteMessage: PropTypes.func,
  onAddReaction: PropTypes.func,
  onRemoveReaction: PropTypes.func,
  onClearHistory: PropTypes.func,
  highlightMessageId: PropTypes.string,
};
