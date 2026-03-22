// src/components/common/ConnectionStatus.jsx — Visual indicator for WebSocket connection state
export default function ConnectionStatus({ status }) {
  if (status === 'connected') return null;

  const isReconnecting = status === 'reconnecting';

  return (
    <div className={`connection-status ${status}`}>
      <span className="connection-dot" />
      <span className="connection-label">
        {isReconnecting ? 'Reconnecting...' : 'Disconnected'}
      </span>
    </div>
  );
}
