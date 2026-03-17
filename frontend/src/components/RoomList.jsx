// src/components/RoomList.jsx
export default function RoomList({ rooms, activeRoomId, onSelect }) {
  return (
    <div style={{ width: 180, borderRight: '1px solid #ccc', padding: 8 }}>
      <h4 style={{ margin: '0 0 8px' }}>Rooms</h4>
      {rooms.map(room => (
        <div
          key={room.id}
          onClick={() => onSelect(room.id)}
          style={{
            padding: '6px 8px',
            cursor: 'pointer',
            background: room.id === activeRoomId ? '#dce8ff' : 'transparent',
            borderRadius: 4,
            marginBottom: 2,
          }}
        >
          # {room.name}
        </div>
      ))}
    </div>
  );
}
