// src/components/RoomList.jsx
export default function RoomList({
  rooms = [],
  joinedRooms = new Set(),
  activeRoomId,
  unreadCounts = {},
  onJoin,
  onExit,
  onSelect,
}) {
  const joined = rooms.filter(r => joinedRooms.has(r.id));
  const available = rooms.filter(r => !joinedRooms.has(r.id));

  return (
    <div style={{ width: 200, borderRight: '1px solid #ccc', padding: 8, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* YOUR ROOMS */}
      <div>
        <h4 style={{ margin: '0 0 6px', fontSize: '0.75em', textTransform: 'uppercase', color: '#666', letterSpacing: 1 }}>
          Your Rooms
        </h4>
        {joined.length === 0 && (
          <div style={{ fontSize: '0.8em', color: '#aaa' }}>No rooms joined yet</div>
        )}
        {joined.map(room => {
          const unread = unreadCounts[room.id] || 0;
          const isActive = room.id === activeRoomId;
          return (
            <div
              key={room.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '4px 6px',
                borderRadius: 4,
                background: isActive ? '#dce8ff' : 'transparent',
                marginBottom: 2,
              }}
            >
              <span
                onClick={() => onSelect(room.id)}
                style={{ flex: 1, cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              >
                # {room.name}
              </span>
              {unread > 0 && (
                <span style={{
                  background: '#e53935', color: '#fff', borderRadius: 10,
                  fontSize: '0.7em', padding: '1px 5px', marginRight: 4, minWidth: 18, textAlign: 'center',
                }}>
                  {unread > 99 ? '99+' : unread}
                </span>
              )}
              <button
                onClick={() => onExit(room.id)}
                title="Exit room"
                style={{ fontSize: '0.7em', padding: '1px 4px', cursor: 'pointer', background: 'transparent', border: '1px solid #ccc', borderRadius: 3 }}
              >
                ✕
              </button>
            </div>
          );
        })}
      </div>

      {/* AVAILABLE */}
      <div>
        <h4 style={{ margin: '0 0 6px', fontSize: '0.75em', textTransform: 'uppercase', color: '#666', letterSpacing: 1 }}>
          Available
        </h4>
        {available.length === 0 && (
          <div style={{ fontSize: '0.8em', color: '#aaa' }}>No other rooms</div>
        )}
        {available.map(room => (
          <div
            key={room.id}
            style={{ display: 'flex', alignItems: 'center', padding: '4px 6px', borderRadius: 4, marginBottom: 2 }}
          >
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#555' }}>
              # {room.name}
            </span>
            <button
              onClick={() => onJoin(room.id)}
              style={{ fontSize: '0.7em', padding: '1px 6px', cursor: 'pointer', background: '#1976d2', color: '#fff', border: 'none', borderRadius: 3 }}
            >
              Join
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
