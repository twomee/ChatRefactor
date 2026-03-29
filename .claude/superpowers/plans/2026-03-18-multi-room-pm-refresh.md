# Multi-Room, Private Message Threads, and Periodic Refresh — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-room support (join/exit multiple rooms simultaneously with unread badges), private message conversation threads in the sidebar, and a 1-second periodic refresh that keeps the room list and user list in sync without user interaction.

**Architecture:** A new `useMultiRoomChat` hook owns all WebSocket connections (one per joined room) and the REST polling loop, replacing the current module-level `websocket.js` singleton. `ChatContext` is extended with `joinedRooms` and `unreadCounts`. A new `PMContext` holds in-session private message threads. The backend gains a new `/rooms/{id}/users` endpoint and ETag-based caching on `/rooms/`, plus fixes to the kick disconnect handler and private message payload.

**Tech Stack:** FastAPI + WebSockets (Python), React 18 + Vite, SQLite/SQLAlchemy, native browser WebSocket API, axios for HTTP

**Spec:** `.claude/superpowers/specs/2026-03-17-multi-room-pm-refresh-design.md`

**Run backend tests:** `cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/ -v`

---

## Chunk 1: Backend Changes

### Task 1.1: Fix kicked_users — change Set to Dict and add early-return guard in disconnect handler

**Files:**
- Modify: `backend/infrastructure/websocket.py`
- Modify: `backend/routers/websocket.py`
- Test: `backend/tests/test_websocket.py`

**Context:**
`manager.kicked_users` is currently a `Set[str]`. Under multi-room, kicking a user closes all their sockets. Each socket's `WebSocketDisconnect` handler fires independently. The current code only suppresses the "has left" system message but still broadcasts `user_left` and runs admin succession in every room. We need to: (1) change `kicked_users` to `Dict[str, int]` tracking how many sockets remain, (2) add an early-return at the top of the disconnect handler when the user is being kicked.

- [ ] **Step 1: Write the failing test**

Note: `_room()` returns an `int` (the room id). Use it directly. `_drain(ws, type)` skips messages until one of the given type appears.

Add to `backend/tests/test_websocket.py`:

```python
def test_kick_does_not_broadcast_user_left_in_other_room():
    """When user is kicked from room A while also in room B,
    room B must NOT receive a user_left event."""
    import threading
    room_a_id = _room("kick_test_a")
    room_b_id = _room("kick_test_b")
    admin_token = _login("kick_admin_1")
    victim_token = _login("kick_victim_1")

    with _client_ctx.websocket_connect(f"/ws/{room_a_id}?token={admin_token}") as ws_admin_a, \
         _client_ctx.websocket_connect(f"/ws/{room_a_id}?token={victim_token}") as ws_victim_a, \
         _client_ctx.websocket_connect(f"/ws/{room_b_id}?token={victim_token}") as ws_victim_b:

        # Drain setup messages for ws_admin_a
        ws_admin_a.receive_json()               # history
        _drain(ws_admin_a, "user_join")         # self join
        _drain(ws_admin_a, "system")            # became admin

        # Drain setup messages for ws_victim_a
        ws_victim_a.receive_json()              # history
        _drain(ws_victim_a, "user_join")        # user_join broadcast (both users)

        # ws_admin_a receives victim joining room_a
        _drain(ws_admin_a, "user_join")         # victim joined
        _drain(ws_admin_a, "system")            # "has joined" system msg

        # Drain setup messages for ws_victim_b
        ws_victim_b.receive_json()              # history
        _drain(ws_victim_b, "user_join")        # self join in room_b

        # Admin kicks victim from room_a
        ws_admin_a.send_json({"type": "kick", "target": "kick_victim_1"})

        # Victim receives kicked event on room_a socket
        kicked_msg = _drain(ws_victim_a, "kicked")
        assert kicked_msg["room_id"] == room_a_id

        # Admin receives system message about kick
        _drain(ws_admin_a, "system")

        # Verify room_b receives NO user_left within 0.3 seconds
        received_in_b = []
        done = threading.Event()

        def try_receive():
            try:
                msg = ws_victim_b.receive_json()
                received_in_b.append(msg)
            except Exception:
                pass
            done.set()

        t = threading.Thread(target=try_receive, daemon=True)
        t.start()
        done.wait(timeout=0.3)

        user_left_events = [m for m in received_in_b if m.get("type") == "user_left"]
        assert user_left_events == [], f"room_b should not receive user_left, got: {user_left_events}"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/test_websocket.py::test_kick_does_not_broadcast_user_left_in_other_room -v
```

Expected: FAIL (room_b receives a spurious `user_left` event)

- [ ] **Step 3: Change kicked_users to Dict[str, int] in infrastructure/websocket.py**

In `backend/infrastructure/websocket.py`, change line 26:

```python
# Old:
self.kicked_users: Set[str] = set()

# New:
self.kicked_users: Dict[str, int] = {}
```

Also update the import at the top to include `Dict` (already there). No other changes to infrastructure/websocket.py.

- [ ] **Step 4: Update kick handler in websocket.py to set the count**

In `backend/routers/websocket.py`, in the `elif msg_type == "kick":` block, replace lines 186–193:

```python
# Old:
manager.kicked_users.add(target)
target_sockets = list(manager.user_to_socket.get(target, set()))
for target_ws in target_sockets:
    try:
        await target_ws.send_json({"type": "kicked", "room_id": room_id})
        await target_ws.close()
    except Exception:
        pass

# New:
target_sockets = list(manager.user_to_socket.get(target, set()))
if target_sockets:
    manager.kicked_users[target] = len(target_sockets)
for target_ws in target_sockets:
    try:
        await target_ws.send_json({"type": "kicked", "room_id": room_id})
        await target_ws.close()
    except Exception:
        pass
```

- [ ] **Step 5: Add early-return guard at top of disconnect handler in websocket.py**

In `backend/routers/websocket.py`, replace the entire `except WebSocketDisconnect:` block (lines 245–281):

```python
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)

        # If this user is being kicked, skip ALL post-disconnect processing.
        # Decrement counter; remove entry when last socket is accounted for.
        if user.username in manager.kicked_users:
            manager.kicked_users[user.username] -= 1
            if manager.kicked_users[user.username] <= 0:
                del manager.kicked_users[user.username]
            return  # skip user_left broadcast, admin succession, mute clearing

        # Clear mute if user was muted in this room (user left → mute reset)
        mute_record = db.query(models.MutedUser).filter(
            models.MutedUser.user_id == user.id,
            models.MutedUser.room_id == room_id,
        ).first()
        if mute_record:
            db.delete(mute_record)
            db.commit()
            await manager.broadcast(room_id, {"type": "unmuted", "username": user.username, "room_id": room_id})

        was_admin = room_service.is_admin_in_room(user.username, room_id, db)
        if was_admin:
            await room_service.handle_admin_succession(room_id, user.username, db, manager)

        # Broadcast updated user list with authoritative admins + muted state
        remaining = manager.get_users_in_room(room_id)
        await manager.broadcast(room_id, {
            "type": "user_left",
            "username": user.username,
            "users": remaining,
            "admins": _get_room_admins(room_id, db, remaining),
            "muted": _get_room_muted(room_id, db, remaining),
            "room_id": room_id,
        })
        await manager.broadcast(room_id, {
            "type": "system",
            "text": f"{user.username} has left the room",
            "room_id": room_id,
        })
```

