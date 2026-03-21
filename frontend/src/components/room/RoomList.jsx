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
  const available = rooms.filter(r => !joinedRooms.has(r.id) && r.is_active);

  return (
    <div>
      {/* YOUR ROOMS */}
      <div>
        <div className="section-title">Your Rooms</div>
        {joined.length === 0 && (
          <div className="section-empty">No rooms joined yet</div>
        )}
        {joined.map(room => {
          const unread = unreadCounts[room.id] || 0;
          const isActive = room.id === activeRoomId;
          return (
            <div
              key={room.id}
              className={`room-item ${isActive ? 'active' : ''}`}
              onClick={() => onSelect(room.id)}
            >
              <span className="room-hash">#</span>
              <span className="room-name">{room.name}</span>
              {unread > 0 && (
                <span className="unread-badge">
                  {unread > 99 ? '99+' : unread}
                </span>
              )}
              <button
                className="room-exit-btn"
                onClick={e => { e.stopPropagation(); onExit(room.id); }}
                title="Exit room"
              >
                &times;
              </button>
            </div>
          );
        })}
      </div>

      {/* AVAILABLE */}
      <div style={{ marginTop: 16 }}>
        <div className="section-title">Available</div>
        {available.length === 0 && (
          <div className="section-empty">No other rooms</div>
        )}
        {available.map(room => (
          <div key={room.id} className="room-item room-item-available">
            <span className="room-hash">#</span>
            <span className="room-name">{room.name}</span>
            <button
              className="room-join-btn"
              onClick={() => onJoin(room.id)}
            >
              Join
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
