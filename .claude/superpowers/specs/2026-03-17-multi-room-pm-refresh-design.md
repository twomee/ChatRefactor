# Design: Multi-Room Support, Private Message Threads, and Periodic UI Refresh

**Date:** 2026-03-17
**Project:** cHATBOX (FastAPI + React + SQLite)

---

## Overview

Three interconnected features that make the chat experience feel live and allow users to participate in multiple rooms simultaneously:

1. **Periodic UI refresh** — a 1-second interval that re-syncs room list and online users so the UI adapts to changes without requiring user interaction.
2. **Multi-room support** — users can join multiple rooms at the same time, switch between them in a single pane, and see unread message badges on inactive rooms.
3. **Private message threads** — private messages are surfaced as named conversation threads in the sidebar, with unread badges, replacing the current approach where PMs arrive inline in a room.

---

## Architecture

### Frontend — State

**ChatContext** (extended, not replaced):
- Gains `joinedRooms: Set<roomId>` — the set of rooms the user is currently connected to.
- Gains `unreadCounts: { [roomId]: number }` — count of unread chat messages per room (user messages only, not system messages).
- `joinedRooms` is mirrored to `localStorage` so it survives page refresh.
- Existing state slices (`messages`, `onlineUsers`, `admins`, `mutedUsers`) remain unchanged but now hold data for all joined rooms, not just the active one.

**`state.rooms` is always the complete server room list** — it is populated by `SET_ROOMS` from the periodic `/rooms/` poll and is never scoped to only joined rooms. `EXIT_ROOM` does not touch `state.rooms`. This guarantees room name lookups (e.g., for kick alerts) always work regardless of join state.

**Existing ChatContext reducer actions are all preserved** (`SET_ROOMS`, `SET_ACTIVE_ROOM`, `SET_HISTORY`, `ADD_MESSAGE`, `SET_USERS`, `SET_ADMINS`, `SET_ADMIN`, `SET_MUTED_USERS`, `ADD_MUTED`, `REMOVE_MUTED`). The following new actions are added:

| Action | Payload | Effect |
|---|---|---|
| `JOIN_ROOM` | `{ roomId }` | Adds roomId to `joinedRooms` |
| `EXIT_ROOM` | `{ roomId }` | If roomId is not in `joinedRooms`, no-op (idempotent). Otherwise removes roomId from `joinedRooms`; clears `messages[roomId]`, `onlineUsers[roomId]`, `admins[roomId]`, `mutedUsers[roomId]`, `unreadCounts[roomId]` |

| `INCREMENT_UNREAD` | `{ roomId }` | Increments `unreadCounts[roomId]` by 1 |
| `CLEAR_UNREAD` | `{ roomId }` | Sets `unreadCounts[roomId]` to 0 |

**`activeRoomId` is unchanged:** The existing `activeRoomId` state field and `SET_ACTIVE_ROOM` action are retained as-is. `useMultiRoomChat` reads `activeRoomId` from ChatContext state to decide whether to dispatch `INCREMENT_UNREAD` when a message arrives.

**Unread increment logic:** `INCREMENT_UNREAD` is dispatched from `useMultiRoomChat` when an `ADD_MESSAGE` event arrives for a room that is not the current `activeRoomId`. The check is done in the hook, not in the reducer.

**State cleanup on exit:** When `EXIT_ROOM` is dispatched, the reducer removes all per-room data for that roomId from every state slice. This prevents stale data accumulating over join/exit cycles. `EXIT_ROOM` is idempotent — dispatching it for a roomId that is already absent from `joinedRooms` is a no-op.

**PMContext** (new):
- Holds `threads: { [username]: Message[] }` — in-session PM conversations keyed by the other person's username.
- Holds `pmUnread: { [username]: number }` — unread PM counts per conversation.
- Holds `activePM: string | null` — which PM conversation is currently open.
- Private messages are **not persisted to the database** and are lost on page refresh. This is intentional to preserve user privacy.
- `PMProvider` is mounted inside `ProtectedRoute` in `App.jsx` (i.e., only when the user is authenticated), not at the root level. This prevents the context from initializing for unauthenticated routes like `/login`.

### Frontend — Custom Hook (useMultiRoomChat)

Location: `src/hooks/useMultiRoomChat.js`