- [ ] **Step 6: Run the test to verify it passes**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/test_websocket.py::test_kick_does_not_broadcast_user_left_in_other_room -v
```

Expected: PASS

- [ ] **Step 7: Run full test suite to make sure nothing is broken**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/ -v
```

Expected: 88 tests PASS (87 existing + 1 new)

- [ ] **Step 8: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add backend/infrastructure/websocket.py backend/routers/websocket.py backend/tests/test_websocket.py
git commit -m "fix: kicked_users Dict + disconnect early-return prevents spurious user_left in other rooms"
```

---

### Task 1.2: Add msg_id to private_message and error on offline PM target

**Files:**
- Modify: `backend/routers/websocket.py`
- Test: `backend/tests/test_websocket.py`

**Context:**
Under multi-room, a PM is delivered to all of the recipient's active sockets. The frontend deduplicates using `msg_id`. We also need to return an error when the target user is offline.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_websocket.py`:

```python
def test_private_message_has_msg_id():
    """Both delivery and echo of a private message must include msg_id."""
    room_id = _room("pm_msgid_room")
    t1 = _login("pm_sender_1")
    t2 = _login("pm_receiver_1")

    with _client_ctx.websocket_connect(f"/ws/{room_id}?token={t1}") as ws1, \
         _client_ctx.websocket_connect(f"/ws/{room_id}?token={t2}") as ws2:

        # Drain setup: ws1 history + self join + became admin
        ws1.receive_json()
        _drain(ws1, "user_join")
        _drain(ws1, "system")

        # Drain setup: ws2 history + user_join broadcast; ws1 gets ws2's join
        ws2.receive_json()
        _drain(ws2, "user_join")
        _drain(ws1, "user_join")
        _drain(ws1, "system")

        ws1.send_json({"type": "private_message", "to": "pm_receiver_1", "text": "hello"})

        # Echo on sender
        echo = ws1.receive_json()
        assert echo["type"] == "private_message"
        assert "msg_id" in echo, "sender echo must have msg_id"

        # Delivery to receiver
        delivery = ws2.receive_json()
        assert delivery["type"] == "private_message"
        assert "msg_id" in delivery, "delivery must have msg_id"

        # Both have the same msg_id
        assert echo["msg_id"] == delivery["msg_id"]


def test_private_message_to_offline_user_returns_error():
    """Sending a PM to a user not connected to any room returns an error event."""
    room_id = _room("pm_offline_room")
    t1 = _login("pm_sender_2")
    _login("pm_offline_user")  # registered but never connected

    with _client_ctx.websocket_connect(f"/ws/{room_id}?token={t1}") as ws1:
        ws1.receive_json()              # history
        _drain(ws1, "user_join")        # self join
        _drain(ws1, "system")           # became admin

        ws1.send_json({"type": "private_message", "to": "pm_offline_user", "text": "hello?"})
        resp = ws1.receive_json()
        assert resp["type"] == "error"
        assert "not online" in resp["detail"].lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/test_websocket.py::test_private_message_has_msg_id tests/test_websocket.py::test_private_message_to_offline_user_returns_error -v
```

Expected: Both FAIL

- [ ] **Step 3: Implement the changes in websocket.py**

At the top of `backend/routers/websocket.py`, add:

```python
import uuid
```

In the `elif msg_type == "private_message":` block, replace from `text = data.get("text", "")` onward:

```python
                text = data.get("text", "")
                if not text.strip():
                    await websocket.send_json({"type": "error", "detail": "Cannot send empty private message"})
                    continue
                # Error if target is not online
                if not manager.user_to_socket.get(target):
                    await websocket.send_json({"type": "error", "detail": "User is not online"})
                    continue
                msg_id = str(uuid.uuid4())
                # Send to target
                await manager.send_personal(target, {
                    "type": "private_message",
                    "from": user.username,
                    "to": target,
                    "text": text,
                    "msg_id": msg_id,
                })
                # Echo to sender so they see their sent message
                await websocket.send_json({
                    "type": "private_message",
                    "from": user.username,
                    "to": target,
                    "text": text,
                    "self": True,
                    "msg_id": msg_id,
                })
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/test_websocket.py::test_private_message_has_msg_id tests/test_websocket.py::test_private_message_to_offline_user_returns_error -v
```

Expected: Both PASS

- [ ] **Step 5: Run full test suite**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/ -v
```

Expected: 90 tests PASS (88 + 2 new)

- [ ] **Step 6: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add backend/routers/websocket.py backend/tests/test_websocket.py
git commit -m "feat: add msg_id to private_message payload and error on offline PM target"
```

---

### Task 1.3: New GET /rooms/{room_id}/users endpoint + ETag caching on GET /rooms/

**Files:**
- Modify: `backend/routers/rooms.py`
- Modify: `backend/routers/admin.py` (to call cache invalidation)
- Test: `backend/tests/test_websocket.py` (users endpoint) and `backend/tests/test_auth.py` (rooms ETag)

**Context:**
The frontend polls `/rooms/` every second. We add: (1) a 1-second server-side cache + ETag on `GET /rooms/` so DB is hit at most once per second across all clients; (2) a new `GET /rooms/{id}/users` endpoint that reads from `ConnectionManager.get_users_in_room()` (no DB query). First check admin.py to understand where room creation/toggling happens so we can invalidate the cache.

- [ ] **Step 1: Read admin.py to understand room toggle endpoints**

```bash
cat /home/ido/Desktop/Chat-Project-Final/backend/routers/admin.py
```

Note which functions create or toggle rooms — those need to call `invalidate_rooms_cache()`.

- [ ] **Step 2: Write failing tests**

Note: `_room()` returns an `int` room id directly. Use it in f-strings without `.id`.

Add to `backend/tests/test_websocket.py` (for the users endpoint):

```python
def test_get_room_users_returns_online_users():
    """GET /rooms/{id}/users returns usernames of connected users."""
    room_id = _room("users_endpoint_room")
    t1 = _login("users_ep_user1")
    t2 = _login("users_ep_user2")

    # No one connected yet
    resp = _client_ctx.get(f"/rooms/{room_id}/users",
                           headers={"Authorization": f"Bearer {t1}"})
    assert resp.status_code == 200
    assert resp.json()["users"] == []

    with _client_ctx.websocket_connect(f"/ws/{room_id}?token={t1}") as ws1, \
         _client_ctx.websocket_connect(f"/ws/{room_id}?token={t2}") as ws2:
        import time; time.sleep(0.1)
        resp2 = _client_ctx.get(f"/rooms/{room_id}/users",
                                headers={"Authorization": f"Bearer {t1}"})
        assert resp2.status_code == 200
        assert set(resp2.json()["users"]) == {"users_ep_user1", "users_ep_user2"}


def test_get_room_users_requires_auth():
    """GET /rooms/{id}/users must return 401 without a token."""
    room_id = _room("users_auth_room")
    resp = _client_ctx.get(f"/rooms/{room_id}/users")
    assert resp.status_code == 401


def test_get_room_users_returns_etag():
    """GET /rooms/{id}/users must return an ETag header."""
    room_id = _room("users_etag_room")
    t1 = _login("users_etag_user")
    resp = _client_ctx.get(f"/rooms/{room_id}/users",
                           headers={"Authorization": f"Bearer {t1}"})
    assert resp.status_code == 200
    assert "etag" in resp.headers


def test_get_rooms_returns_etag():
    """GET /rooms/ must return an ETag header."""
    t1 = _login("rooms_etag_user")
    resp = _client_ctx.get("/rooms/", headers={"Authorization": f"Bearer {t1}"})
    assert resp.status_code == 200
    assert "etag" in resp.headers


def test_get_rooms_304_on_matching_etag():
    """GET /rooms/ with a matching If-None-Match returns 304."""
    from routers.rooms import invalidate_rooms_cache
    invalidate_rooms_cache()  # ensure cache is fresh for this test
    t1 = _login("rooms_304_user")
    resp = _client_ctx.get("/rooms/", headers={"Authorization": f"Bearer {t1}"})
    etag = resp.headers["etag"]
    resp2 = _client_ctx.get("/rooms/",
                             headers={"Authorization": f"Bearer {t1}",
                                      "If-None-Match": etag})
    assert resp2.status_code == 304
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/test_websocket.py::test_get_room_users_returns_online_users tests/test_websocket.py::test_get_room_users_requires_auth tests/test_websocket.py::test_get_room_users_returns_etag tests/test_websocket.py::test_get_rooms_returns_etag tests/test_websocket.py::test_get_rooms_304_on_matching_etag -v
```

