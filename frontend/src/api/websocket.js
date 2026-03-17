// src/api/websocket.js
const sockets = {}; // room_id -> WebSocket

export function connectToRoom(roomId, token, onMessage) {
  if (sockets[roomId]) return; // already connected

  const ws = new WebSocket(`ws://localhost:8000/ws/${roomId}?token=${token}`);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    onMessage(data);
  };

  ws.onclose = () => {
    delete sockets[roomId];
    onMessage({ type: 'disconnected', room_id: roomId });
  };

  sockets[roomId] = ws;
}

export function sendMessage(roomId, payload) {
  const ws = sockets[roomId];
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  }
}

export function disconnectFromRoom(roomId) {
  if (sockets[roomId]) {
    sockets[roomId].close();
    delete sockets[roomId];
  }
}