Responsibilities:
- Maintains a `Map<roomId, WebSocket>` so multiple rooms stay connected simultaneously.
- Exposes `joinRoom(roomId)` — connects WebSocket, dispatches `JOIN_ROOM`, saves to localStorage.
- Exposes `exitRoom(roomId)` — disconnects WebSocket, dispatches `EXIT_ROOM`, updates localStorage.
- Exposes `exitAllRooms()` — calls `exitRoom` for every roomId in `joinedRooms`. Used by the logout handler.
- Exposes `sendMessage(roomId, payload)` — sends to the correct WebSocket.
- Runs a `setInterval` every 1 second that fetches `/rooms/` and `/rooms/{activeRoomId}/users` (online users for the currently visible room only).
- Dispatches updates to ChatContext and PMContext via their respective dispatch functions.
- On mount, reads `joinedRooms` from localStorage and reconnects WebSockets for any previously joined rooms. If a reconnect is rejected with code `4003` (user already in room — server has not yet processed the prior disconnect), the hook retries once after a 1-second delay. If it fails again, the room is silently removed from `joinedRooms` and localStorage.

**WS message types handled by the hook** (for all connected rooms):
`history`, `user_join`, `user_left`, `message`, `system`, `private_message`, `file_shared`, `kicked`, `muted`, `unmuted`, `new_admin`, `chat_closed`, `error`

**PM deduplication:** Under multi-room a user has one WebSocket per joined room. The backend's `send_personal()` delivers a PM to all sockets for that user, meaning an incoming PM would arrive once per joined room. To prevent duplicate dispatches, the backend adds a `msg_id` (UUID) field to every `private_message` payload. `useMultiRoomChat` keeps a `Set<msg_id>` of recently seen PM IDs (cleared on page unload) and ignores duplicates.

**Kicked event handling:** The existing backend kick closes all sockets for the kicked user across all rooms. On the client, when a `kicked` event arrives: call `exitAllRooms()` (clears all state, closes all WS), switch to the placeholder view, and show a `window.alert` with the message "You were kicked from [room name]". This matches the existing single-room kick behavior and avoids complex state management.

**`LEAVE_ROOM` action is removed from the design** — it was introduced to preserve a kicked-room notice in state, but since the notice is shown via alert this is unnecessary.

**Backend fix required for kick — disconnect handler:** When the backend closes all user sockets as part of a kick, each socket's `WebSocketDisconnect` handler fires for every room the user was in. The existing `kicked_users` set suppresses the "has left" system message but does NOT currently suppress `user_left` broadcasts or admin succession in non-kicked rooms. Two changes are required:

1. Change `kicked_users` from `Set[str]` to `Dict[str, int]` on `ConnectionManager`. When the kick is issued, set `manager.kicked_users[target] = len(target_sockets)` (the count of sockets being closed). Each `WebSocketDisconnect` handler checks `user.username in manager.kicked_users` at the very top of its block. If present, it decrements the counter, removes the entry if the counter reaches zero, and then **returns immediately** — skipping the entire post-disconnect block (mute clearing, admin succession, `user_left` broadcast, and "has left" system message). The existing partial guard at line 274 (which only skips the "has left" message) is replaced by this early return at the top of the `WebSocketDisconnect` block.

2. The `is_user_in_room` check at line 59 must also be updated to allow the connection if the previous socket for that user+room is in the process of being closed (i.e., `user.username in manager.kicked_users`). In practice, since the kick closes and awaits each socket before the new connection attempt, this case is unlikely — but the retry logic in `joinRoom` (see hook section) handles it if it occurs.

**Logout path:** `ChatPage` calls `exitAllRooms()` before calling `logout()`. This closes all open WebSockets cleanly so the backend does not hold orphaned connections.

**Retirement of websocket.js:** The existing `src/api/websocket.js` module-level singleton is deleted. All WebSocket management moves into `useMultiRoomChat`. ChatPage and any other consumers are updated to use the hook exclusively.

ChatPage calls this hook and receives everything it needs. No connection logic lives in ChatPage itself.

### Frontend — Sidebar Layout

The left sidebar is a single scrollable column with three sections:

**YOUR ROOMS**
- Lists rooms the user has joined.
- Each entry shows: room name, unread badge (hidden when count is zero), Exit button.
- Clicking the room name sets it as the active view in the main panel.
- Exit disconnects the WebSocket for that room, dispatches `EXIT_ROOM`, and moves it back to AVAILABLE.
- If a room in YOUR ROOMS disappears from the `/rooms/` poll response (i.e. it was closed or deleted), `useMultiRoomChat` automatically calls `exitRoom(roomId)` for that room and appends a system notice ("This room was closed") to its message list before dispatching `EXIT_ROOM`.

**AVAILABLE**
- Lists rooms the user has not joined.
- Each entry shows: room name, Join button.
- Clicking Join connects the WebSocket and moves the room to YOUR ROOMS.

**PRIVATE MESSAGES**
- Lists one entry per person the user has exchanged private messages with this session.
- Each entry shows: the other person's username and an unread badge.
- Clicking an entry opens that PM conversation in the main panel.
- New entries appear automatically when an incoming PM arrives from someone not yet in the list.

