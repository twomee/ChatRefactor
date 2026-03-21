# infrastructure/websocket.py
import asyncio
import json

from fastapi import WebSocket

from core.logging import get_logger

logger = get_logger("ws_manager")


class ConnectionManager:
    """
    In-memory state of active WebSocket connections.
    Redis pub/sub enables cross-worker message relay in multi-process mode.
    """

    def __init__(self):
        # room_id -> list of active WebSocket connections
        self.rooms: dict[int, list[WebSocket]] = {}
        # WebSocket -> username
        self.socket_to_user: dict[WebSocket, str] = {}
        # username -> set of WebSockets (user may be in multiple rooms simultaneously)
        self.user_to_socket: dict[str, set[WebSocket]] = {}
        # room_id -> join order list (for admin succession)
        self.room_join_order: dict[int, list[str]] = {}
        # usernames currently being kicked → count of remaining sockets to process
        self.kicked_users: dict[str, int] = {}
        # users who have logged in via POST /auth/login (independent of WebSocket state)
        self.logged_in_users: set[str] = set()
        # lobby WebSockets — one per user, for push updates + PM delivery
        self.lobby_sockets: dict[WebSocket, str] = {}  # ws -> username
        # Redis pub/sub (lazy-initialized)
        self._redis_available = None

    def _get_redis(self):
        """Lazy-load Redis client, returning None if unavailable."""
        if self._redis_available is False:
            return None
        try:
            from infrastructure.redis import get_redis

            r = get_redis()
            r.ping()
            self._redis_available = True
            return r
        except Exception:
            self._redis_available = False
            logger.warning("redis_unavailable", msg="Falling back to local-only delivery")
            return None

    async def connect(self, websocket: WebSocket, room_id: int, username: str):
        await websocket.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = []
            self.room_join_order[room_id] = []
        self.rooms[room_id].append(websocket)
        self.socket_to_user[websocket] = username
        if username not in self.user_to_socket:
            self.user_to_socket[username] = set()
        self.user_to_socket[username].add(websocket)
        self.room_join_order[room_id].append(username)

    def disconnect(self, websocket: WebSocket, room_id: int):
        username = self.socket_to_user.get(websocket)
        if room_id in self.rooms and websocket in self.rooms[room_id]:
            self.rooms[room_id].remove(websocket)
        if websocket in self.socket_to_user:
            del self.socket_to_user[websocket]
        if username and username in self.user_to_socket:
            self.user_to_socket[username].discard(websocket)
            if not self.user_to_socket[username]:
                del self.user_to_socket[username]
        if username and room_id in self.room_join_order and username in self.room_join_order[room_id]:
                self.room_join_order[room_id].remove(username)

    async def broadcast(self, room_id: int, message: dict, exclude: WebSocket = None):
        """Publish to Redis for cross-worker relay, then deliver locally."""
        r = self._get_redis()
        if r:
            try:
                r.publish(f"room:{room_id}", json.dumps(message))
                return  # subscriber handles local delivery
            except Exception:
                logger.warning("redis_publish_failed", channel=f"room:{room_id}")
        # Fallback: local-only delivery
        await self._local_broadcast_room(room_id, message, exclude)

    async def _local_broadcast_room(self, room_id: int, message: dict, exclude: WebSocket = None):
        """Direct local delivery to all sockets in a room."""
        dead_sockets = []
        for ws in list(self.rooms.get(room_id, [])):
            if ws != exclude:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_sockets.append(ws)
        for ws in dead_sockets:
            logger.debug("ws_send_failed_cleaning_up", room_id=room_id)
            self.disconnect(ws, room_id)

    async def send_personal(self, username: str, message: dict):
        """Send to a specific user across all their active connections."""
        r = self._get_redis()
        if r:
            try:
                r.publish(f"user:{username}", json.dumps(message))
                return
            except Exception:
                logger.warning("redis_publish_failed", channel=f"user:{username}")
        await self._local_send_personal(username, message)

    async def _local_send_personal(self, username: str, message: dict):
        """Direct local delivery to all sockets of a user."""
        dead_sockets = []
        for ws in list(self.user_to_socket.get(username, set())):
            try:
                await ws.send_json(message)
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            logger.debug("ws_send_failed_cleaning_up", username=username)
            if ws in self.lobby_sockets:
                self.disconnect_lobby(ws)
            else:
                # Find the room this socket belongs to
                for rid, sockets in list(self.rooms.items()):
                    if ws in sockets:
                        self.disconnect(ws, rid)
                        break

    def get_users_in_room(self, room_id: int) -> list[str]:
        return [self.socket_to_user[ws] for ws in self.rooms.get(room_id, []) if ws in self.socket_to_user]

    def get_admin_successor(self, room_id: int):
        """When admin leaves, the next user in join order becomes admin."""
        order = self.room_join_order.get(room_id, [])
        return order[0] if order else None

    def is_user_in_room(self, username: str, room_id: int) -> bool:
        return username in self.get_users_in_room(room_id)

    def mark_logged_in(self, username: str):
        self.logged_in_users.add(username)

    def mark_logged_out(self, username: str):
        self.logged_in_users.discard(username)

    def is_user_online(self, username: str) -> bool:
        """Return True if the user has at least one active WebSocket connection."""
        return bool(self.user_to_socket.get(username))

    # ── Lobby connections ──────────────────────────────────────────────

    async def connect_lobby(self, websocket: WebSocket, username: str):
        await websocket.accept()
        self.lobby_sockets[websocket] = username
        if username not in self.user_to_socket:
            self.user_to_socket[username] = set()
        self.user_to_socket[username].add(websocket)

    def disconnect_lobby(self, websocket: WebSocket):
        username = self.lobby_sockets.pop(websocket, None)
        if username and username in self.user_to_socket:
            self.user_to_socket[username].discard(websocket)
            if not self.user_to_socket[username]:
                del self.user_to_socket[username]

    async def broadcast_all(self, message: dict):
        """Send a message to every connected lobby socket."""
        r = self._get_redis()
        if r:
            try:
                r.publish("lobby", json.dumps(message))
                return
            except Exception:
                logger.warning("redis_publish_failed", channel="lobby")
        await self._local_broadcast_lobby(message)

    async def _local_broadcast_lobby(self, message: dict):
        """Direct local delivery to all lobby sockets."""
        dead_sockets = []
        for ws in list(self.lobby_sockets):
            try:
                await ws.send_json(message)
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            logger.debug("ws_send_failed_cleaning_up", target="lobby")
            self.disconnect_lobby(ws)

    # ── Redis subscriber (background task) ─────────────────────────────

    async def start_subscriber(self):
        """Subscribe to Redis channels and relay messages to local WebSockets."""
        import redis.asyncio as aioredis

        from core.config import REDIS_URL

        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.psubscribe("room:*", "lobby", "user:*")
        logger.info("redis_subscriber_started")

        try:
            async for message in pubsub.listen():
                if message["type"] not in ("pmessage",):
                    continue
                try:
                    data = json.loads(message["data"])
                    channel = message.get("channel", "")

                    if channel.startswith("room:"):
                        room_id = int(channel.split(":")[1])
                        await self._local_broadcast_room(room_id, data)
                    elif channel == "lobby":
                        await self._local_broadcast_lobby(data)
                    elif channel.startswith("user:"):
                        username = channel.split(":", 1)[1]
                        await self._local_send_personal(username, data)
                except Exception:
                    logger.warning("redis_relay_error", channel=message.get("channel"))
        except asyncio.CancelledError:
            logger.info("redis_subscriber_stopped")
            await pubsub.punsubscribe()
            await r.aclose()
            raise


manager = ConnectionManager()  # singleton shared across requests