Expected: All 5 FAIL

- [ ] **Step 4: Implement changes in rooms.py**

Replace the entire `backend/routers/rooms.py` with:

```python
# routers/rooms.py
import hashlib
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from auth import get_current_user, require_admin
from ws_manager import manager as ws_manager
import models, schemas

router = APIRouter(prefix="/rooms", tags=["rooms"])

# ---------------------------------------------------------------------------
# In-memory cache for GET /rooms/
# ---------------------------------------------------------------------------
_rooms_cache: dict = {"data": None, "etag": None, "ts": 0.0}
CACHE_TTL = 1.0  # seconds


def invalidate_rooms_cache() -> None:
    """Call this whenever a room is created, closed, or reopened."""
    _rooms_cache["ts"] = 0.0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[schemas.RoomResponse])
def list_rooms(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    now = time.time()
    if _rooms_cache["data"] is None or now - _rooms_cache["ts"] > CACHE_TTL:
        rooms = db.query(models.Room).filter(models.Room.is_active == True).all()
        data = [{"id": r.id, "name": r.name, "is_active": r.is_active} for r in rooms]
        etag = hashlib.md5(str(data).encode()).hexdigest()
        _rooms_cache.update({"data": data, "etag": etag, "ts": now})

    etag = _rooms_cache["etag"]
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return JSONResponse(_rooms_cache["data"], headers={"ETag": etag})


@router.post("/", response_model=schemas.RoomResponse, status_code=201)
def create_room(body: schemas.RoomCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(models.Room).filter(models.Room.name == body.name).first():
        raise HTTPException(status_code=409, detail="Room name already exists")
    room = models.Room(name=body.name.strip())
    db.add(room)
    db.commit()
    db.refresh(room)
    invalidate_rooms_cache()
    return room


@router.get("/{room_id}/users")
def get_room_users(
    room_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    users = ws_manager.get_users_in_room(room_id)
    etag = hashlib.md5(",".join(sorted(users)).encode()).hexdigest()
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return JSONResponse({"users": users}, headers={"ETag": etag})
```

- [ ] **Step 5: Import and call invalidate_rooms_cache in admin.py**

There are exactly 4 functions in `backend/routers/admin.py` that change room `is_active`: `close_all_rooms`, `open_all_rooms`, `close_room`, `open_room`.

Add to the top of `backend/routers/admin.py` (after the existing imports):

```python
from routers.rooms import invalidate_rooms_cache
```

Then after each `db.commit()` call in those 4 functions, add `invalidate_rooms_cache()`:

In `close_all_rooms` (currently ends with `return {"message": "All rooms closed"}`):
```python
    db.commit()
    invalidate_rooms_cache()  # ADD THIS LINE
    for room_id, sockets in list(manager.rooms.items()):
```

In `open_all_rooms` (after `db.commit()`):
```python
    db.commit()
    invalidate_rooms_cache()  # ADD THIS LINE
    return {"message": "All rooms opened"}
```

In `close_room` (after `db.commit()`):
```python
    db.commit()
    invalidate_rooms_cache()  # ADD THIS LINE
    await manager.broadcast(...)
```

In `open_room` (after `db.commit()`):
```python
    db.commit()
    invalidate_rooms_cache()  # ADD THIS LINE
    return {"message": f"Room '{room.name}' opened"}
```

- [ ] **Step 6: Run the failing tests**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/test_websocket.py::test_get_room_users_returns_online_users tests/test_websocket.py::test_get_room_users_requires_auth tests/test_websocket.py::test_get_room_users_returns_etag tests/test_websocket.py::test_get_rooms_returns_etag tests/test_websocket.py::test_get_rooms_304_on_matching_etag -v
```

Expected: All 5 PASS

- [ ] **Step 7: Run full test suite**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/ -v
```

Expected: 95 tests PASS (90 + 5 new)

- [ ] **Step 8: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add backend/routers/rooms.py backend/routers/admin.py backend/tests/test_websocket.py
git commit -m "feat: GET /rooms/{id}/users endpoint + ETag caching on GET /rooms/"
```

---

## Chunk 2: Frontend State — ChatContext + PMContext

### Task 2.1: Extend ChatContext with joinedRooms, unreadCounts, and new actions

**Files:**
- Modify: `frontend/src/context/ChatContext.jsx`

**Context:**
`ChatContext` currently holds `rooms`, `activeRoomId`, `messages`, `onlineUsers`, `admins`, `mutedUsers`. We add `joinedRooms` (Set of room IDs the user has joined) and `unreadCounts` (map of roomId→number). All existing actions are preserved. New actions: `JOIN_ROOM`, `EXIT_ROOM` (idempotent, clears per-room data), `INCREMENT_UNREAD`, `CLEAR_UNREAD`.

- [ ] **Step 1: Update ChatContext.jsx**

Replace `frontend/src/context/ChatContext.jsx` with:

```jsx
// src/context/ChatContext.jsx
import { createContext, useContext, useReducer } from 'react';

const ChatContext = createContext(null);

const initialState = {
  rooms: [],           // list of { id, name, is_active } — always the full server list
  activeRoomId: null,
  joinedRooms: new Set(),    // Set<roomId> — rooms with active WS connections
  unreadCounts: {},          // { roomId: number }
  messages: {},        // { roomId: [{ from, text, timestamp, isSystem, isFile, isPrivate }] }
  onlineUsers: {},     // { roomId: [username] }
  admins: {},          // { roomId: [username] }
  mutedUsers: {},      // { roomId: [username] }
};

