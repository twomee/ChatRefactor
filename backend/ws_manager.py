# ws_manager.py
from fastapi import WebSocket
from typing import Dict, List


class ConnectionManager:
    """
    In-memory state of active WebSocket connections.

    Old equivalent:
      - self._roomlist (Rooms object)  →  self.rooms
      - room._openSockets              →  self.rooms[room_id]
      - self._loggedUserList (Users)   →  self.socket_to_user + self.user_to_socket
    """

    def __init__(self):
        # room_id -> list of active WebSocket connections
        self.rooms: Dict[int, List[WebSocket]] = {}
        # WebSocket -> username
        self.socket_to_user: Dict[WebSocket, str] = {}
        # username -> WebSocket (one connection per user for personal messages)
        self.user_to_socket: Dict[str, WebSocket] = {}
        # room_id -> first socket (for admin succession)
        self.room_join_order: Dict[int, List[str]] = {}

    async def connect(self, websocket: WebSocket, room_id: int, username: str):
        await websocket.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = []
            self.room_join_order[room_id] = []
        self.rooms[room_id].append(websocket)
        self.socket_to_user[websocket] = username
        self.user_to_socket[username] = websocket
        self.room_join_order[room_id].append(username)

    def disconnect(self, websocket: WebSocket, room_id: int):
        username = self.socket_to_user.get(websocket)
        if room_id in self.rooms and websocket in self.rooms[room_id]:
            self.rooms[room_id].remove(websocket)
        if websocket in self.socket_to_user:
            del self.socket_to_user[websocket]
        if username and username in self.user_to_socket:
            del self.user_to_socket[username]
        if username and room_id in self.room_join_order:
            if username in self.room_join_order[room_id]:
                self.room_join_order[room_id].remove(username)

    async def broadcast(self, room_id: int, message: dict, exclude: WebSocket = None):
        """Send to all sockets in a room. Old equivalent: Room.sendToGroup()."""
        for ws in list(self.rooms.get(room_id, [])):
            if ws != exclude:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass

    async def send_personal(self, username: str, message: dict):
        """Send to a specific user. Old equivalent: the private message flow."""
        ws = self.user_to_socket.get(username)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    def get_users_in_room(self, room_id: int) -> List[str]:
        return [self.socket_to_user[ws] for ws in self.rooms.get(room_id, []) if ws in self.socket_to_user]

    def get_admin_successor(self, room_id: int):
        """
        Old code: chatServer logic — when admin leaves, the next user in join order becomes admin.
        Returns the username of the next user, or None if room is empty.
        """
        order = self.room_join_order.get(room_id, [])
        return order[0] if order else None

    def is_user_in_room(self, username: str, room_id: int) -> bool:
        return username in self.get_users_in_room(room_id)


manager = ConnectionManager()  # singleton shared across requests