### Frontend — Main Chat Area

The center panel shows exactly one of the following based on what is selected in the sidebar:

- **Room view** — messages list, file upload, and message input. If the room is closed, messaging is disabled and a banner is shown. The right-side user list is visible.
- **PM view** — the private message thread with the selected person, with a message input at the bottom. The right-side user list is hidden in this view.
- **Placeholder** — shown when nothing is selected ("Select a room or conversation to start chatting").

**Unread count behavior:**
- Increments when a new user chat message arrives in a room or PM that is not the currently active view.
- Clears when the user switches to that view. If the messages are already scrolled to the bottom (within 50px of the bottom), the count clears immediately on switch. If the user is scrolled up, the count clears when they scroll to within 50px of the bottom. This logic lives in `MessageList` via an `onScrollToBottom` callback prop.

### Frontend — Starting a Private Message

The user clicks a username in the right-side user list. This opens a PM thread in the sidebar (if one does not already exist) and switches the main panel to that PM conversation.

**Sending a PM to an offline user:** Since PMs are initiated from the user list (which only shows online users), offline sends are not a normal path. However, if the target disconnects between click and send, the backend will send an error WS event to the sender: `{"type": "error", "detail": "User is not online"}`. The frontend displays this as a system notice in the PM thread.

---

## Backend Changes

### New endpoint: GET /rooms/{room_id}/users

Requires JWT authentication (same `Depends(get_current_user)` as all other existing endpoints). Returns the list of online usernames for a given room. Uses the existing `manager.get_users_in_room(room_id)` method on the `ConnectionManager` singleton, which already resolves usernames from the internal `room_join_order` structure — no database query. The ETag is computed as a hash of the sorted usernames list. No server-side cache is needed since the data is already in memory.

```json
{ "users": ["alice", "bob"] }
```

### Server-side caching for GET /rooms/

An in-memory cache stores the result of the rooms DB query with a timestamp. Requests arriving within 1 second of the last query return the cached result. The cache is explicitly invalidated when:
- A room is created
- A room is closed
- A room is reopened

This means in steady state, continuous polling from all clients costs zero DB queries.

### ETags on /rooms/ and /rooms/{id}/users

Both endpoints return an `ETag` header (a hash of the response data). The client sends `If-None-Match` on subsequent requests. If the data has not changed, the server returns `304 Not Modified` with no body, avoiding unnecessary React state updates and re-renders.

- `/rooms/` ETag: hash of the full rooms list JSON.
- `/rooms/{id}/users` ETag: hash of the sorted usernames list.

### Private messages — backend changes

The `private_message` WS payload gains a `msg_id` field (UUID generated server-side) on both the delivery to the target and the echo to the sender. This enables client-side deduplication under multi-room.

The backend's private message handler is updated to send an error event to the sender if `user_to_socket.get(target)` is empty: `{"type": "error", "detail": "User is not online"}`.

### ConnectionManager — type clarification

`ConnectionManager.rooms` is `Dict[int, List[WebSocket]]` (a List, not a Set). `user_to_socket` is `Dict[str, Set[WebSocket]]`. These types are as-is in the existing code and are not changed by this feature.

---

## Data Flow

**Joining a room:**
1. User clicks Join in the sidebar.
2. Dispatch `JOIN_ROOM` immediately → roomId added to `joinedRooms` in state and localStorage. Room moves to YOUR ROOMS in the sidebar.
3. `useMultiRoomChat.joinRoom(roomId)` opens a WebSocket to `/ws/{roomId}`.
4. Server sends `history` → ChatContext `SET_HISTORY`.
5. Server broadcasts `user_join` → ChatContext `SET_USERS`, `SET_ADMINS`, `SET_MUTED_USERS`.

(`JOIN_ROOM` is dispatched before the WebSocket is opened so that any WS events arriving immediately — including `history` and `user_join` — land in tracked state and can be cleaned up by `EXIT_ROOM` if the connection fails.)

**Exiting a room:**
1. User clicks Exit on a room in YOUR ROOMS.
2. `useMultiRoomChat.exitRoom(roomId)` closes the WebSocket.
3. Dispatch `EXIT_ROOM` → all per-room state for that roomId is cleared.
4. Room moves back to AVAILABLE. localStorage updated.
5. If it was the active room, switch to next joined room or placeholder.

**Receiving a message in an inactive room:**
1. WebSocket message of type `message` arrives for a non-active roomId.
2. `useMultiRoomChat` dispatches `ADD_MESSAGE` to ChatContext.
3. `useMultiRoomChat` dispatches `INCREMENT_UNREAD` for that roomId.
4. Sidebar badge updates.