function chatReducer(state, action) {
  switch (action.type) {

    // ── Existing actions (unchanged) ──────────────────────────────────────
    case 'SET_ROOMS':
      return { ...state, rooms: action.rooms };

    case 'SET_ACTIVE_ROOM':
      return { ...state, activeRoomId: action.roomId };

    case 'SET_HISTORY':
      return {
        ...state,
        messages: { ...state.messages, [action.roomId]: action.messages },
      };

    case 'ADD_MESSAGE': {
      const roomMsgs = state.messages[action.roomId] || [];
      return {
        ...state,
        messages: { ...state.messages, [action.roomId]: [...roomMsgs, action.message] },
      };
    }

    case 'SET_USERS':
      return { ...state, onlineUsers: { ...state.onlineUsers, [action.roomId]: action.users } };

    case 'SET_ADMINS':
      return { ...state, admins: { ...state.admins, [action.roomId]: action.admins } };

    case 'SET_ADMIN':
      return {
        ...state,
        admins: {
          ...state.admins,
          [action.roomId]: [...new Set([...(state.admins[action.roomId] || []), action.username])],
        },
      };

    case 'SET_MUTED_USERS':
      return { ...state, mutedUsers: { ...state.mutedUsers, [action.roomId]: action.muted } };

    case 'ADD_MUTED':
      return {
        ...state,
        mutedUsers: {
          ...state.mutedUsers,
          [action.roomId]: [...(state.mutedUsers[action.roomId] || []), action.username],
        },
      };

    case 'REMOVE_MUTED':
      return {
        ...state,
        mutedUsers: {
          ...state.mutedUsers,
          [action.roomId]: (state.mutedUsers[action.roomId] || []).filter(u => u !== action.username),
        },
      };

    // ── New actions ────────────────────────────────────────────────────────
    case 'JOIN_ROOM': {
      const next = new Set(state.joinedRooms);
      next.add(action.roomId);
      return { ...state, joinedRooms: next };
    }

    case 'EXIT_ROOM': {
      // Idempotent — if room not joined, no-op
      if (!state.joinedRooms.has(action.roomId)) return state;
      const next = new Set(state.joinedRooms);
      next.delete(action.roomId);
      // Deep-clone each slice and remove this roomId's key
      const { [action.roomId]: _m, ...messages } = state.messages;
      const { [action.roomId]: _u, ...onlineUsers } = state.onlineUsers;
      const { [action.roomId]: _a, ...admins } = state.admins;
      const { [action.roomId]: _mu, ...mutedUsers } = state.mutedUsers;
      const { [action.roomId]: _un, ...unreadCounts } = state.unreadCounts;
      return { ...state, joinedRooms: next, messages, onlineUsers, admins, mutedUsers, unreadCounts };
    }

    case 'INCREMENT_UNREAD': {
      const current = state.unreadCounts[action.roomId] || 0;
      return {
        ...state,
        unreadCounts: { ...state.unreadCounts, [action.roomId]: current + 1 },
      };
    }

    case 'CLEAR_UNREAD':
      return {
        ...state,
        unreadCounts: { ...state.unreadCounts, [action.roomId]: 0 },
      };

    default:
      return state;
  }
}

export function ChatProvider({ children }) {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  return (
    <ChatContext.Provider value={{ state, dispatch }}>
      {children}
    </ChatContext.Provider>
  );
}

export const useChat = () => useContext(ChatContext);
```

- [ ] **Step 2: Verify the backend tests still pass (no frontend test runner yet)**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/ -v
```

Expected: All tests still PASS (backend unchanged)

- [ ] **Step 3: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add frontend/src/context/ChatContext.jsx
git commit -m "feat: extend ChatContext with joinedRooms, unreadCounts, JOIN_ROOM, EXIT_ROOM actions"
```

---

### Task 2.2: Create PMContext for in-session private message threads

**Files:**
- Create: `frontend/src/context/PMContext.jsx`
- Modify: `frontend/src/App.jsx`

**Context:**
`PMContext` holds PM conversation threads (in-session only, never persisted to DB). Each thread is keyed by the other user's username. The provider mounts inside `ProtectedRoute` so it only initializes for authenticated routes.

- [ ] **Step 1: Create PMContext.jsx**

Create `frontend/src/context/PMContext.jsx`:

```jsx
// src/context/PMContext.jsx
import { createContext, useContext, useReducer } from 'react';

const PMContext = createContext(null);

const initialPMState = {
  threads: {},    // { username: [{ from, text, isSelf, to, timestamp }] }
  pmUnread: {},   // { username: number }
  activePM: null, // username of currently open PM conversation (or null)
};

function pmReducer(state, action) {
  switch (action.type) {
    case 'ADD_PM_MESSAGE': {
      const existing = state.threads[action.username] || [];
      return {
        ...state,
        threads: {
          ...state.threads,
          [action.username]: [...existing, action.message],
        },
      };
    }

    case 'INCREMENT_PM_UNREAD': {
      const current = state.pmUnread[action.username] || 0;
      return {
        ...state,
        pmUnread: { ...state.pmUnread, [action.username]: current + 1 },
      };
    }

    case 'CLEAR_PM_UNREAD':
      return {
        ...state,
        pmUnread: { ...state.pmUnread, [action.username]: 0 },
      };

    case 'SET_ACTIVE_PM':
      return { ...state, activePM: action.username };

    default:
      return state;
  }
}

export function PMProvider({ children }) {
  const [pmState, pmDispatch] = useReducer(pmReducer, initialPMState);
  return (
    <PMContext.Provider value={{ pmState, pmDispatch }}>
      {children}
    </PMContext.Provider>
  );
}

export const usePM = () => useContext(PMContext);
```

- [ ] **Step 2: Mount PMProvider inside ProtectedRoute in App.jsx**

Replace `frontend/src/App.jsx` with:

```jsx
// src/App.jsx
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ChatProvider } from './context/ChatContext';
import { PMProvider } from './context/PMContext';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import AdminPage from './pages/AdminPage';

// Wraps ALL authenticated routes as a single parent — PMProvider mounts once
// so PM state survives /chat ↔ /admin navigation.
// Unmounts (resetting PM state) when user is redirected to /login on logout.
function AuthenticatedShell() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" />;
  return <PMProvider><Outlet /></PMProvider>;
}

// Admin-only guard (does not re-mount PMProvider)
function AdminGuard({ children }) {
  const { user } = useAuth();
  if (!user?.is_global_admin) return <Navigate to="/chat" />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <ChatProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            {/* Single AuthenticatedShell parent keeps PMProvider alive across /chat and /admin */}
            <Route element={<AuthenticatedShell />}>
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/admin" element={<AdminGuard><AdminPage /></AdminGuard>} />
            </Route>
            <Route path="*" element={<Navigate to="/login" />} />
          </Routes>
        </BrowserRouter>
      </ChatProvider>
    </AuthProvider>
  );
}
```

- [ ] **Step 3: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add frontend/src/context/PMContext.jsx frontend/src/App.jsx
git commit -m "feat: add PMContext for in-session PM threads, mount PMProvider in ProtectedRoute"
```

---

## Chunk 3: useMultiRoomChat Hook

### Task 3.1: Create useMultiRoomChat hook

**Files:**
- Create: `frontend/src/hooks/useMultiRoomChat.js`
- Delete: `frontend/src/api/websocket.js` (after this task — ChatPage still imports it; we delete it in Chunk 5 when ChatPage is rewritten)

**Context:**
This hook replaces `src/api/websocket.js`. It manages a `Map<roomId, WebSocket>`, the 1-second polling interval, all WS message dispatch, localStorage persistence of joined rooms, and PM deduplication via `msg_id`.

Key patterns used:
- `useRef` for mutable values that shouldn't trigger re-renders: socket map, seen PM IDs, ETags, active room ID (for unread increment check), current state reference (for kicked room name lookup)
- `useCallback` with stable dispatch as only dep for `joinRoom`/`exitRoom`/`sendMessage`
- `setInterval` in `useEffect` for the polling loop
- Retry-once on WS close with code 4003 (already-in-room guard)

