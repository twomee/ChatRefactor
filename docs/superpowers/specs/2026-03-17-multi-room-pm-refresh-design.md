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

**PMContext** (new):
- Holds `threads: { [username]: Message[] }` — in-session PM conversations keyed by the other person's username.
- Holds `pmUnread: { [username]: number }` — unread PM counts per conversation.
- Holds `activePM: string | null` — which PM conversation is currently open.
- Private messages are **not persisted to the database** and are lost on page refresh. This is intentional to preserve user privacy.

### Frontend — Custom Hook (useMultiRoomChat)

Location: `src/hooks/useMultiRoomChat.js`

Responsibilities:
- Maintains a `Map<roomId, WebSocket>` so multiple rooms stay connected simultaneously.
- Exposes `joinRoom(roomId)` — connects WebSocket, adds to joined rooms, saves to localStorage.
- Exposes `exitRoom(roomId)` — disconnects WebSocket, removes from joined rooms, updates localStorage.
- Exposes `sendMessage(roomId, payload)` — sends to the correct WebSocket.
- Runs a `setInterval` every 1 second that fetches `/rooms/` and `/rooms/{activeRoomId}/users` (online users for the currently visible room only).
- Dispatches updates to ChatContext and PMContext via their respective dispatch functions.
- On mount, reads `joinedRooms` from localStorage and reconnects WebSockets for any previously joined rooms.

ChatPage calls this hook and receives everything it needs. No connection logic lives in ChatPage itself.

### Frontend — Sidebar Layout

The left sidebar is a single scrollable column with three sections:

**YOUR ROOMS**
- Lists rooms the user has joined.
- Each entry shows: room name, unread badge (hidden when count is zero), Exit button.
- Clicking the room name sets it as the active view in the main panel.
- Exit disconnects the WebSocket for that room, removes it from YOUR ROOMS, and moves it back to AVAILABLE.

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
- Clears when the user switches to that view **and** scrolls to the bottom of the messages.

### Frontend — Starting a Private Message

The user clicks a username in the right-side user list. This opens a PM thread in the sidebar (if one does not already exist) and switches the main panel to that PM conversation.

---

## Backend Changes

### New endpoint: GET /rooms/{room_id}/users

Returns the list of online usernames for a given room. Reads directly from `ConnectionManager` (in-memory) — no database query.

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

### Private messages — no DB changes

Private messages remain WebSocket-only and are not persisted. The existing `private_message` WebSocket message type is used unchanged.

### Existing WebSocket endpoint — unchanged

The WebSocket endpoint at `/ws/{room_id}` requires no changes. Multiple simultaneous connections from the same user to different rooms are already supported by `ConnectionManager` since it uses `user_to_socket: Dict[str, Set[WebSocket]]`.

---

## Data Flow

**Joining a room:**
1. User clicks Join in the sidebar.
2. `useMultiRoomChat.joinRoom(roomId)` connects a WebSocket to `/ws/{roomId}`.
3. Server sends `history` → ChatContext `SET_HISTORY`.
4. Server broadcasts `user_join` → ChatContext `SET_USERS`, `SET_ADMINS`, `SET_MUTED_USERS`.
5. `joinedRooms` updated in state and localStorage. Room moves to YOUR ROOMS section.

**Receiving a message in an inactive room:**
1. WebSocket message arrives for a non-active roomId.
2. `useMultiRoomChat` dispatches `ADD_MESSAGE` to ChatContext.
3. Since roomId !== activeRoomId, ChatContext increments `unreadCounts[roomId]`.
4. Sidebar badge updates.

**Receiving a private message:**
1. `private_message` WebSocket event arrives.
2. `useMultiRoomChat` dispatches to PMContext: add message to thread, increment `pmUnread`.
3. If no thread exists for that sender yet, one is created and appears in PRIVATE MESSAGES.
4. Unread badge appears on the sender's entry.

**Periodic refresh (1-second interval):**
1. Fetch `GET /rooms/` with `If-None-Match` header.
2. If 200 → dispatch `SET_ROOMS` to ChatContext. Update AVAILABLE / YOUR ROOMS sections.
3. If 304 → do nothing.
4. Fetch `GET /rooms/{activeRoomId}/users` (only if a room is active).
5. Dispatch `SET_USERS` to ChatContext.

**Page refresh with localStorage:**
1. On mount, `useMultiRoomChat` reads `joinedRooms` from localStorage.
2. For each roomId, calls `joinRoom(roomId)` to reconnect.
3. Server sends history and user list as normal.

---

## File Changes Summary

| File | Change |
|---|---|
| `frontend/src/hooks/useMultiRoomChat.js` | New — all WS + polling logic |
| `frontend/src/context/ChatContext.jsx` | Add `joinedRooms`, `unreadCounts` state |
| `frontend/src/context/PMContext.jsx` | New — PM threads, unread counts |
| `frontend/src/pages/ChatPage.jsx` | Replace inline logic with hook, add PM view |
| `frontend/src/components/RoomList.jsx` | Split into YOUR ROOMS / AVAILABLE sections |
| `frontend/src/components/UserList.jsx` | Click username → open PM thread |
| `frontend/src/components/PMList.jsx` | New — renders PM thread list in sidebar |
| `frontend/src/components/PMView.jsx` | New — renders a PM conversation |
| `backend/routers/rooms.py` | Add GET /rooms/{id}/users, add ETag + cache |

---

## Out of Scope

- Persisting private messages to DB (deferred for privacy reasons)
- PM between users in different rooms (requires a separate lookup mechanism)
- Push notifications or browser notifications for unread messages
- Read receipts
- Message reactions