**Receiving a private message:**
1. `private_message` WebSocket event arrives (may arrive on multiple sockets).
2. `useMultiRoomChat` checks `msg_id` against seen-IDs Set. Drops if duplicate.
3. Dispatches to PMContext: add message to thread, increment `pmUnread`.
4. If no thread exists for that sender yet, one is created and appears in PRIVATE MESSAGES.
5. Unread badge appears on the sender's entry.

**Receiving a kicked event:**
1. `kicked` WS event arrives on one or more sockets (backend closes all user sockets for the kicked user).
2. Resolve the room name: look up `msg.room_id` in `state.rooms` (always the complete server room list, never cleared by `EXIT_ROOM`) and store the name in a local variable before any state changes. If the room is not found (edge case: kicked from a room not in the current list), fall back to `"a room"`.
3. Call `exitAllRooms()` — dispatches `EXIT_ROOM` for all joined rooms, clears all per-room state, closes all WS connections.
4. Switch active view to placeholder.
5. Show `window.alert("You were kicked from [room name]")` using the name resolved in step 2.
6. Any duplicate `kicked` events arriving before all sockets close are no-ops (`exitAllRooms` is idempotent via the `EXIT_ROOM` no-op on already-removed rooms).

**Room closed while joined (detected via poll):**
1. Periodic poll fetches `/rooms/` and receives a list that no longer includes a joined roomId.
2. `useMultiRoomChat` calls `exitRoom(roomId)` for the missing room.
3. Appends system notice "This room was closed" to the room's message list before cleanup.
4. Dispatch `EXIT_ROOM`. If it was the active room, switch to next joined room or placeholder.

**Periodic refresh (1-second interval):**
1. Fetch `GET /rooms/` with `If-None-Match` header.
2. If 200 → dispatch `SET_ROOMS`. Check for rooms missing from `joinedRooms` (handled above).
3. If 304 → do nothing.
4. Fetch `GET /rooms/{activeRoomId}/users` with `If-None-Match` (only if a room is active).
5. If 200 → dispatch `SET_USERS` to ChatContext.
6. If 304 → do nothing.

**Logout:**
1. ChatPage calls `exitAllRooms()` → closes all WebSockets cleanly.
2. ChatPage calls `logout()` → clears auth state.
3. Navigate to `/login`.

**Page refresh with localStorage:**
1. On mount, `useMultiRoomChat` reads `joinedRooms` from localStorage.
2. For each roomId, calls `joinRoom(roomId)` to reconnect.
3. Server sends history and user list as normal.

---

## File Changes Summary

| File | Change |
|---|---|
| `frontend/src/hooks/useMultiRoomChat.js` | New — all WS + polling logic |
| `frontend/src/api/websocket.js` | Deleted — replaced by `useMultiRoomChat` |
| `frontend/src/context/ChatContext.jsx` | Add `joinedRooms`, `unreadCounts` state; add `JOIN_ROOM`, `EXIT_ROOM`, `INCREMENT_UNREAD`, `CLEAR_UNREAD` actions; retain all existing actions |
| `frontend/src/context/PMContext.jsx` | New — PM threads, unread counts |
| `frontend/src/App.jsx` | Mount `<PMProvider>` inside `ProtectedRoute` (authenticated routes only) |
| `frontend/src/pages/ChatPage.jsx` | Replace inline logic with hook; call `exitAllRooms()` on logout; add PM view |
| `frontend/src/components/room/RoomList.jsx` | Split into YOUR ROOMS / AVAILABLE sections with Join/Exit buttons |
| `frontend/src/components/chat/MessageList.jsx` | Add `onScrollToBottom` callback prop (fires when within 50px of bottom) |
| `frontend/src/components/room/UserList.jsx` | Click username → open PM thread |
| `frontend/src/components/pm/PMList.jsx` | New — renders PM thread list in sidebar |
| `frontend/src/components/pm/PMView.jsx` | New — renders a PM conversation |
| `backend/routers/rooms.py` | Add `GET /rooms/{id}/users`; add ETag + in-memory cache to `GET /rooms/` |
| `backend/routers/websocket.py` | Add `msg_id` (UUID) to `private_message` payload; error on offline PM target; update disconnect handler to skip all post-disconnect processing (`user_left`, admin succession, mute clearing) when `user.username in manager.kicked_users` |

---

## Out of Scope

- Persisting private messages to DB (deferred for privacy reasons)
- PM between users in different rooms (requires a separate lookup mechanism)
- Changing the kick-affects-all-rooms behavior (intentional current behavior, noted above)
- Push notifications or browser notifications for unread messages
- Read receipts
- Message reactions