- [ ] **Step 1: Create the hook directory**

```bash
mkdir -p /home/ido/Desktop/Chat-Project-Final/frontend/src/hooks
```

- [ ] **Step 2: Create useMultiRoomChat.js**

Create `frontend/src/hooks/useMultiRoomChat.js`:

```js
// src/hooks/useMultiRoomChat.js
import { useEffect, useRef, useCallback } from 'react';
import { useChat } from '../context/ChatContext';
import { usePM } from '../context/PMContext';
import { useAuth } from '../context/AuthContext';
import http from '../services/http';

const STORAGE_KEY = 'chatbox_joined_rooms';

export function useMultiRoomChat() {
  const { state, dispatch } = useChat();
  const { pmState, pmDispatch } = usePM();
  const { token } = useAuth();

  // Mutable refs — changes don't need re-renders
  const socketsRef = useRef(new Map());         // roomId -> WebSocket
  const seenMsgIdsRef = useRef(new Set());      // for PM deduplication
  const roomsEtagRef = useRef(null);
  const usersEtagRef = useRef(null);
  const activeRoomIdRef = useRef(state.activeRoomId);
  const stateRef = useRef(state);               // always-current state for callbacks
  const pmStateRef = useRef(pmState);           // always-current pmState for callbacks

  // Keep refs in sync with latest state
  useEffect(() => { activeRoomIdRef.current = state.activeRoomId; }, [state.activeRoomId]);
  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => { pmStateRef.current = pmState; }, [pmState]);
  // Reset users ETag when active room changes — old ETag is invalid for the new room
  useEffect(() => { usersEtagRef.current = null; }, [state.activeRoomId]);

  // ── Message handler (uses refs so it's always current) ─────────────────
  const handleMessage = useCallback((msg, roomId) => {
    switch (msg.type) {
      case 'history':
        dispatch({ type: 'SET_HISTORY', roomId: msg.room_id, messages: msg.messages });
        break;

      case 'user_join':
      case 'user_left':
        dispatch({ type: 'SET_USERS', roomId: msg.room_id, users: msg.users });
        if (msg.admins) dispatch({ type: 'SET_ADMINS', roomId: msg.room_id, admins: msg.admins });
        if (msg.muted !== undefined) dispatch({ type: 'SET_MUTED_USERS', roomId: msg.room_id, muted: msg.muted });
        break;

      case 'system':
        dispatch({ type: 'ADD_MESSAGE', roomId: msg.room_id, message: { isSystem: true, text: msg.text } });
        break;

      case 'message':
        dispatch({ type: 'ADD_MESSAGE', roomId: msg.room_id, message: { from: msg.from, text: msg.text } });
        if (msg.room_id !== activeRoomIdRef.current) {
          dispatch({ type: 'INCREMENT_UNREAD', roomId: msg.room_id });
        }
        break;

      case 'private_message': {
        // Deduplicate using msg_id (arrives on each joined room's socket)
        if (msg.msg_id) {
          if (seenMsgIdsRef.current.has(msg.msg_id)) break;
          seenMsgIdsRef.current.add(msg.msg_id);
        }
        const otherUser = msg.self ? msg.to : msg.from;
        pmDispatch({
          type: 'ADD_PM_MESSAGE',
          username: otherUser,
          message: { from: msg.from, text: msg.text, isSelf: !!msg.self, to: msg.to },
        });
        // Increment unread if this PM thread is not the active one
        if (otherUser !== pmStateRef.current.activePM) {
          pmDispatch({ type: 'INCREMENT_PM_UNREAD', username: otherUser });
        }
        break;
      }

      case 'file_shared':
        dispatch({
          type: 'ADD_MESSAGE',
          roomId: msg.room_id,
          message: { isFile: true, from: msg.from, text: msg.filename, fileId: msg.file_id, fileSize: msg.size },
        });
        if (msg.room_id !== activeRoomIdRef.current) {
          dispatch({ type: 'INCREMENT_UNREAD', roomId: msg.room_id });
        }
        break;

      case 'kicked': {
        const roomName = stateRef.current.rooms.find(r => r.id === msg.room_id)?.name || 'a room';
        // exitAllRooms inline to avoid stale closure (exitAllRoomsRef set below)
        exitAllRoomsRef.current();
        dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });
        window.alert(`You were kicked from ${roomName}`);
        break;
      }

      case 'muted':
        dispatch({ type: 'ADD_MUTED', roomId: msg.room_id, username: msg.username });
        break;

      case 'unmuted':
        dispatch({ type: 'REMOVE_MUTED', roomId: msg.room_id, username: msg.username });
        break;

      case 'new_admin':
        dispatch({ type: 'SET_ADMIN', roomId: msg.room_id, username: msg.username });
        break;

      case 'chat_closed':
        exitRoomRef.current(msg.room_id ?? roomId);
        dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });
        window.alert(msg.detail || 'Room was closed');
        break;

      case 'error':
        window.alert(msg.detail);
        break;

      default:
        break;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch, pmDispatch]);

  // ── Stable refs for functions that call each other ──────────────────────
  const handleMessageRef = useRef(handleMessage);
  useEffect(() => { handleMessageRef.current = handleMessage; }, [handleMessage]);

  const exitRoomRef = useRef(() => {});
  const exitAllRoomsRef = useRef(() => {});

  // ── joinRoom ─────────────────────────────────────────────────────────────
  const joinRoom = useCallback((roomId, isRetry = false) => {
    if (socketsRef.current.has(roomId)) return;

    if (!isRetry) {
      dispatch({ type: 'JOIN_ROOM', roomId });
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      if (!saved.includes(roomId)) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify([...saved, roomId]));
      }
    }

    const ws = new WebSocket(`ws://localhost:8000/ws/${roomId}?token=${token}`);

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      handleMessageRef.current(msg, roomId);
    };

    ws.onclose = (event) => {
      socketsRef.current.delete(roomId);
      if (event.code === 4003 && !isRetry) {
        // Already-in-room: retry once after 1s (server may not have processed prior disconnect)
        setTimeout(() => {
          const saved2 = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
          if (saved2.includes(roomId)) {
            joinRoom(roomId, true);
          }
        }, 1000);
      } else if (event.code === 4003 && isRetry) {
        // Second failure — give up, remove from joined
        dispatch({ type: 'EXIT_ROOM', roomId });
        const saved3 = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
        localStorage.setItem(STORAGE_KEY, JSON.stringify(saved3.filter(id => id !== roomId)));
      }
    };

    socketsRef.current.set(roomId, ws);
  }, [token, dispatch]);

  // ── exitRoom ─────────────────────────────────────────────────────────────
  const exitRoom = useCallback((roomId) => {
    const ws = socketsRef.current.get(roomId);
    if (ws) {
      ws.close();
      socketsRef.current.delete(roomId);
    }
    dispatch({ type: 'EXIT_ROOM', roomId });
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    localStorage.setItem(STORAGE_KEY, JSON.stringify(saved.filter(id => id !== roomId)));
  }, [dispatch]);

  // ── exitAllRooms ──────────────────────────────────────────────────────────
  const exitAllRooms = useCallback(() => {
    [...socketsRef.current.keys()].forEach(roomId => exitRoom(roomId));
  }, [exitRoom]);

  // Keep refs current so handleMessage can call them without stale closure
  useEffect(() => { exitRoomRef.current = exitRoom; }, [exitRoom]);
  useEffect(() => { exitAllRoomsRef.current = exitAllRooms; }, [exitAllRooms]);

  // ── sendMessage ──────────────────────────────────────────────────────────
  const sendMessage = useCallback((roomId, payload) => {
    const ws = socketsRef.current.get(roomId);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }, []);

  // ── Polling loop (1-second interval) ─────────────────────────────────────
  useEffect(() => {
    const poll = async () => {
      try {
        // --- Poll room list ---
        const roomHeaders = roomsEtagRef.current
          ? { 'If-None-Match': roomsEtagRef.current }
          : {};
        const roomRes = await http.get('/rooms/', {
          headers: roomHeaders,
          validateStatus: s => s < 500,
        });

        if (roomRes.status === 200) {
          roomsEtagRef.current = roomRes.headers['etag'] || null;
          dispatch({ type: 'SET_ROOMS', rooms: roomRes.data });

          // Auto-exit any joined rooms that disappeared from the server list.
          // NOTE: We use window.alert rather than an ADD_MESSAGE system notice because
          // React 18 automatic batching merges ADD_MESSAGE + EXIT_ROOM into one render,
          // showing the post-EXIT_ROOM state (messages[roomId] = cleared) — the notice
          // would never be visible. window.alert is the reliable user notification here,
          // consistent with the chat_closed WS handler which also uses window.alert.
          const serverIds = new Set(roomRes.data.map(r => r.id));
          const joined = stateRef.current.joinedRooms;
          joined.forEach(roomId => {
            if (!serverIds.has(roomId)) {
              exitRoomRef.current(roomId);
              if (activeRoomIdRef.current === roomId) {
                // Prefer switching to another joined room; fall back to placeholder
                const nextJoined = [...stateRef.current.joinedRooms].find(id => id !== roomId);
                dispatch({ type: 'SET_ACTIVE_ROOM', roomId: nextJoined ?? null });
              }
              window.alert('A room you were in was closed by the admin.');
            }
          });
        }

        // --- Poll active room users ---
        const activeId = activeRoomIdRef.current;
        if (activeId) {
          const userHeaders = usersEtagRef.current
            ? { 'If-None-Match': usersEtagRef.current }
            : {};
          const userRes = await http.get(`/rooms/${activeId}/users`, {
            headers: userHeaders,
            validateStatus: s => s < 500,
          });
          if (userRes.status === 200) {
            usersEtagRef.current = userRes.headers['etag'] || null;
            dispatch({ type: 'SET_USERS', roomId: activeId, users: userRes.data.users });
          }
        }
      } catch {
        // Silently ignore network errors during polling
      }
    };

    const interval = setInterval(poll, 1000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  // ── Mount: restore joined rooms from localStorage ────────────────────────
  useEffect(() => {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    saved.forEach(roomId => joinRoom(roomId));

    // Cleanup: close all sockets on unmount
    return () => {
      socketsRef.current.forEach(ws => ws.close());
      seenMsgIdsRef.current.clear();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally run once on mount

  return { joinRoom, exitRoom, exitAllRooms, sendMessage };
}
```

- [ ] **Step 3: Verify backend tests still pass**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add frontend/src/hooks/useMultiRoomChat.js
git commit -m "feat: add useMultiRoomChat hook with multi-socket management, polling, PM dedup"
```

---

## Chunk 4: Frontend Components

### Task 4.1: Rewrite RoomList with YOUR ROOMS / AVAILABLE sections and unread badges

**Files:**
- Modify: `frontend/src/components/room/RoomList.jsx`

**Context:**
Currently `RoomList` is a simple flat list. It needs to become two sections. `YOUR ROOMS` shows joined rooms with an unread badge and Exit button. `AVAILABLE` shows unjoin rooms with a Join button. Props: `rooms`, `joinedRooms` (Set), `activeRoomId`, `unreadCounts`, `onJoin`, `onExit`, `onSelect`.

- [ ] **Step 1: Replace RoomList.jsx**

```jsx
// src/components/room/RoomList.jsx
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
```

- [ ] **Step 2: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add frontend/src/components/room/RoomList.jsx
git commit -m "feat: rewrite RoomList with YOUR ROOMS / AVAILABLE sections, unread badges, join/exit buttons"
```

---

### Task 4.2: Add onScrollToBottom callback to MessageList

**Files:**
- Modify: `frontend/src/components/chat/MessageList.jsx`

**Context:**
`MessageList` needs to fire `onScrollToBottom` when the scroll position is within 50px of the bottom. This is used by `ChatPage` to call `dispatch({ type: 'CLEAR_UNREAD' })`.

- [ ] **Step 1: Update MessageList.jsx**

Replace `frontend/src/components/chat/MessageList.jsx` with:

```jsx
// src/components/chat/MessageList.jsx
import { useEffect, useRef, useCallback } from 'react';

const API_BASE = 'http://localhost:8000';

function formatSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function MessageList({ messages, onScrollToBottom }) {
  const endRef = useRef(null);
  const containerRef = useRef(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Fire onScrollToBottom when user scrolls within 50px of the bottom
  const handleScroll = useCallback(() => {
    if (!onScrollToBottom) return;
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom <= 50) {
      onScrollToBottom();
    }
  }, [onScrollToBottom]);

  // Also fire on mount / messages change if already at bottom
  useEffect(() => {
    handleScroll();
  }, [messages, handleScroll]);

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      style={{ flex: 1, overflowY: 'auto', padding: 12 }}
    >
      {(messages || []).map((msg, i) => {
        if (msg.isSystem) {
          return (
            <div key={i} style={{ marginBottom: 4, color: '#888', fontStyle: 'italic', fontSize: '0.85em', textAlign: 'center' }}>
              — {msg.text} —
            </div>
          );
        }
        if (msg.isFile) {
          const token = sessionStorage.getItem('token');
          return (
            <div key={i} style={{ marginBottom: 6 }}>
              <strong>{msg.from}: </strong>
              <a
                href={`${API_BASE}/files/download/${msg.fileId}?token=${token}`}
                target="_blank"
                rel="noreferrer"
                style={{ color: '#1976d2' }}
              >
                📎 {msg.text}
              </a>
              {msg.fileSize ? <span style={{ color: '#999', fontSize: '0.8em' }}> ({formatSize(msg.fileSize)})</span> : null}
            </div>
          );
        }
        if (msg.isPrivate) {
          const label = msg.isSelf ? `[private → ${msg.to}]` : `[private from ${msg.from}]`;
          return (
            <div key={i} style={{ marginBottom: 6, background: '#f3e5f5', borderLeft: '3px solid #9c27b0', padding: '2px 6px', borderRadius: 2 }}>
              <em style={{ color: '#7b1fa2' }}>{label} </em>
              {msg.isSelf ? msg.text : <><strong>{msg.from}: </strong>{msg.text}</>}
            </div>
          );
        }
        return (
          <div key={i} style={{ marginBottom: 6 }}>
            <strong>{msg.from}: </strong>{msg.text}
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add frontend/src/components/chat/MessageList.jsx
git commit -m "feat: add onScrollToBottom callback to MessageList for unread count clearing"
```

---

### Task 4.3: Create PMList component (PM thread list in sidebar)

**Files:**
- Create: `frontend/src/components/pm/PMList.jsx`

**Context:**
`PMList` renders the PRIVATE MESSAGES section of the sidebar. Each entry shows the other user's name and an unread badge. Clicking an entry opens that PM conversation.

- [ ] **Step 1: Create PMList.jsx**

```jsx
// src/components/pm/PMList.jsx
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
```

- [ ] **Step 2: Create PMView.jsx**

Create `frontend/src/components/pm/PMView.jsx`:

```jsx
// src/components/pm/PMView.jsx
import { useState, useEffect, useCallback } from 'react';
import MessageList from '../chat/MessageList';

export default function PMView({ username, messages = [], onSend, onScrollToBottom }) {
  const [text, setText] = useState('');

  function handleSend() {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText('');
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontWeight: 'bold', color: '#7b1fa2' }}>
        💬 Private chat with {username}
      </div>

      {/* Message list */}
      <MessageList messages={messages} onScrollToBottom={onScrollToBottom} />

      {/* Input */}
      <div style={{ display: 'flex', padding: 8, borderTop: '1px solid #ccc', gap: 8 }}>
        <input
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`Message ${username}...`}
          style={{ flex: 1, padding: '6px 10px', borderRadius: 4, border: '1px solid #ccc' }}
        />
        <button
          onClick={handleSend}
          disabled={!text.trim()}
          style={{ padding: '6px 14px', background: '#9c27b0', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add frontend/src/components/pm/PMList.jsx frontend/src/components/pm/PMView.jsx
git commit -m "feat: add PMList sidebar component and PMView conversation component"
```

---

### Task 4.4: Update UserList — click username to open PM thread

**Files:**
- Modify: `frontend/src/components/room/UserList.jsx`

**Context:**
Currently users can only right-click for admin actions. Left-clicking a username (other than yourself) should open a PM thread. Add an `onStartPM` prop. Keep right-click admin context menu unchanged.

- [ ] **Step 1: Update UserList.jsx**

Replace `frontend/src/components/room/UserList.jsx` with:

```jsx
// src/components/room/UserList.jsx
import { useState } from 'react';
import ContextMenu from '../common/ContextMenu';

export default function UserList({
  users,
  admins,
  mutedUsers,
  currentUser,
  isCurrentUserAdmin,
  onKick,
  onMute,
  onUnmute,
  onPromote,
  onStartPM,   // new: called with username when user clicks another user's name
}) {
  const [menu, setMenu] = useState(null); // { x, y, target }

  function handleRightClick(e, username) {
    if (username === currentUser) return;
    if (!isCurrentUserAdmin) return;
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, target: username });
  }

  function handleLeftClick(username) {
    if (username === currentUser) return;
    if (onStartPM) onStartPM(username);
  }

  return (
    <div style={{ width: 160, borderLeft: '1px solid #ccc', padding: 8, overflowY: 'auto' }}>
      <h4 style={{ margin: '0 0 8px' }}>Online ({(users || []).length})</h4>
      {(users || []).map(u => (
        <div
          key={u}
          onClick={() => handleLeftClick(u)}
          onContextMenu={e => handleRightClick(e, u)}
          style={{
            padding: '4px 0',
            cursor: u !== currentUser ? 'pointer' : 'default',
            userSelect: 'none',
          }}
          title={u !== currentUser ? 'Click to send private message' : undefined}
        >
          {(admins || []).includes(u) ? '★ ' : ''}
          {u}
          {(mutedUsers || []).includes(u) ? ' 🔇' : ''}
        </div>
      ))}
      {menu && (
        <ContextMenu
          x={menu.x} y={menu.y} target={menu.target}
          isMuted={(mutedUsers || []).includes(menu.target)}
          isTargetAdmin={(admins || []).includes(menu.target)}
          onKick={onKick}
          onMute={onMute}
          onUnmute={onUnmute}
          onPromote={onPromote}
          onClose={() => setMenu(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add frontend/src/components/room/UserList.jsx
git commit -m "feat: UserList left-click opens PM thread via onStartPM prop"
```

---

## Chunk 5: ChatPage Wiring and Final Integration

### Task 5.1: Rewrite ChatPage to use useMultiRoomChat and wire all components

**Files:**
- Modify: `frontend/src/pages/ChatPage.jsx`
- Delete: `frontend/src/api/websocket.js`

**Context:**
`ChatPage` currently owns all WebSocket logic. After this task: it uses `useMultiRoomChat` for all connection/polling, renders the three-section sidebar (RoomList + PMList), shows the correct view (room / PM / placeholder) based on `activeRoomId` / `activePM`, and calls `exitAllRooms()` on logout.

The PM view (PMView) is shown when `pmState.activePM !== null && state.activeRoomId === null`. Room view is shown when `state.activeRoomId !== null`. Placeholder otherwise.

The right-side `UserList` is only shown in room view (hidden in PM view).

- [ ] **Step 1: Delete websocket.js**

```bash
rm /home/ido/Desktop/Chat-Project-Final/frontend/src/api/websocket.js
```

- [ ] **Step 2: Replace ChatPage.jsx**

Replace `frontend/src/pages/ChatPage.jsx` with:

```jsx
// src/pages/ChatPage.jsx
import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useChat } from '../context/ChatContext';
import { usePM } from '../context/PMContext';
import { useMultiRoomChat } from '../hooks/useMultiRoomChat';
import RoomList from '../components/room/RoomList';
import MessageList from '../components/chat/MessageList';
import MessageInput from '../components/chat/MessageInput';
import UserList from '../components/room/UserList';
import FileUpload from '../components/chat/FileProgress';
import PMList from '../components/pm/PMList';
import PMView from '../components/pm/PMView';

export default function ChatPage() {
  const { user, logout } = useAuth();
  const { state, dispatch } = useChat();
  const { pmState, pmDispatch } = usePM();
  const navigate = useNavigate();

  const { joinRoom, exitRoom, exitAllRooms, sendMessage } = useMultiRoomChat();

  // ── Handlers ─────────────────────────────────────────────────────────────

  function handleJoinRoom(roomId) {
    // Set active room BEFORE opening the WebSocket so that activeRoomIdRef is
    // already correct when the first WS events (history, user_join) arrive —
    // prevents INCREMENT_UNREAD firing against a stale null activeRoomId.
    // NOTE: The localStorage-restore path (on mount) calls joinRoom() on the hook
    // directly — NOT this handler — so SET_ACTIVE_ROOM is never auto-dispatched
    // during restore; the user's last active room is not overwritten.
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId });
    pmDispatch({ type: 'SET_ACTIVE_PM', username: null }); // joining a room shifts focus to it, closing any open PM view
    joinRoom(roomId);
  }

  function handleExitRoom(roomId) {
    // exitRoom() also dispatches EXIT_ROOM internally, clearing all per-room state
    // (messages, onlineUsers, admins, mutedUsers, unreadCounts) for this room.
    exitRoom(roomId);
    if (state.activeRoomId === roomId) {
      // Switch to next joined room or placeholder.
      // state.joinedRooms still contains roomId here (EXIT_ROOM hasn't rendered yet)
      // so we filter it out manually.
      const remaining = [...state.joinedRooms].filter(id => id !== roomId);
      dispatch({ type: 'SET_ACTIVE_ROOM', roomId: remaining[0] ?? null });
      // Clear any open PM view — the room view takes precedence when switching rooms
      pmDispatch({ type: 'SET_ACTIVE_PM', username: null });
    }
  }

  function handleSelectRoom(roomId) {
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId });
    dispatch({ type: 'CLEAR_UNREAD', roomId });
    pmDispatch({ type: 'SET_ACTIVE_PM', username: null });
  }

  function handleSelectPM(username) {
    pmDispatch({ type: 'SET_ACTIVE_PM', username });
    pmDispatch({ type: 'CLEAR_PM_UNREAD', username });
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });
  }

  function handleStartPM(username) {
    pmDispatch({ type: 'SET_ACTIVE_PM', username });
    pmDispatch({ type: 'CLEAR_PM_UNREAD', username });
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });
  }

  function handleSend(text) {
    if (!state.activeRoomId) return;
    sendMessage(state.activeRoomId, { type: 'message', text });
  }

  function handleSendPM(text) {
    if (!pmState.activePM) return;
    // Backend uses a global user_to_socket map (not per-room), so any joined room's
    // socket can deliver the PM to the target regardless of which room they're in.
    const anyRoomId = [...state.joinedRooms][0];
    if (!anyRoomId) {
      window.alert('You must be in a room to send private messages.');
      return;
    }
    sendMessage(anyRoomId, { type: 'private_message', to: pmState.activePM, text });
  }

  function handleKick(target) { sendMessage(state.activeRoomId, { type: 'kick', target }); }
  function handleMute(target) { sendMessage(state.activeRoomId, { type: 'mute', target }); }
  function handleUnmute(target) { sendMessage(state.activeRoomId, { type: 'unmute', target }); }
  function handlePromote(target) { sendMessage(state.activeRoomId, { type: 'promote', target }); }

  function handleLogout() {
    exitAllRooms();
    logout();
    navigate('/login');
  }

  // ── Derived values ────────────────────────────────────────────────────────
  const activeMessages = state.messages[state.activeRoomId] || [];
  const activeUsers = state.onlineUsers[state.activeRoomId] || [];
  const activeAdmins = state.admins[state.activeRoomId] || [];
  const activeMuted = state.mutedUsers[state.activeRoomId] || [];
  const isCurrentUserAdmin = activeAdmins.includes(user?.username);

  const pmMessages = pmState.activePM
    ? (pmState.threads[pmState.activePM] || []).map(m => ({
        isPrivate: true,
        from: m.from,
        text: m.text,
        isSelf: m.isSelf,
        to: m.to,
      }))
    : [];

  // What to show in the main panel
  const showRoom = !!state.activeRoomId;
  const showPM = !showRoom && !!pmState.activePM;

  // Unread clear callbacks
  const handleRoomScrollBottom = useCallback(() => {
    if (state.activeRoomId) dispatch({ type: 'CLEAR_UNREAD', roomId: state.activeRoomId });
  }, [state.activeRoomId, dispatch]);

  const handlePMScrollBottom = useCallback(() => {
    if (pmState.activePM) pmDispatch({ type: 'CLEAR_PM_UNREAD', username: pmState.activePM });
  }, [pmState.activePM, pmDispatch]);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* Header */}
      <div style={{ padding: '8px 16px', borderBottom: '1px solid #ccc', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>cHATBOX</strong>
        <div>
          <span style={{ marginRight: 12 }}>👤 {user?.username}</span>
          {user?.is_global_admin && (
            <button onClick={() => navigate('/admin')} style={{ marginRight: 8 }}>Admin Panel</button>
          )}
          <button onClick={handleLogout}>Logout</button>
        </div>
      </div>

      {/* Main layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Left sidebar */}
        <div style={{ width: 210, borderRight: '1px solid #ccc', padding: 8, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <RoomList
            rooms={state.rooms}
            joinedRooms={state.joinedRooms}
            activeRoomId={state.activeRoomId}
            unreadCounts={state.unreadCounts}
            onJoin={handleJoinRoom}
            onExit={handleExitRoom}
            onSelect={handleSelectRoom}
          />
          <PMList
            threads={pmState.threads}
            pmUnread={pmState.pmUnread}
            activePM={pmState.activePM}
            onSelectPM={handleSelectPM}
          />
        </div>

        {/* Center panel */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          {showRoom && (
            <>
              <MessageList
                messages={activeMessages}
                onScrollToBottom={handleRoomScrollBottom}
              />
              <FileUpload roomId={state.activeRoomId} />
              <MessageInput onSend={handleSend} />
            </>
          )}
          {showPM && (
            <PMView
              username={pmState.activePM}
              messages={pmMessages}
              onSend={handleSendPM}
              onScrollToBottom={handlePMScrollBottom}
            />
          )}
          {!showRoom && !showPM && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: '#999' }}>
              Select a room or conversation to start chatting
            </div>
          )}
        </div>

        {/* Right panel — user list, only in room view */}
        {showRoom && (
          <UserList
            users={activeUsers}
            admins={activeAdmins}
            mutedUsers={activeMuted}
            currentUser={user?.username}
            isCurrentUserAdmin={isCurrentUserAdmin}
            onKick={handleKick}
            onMute={handleMute}
            onUnmute={handleUnmute}
            onPromote={handlePromote}
            onStartPM={handleStartPM}
          />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run backend tests to confirm no backend regressions**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 4: Start the dev servers and verify the app loads**

```bash
# Terminal 1 — backend
cd /home/ido/Desktop/Chat-Project-Final/backend && uvicorn main:app --reload

# Terminal 2 — frontend
cd /home/ido/Desktop/Chat-Project-Final/frontend && npm run dev
```

Open http://localhost:5173. Log in with `ido` / `ido123`. Verify:
- Sidebar shows YOUR ROOMS (empty) and AVAILABLE sections with existing rooms
- Clicking Join on a room moves it to YOUR ROOMS, messages load
- Joining a second room shows both in YOUR ROOMS
- Messages in an inactive room cause an unread badge to appear
- Badge clears on scroll to bottom
- Clicking Exit moves the room back to AVAILABLE
- Clicking a username in the user list opens a PM view
- 1-second poll keeps room list in sync (open AdminPage in another tab and create/close a room — changes appear within 1s)
- Logout disconnects cleanly

- [ ] **Step 5: Commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add frontend/src/pages/ChatPage.jsx
git rm frontend/src/api/websocket.js
git commit -m "feat: rewrite ChatPage with useMultiRoomChat hook, multi-room UI, PM view, clean logout"
```

---

### Task 5.2: Final verification and cleanup

- [ ] **Step 1: Run full backend test suite one final time**

```bash
cd /home/ido/Desktop/Chat-Project-Final/backend && python -m pytest tests/ -v
```

Expected: All tests PASS (≥92 tests including the 5 new ones from backend tasks)

- [ ] **Step 2: Verify no unused imports or dead code**

```bash
cd /home/ido/Desktop/Chat-Project-Final/frontend && grep -r "websocket" src/ --include="*.js" --include="*.jsx"
```

Expected: No references to `src/api/websocket.js` remain

- [ ] **Step 3: Final commit**

```bash
cd /home/ido/Desktop/Chat-Project-Final && git add -A
git commit -m "feat: multi-room support, PM threads, periodic refresh — complete implementation"
```
