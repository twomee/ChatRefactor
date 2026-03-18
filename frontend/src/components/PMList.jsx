// src/components/PMList.jsx
export default function PMList({ threads = {}, pmUnread = {}, activePM, onSelectPM }) {
  const usernames = Object.keys(threads);

  return (
    <div>
      <h4 style={{ margin: '0 0 6px', fontSize: '0.75em', textTransform: 'uppercase', color: '#666', letterSpacing: 1 }}>
        Private Messages
      </h4>
      {usernames.length === 0 && (
        <div style={{ fontSize: '0.8em', color: '#aaa' }}>No conversations yet</div>
      )}
      {usernames.map(username => {
        const unread = pmUnread[username] || 0;
        const isActive = username === activePM;
        return (
          <div
            key={username}
            onClick={() => onSelectPM(username)}
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '4px 6px',
              borderRadius: 4,
              background: isActive ? '#f3e5f5' : 'transparent',
              cursor: 'pointer',
              marginBottom: 2,
            }}
          >
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              @ {username}
            </span>
            {unread > 0 && (
              <span style={{
                background: '#9c27b0', color: '#fff', borderRadius: 10,
                fontSize: '0.7em', padding: '1px 5px', minWidth: 18, textAlign: 'center',
              }}>
                {unread > 99 ? '99+' : unread}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
