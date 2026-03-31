# PM File Sharing & PM Persistence — Design Spec
**Date:** 2026-03-30
**Branch:** feat/pm-files-and-persistence (from feat/pm-fixes)
**Status:** Approved

---

## 1. Overview

Two features added to the PM (Direct Message) system:

1. **PM File Sharing** — users can send files/images inside a DM conversation, mirroring the existing room file-sharing capability.
2. **PM Persistence** — PM conversations survive page refresh and re-login. Thread list restored from localStorage; message content loaded lazily from the backend.

### Privacy model
- Message content is **never stored in localStorage** — only usernames of open conversations.
- The backend history endpoint enforces strict participant-only access (sender or recipient, no admin bypass).
- `UserMessageClear` and `DeletedPMConversation` filters are applied at query time — cleared/deleted history never reappears after refresh.
- **Tech debt:** E2EE (Signal protocol) and Redis cache documented below.

---

## 2. Prerequisite Fix — `recipient_id` in Kafka payload

**File:** `services/chat-service/internal/handler/pm.go`

`pm.go`'s Kafka payload currently omits `recipient_id`. The message-service stores it as `null`, breaking the history query.

**Fix:** add `recipient_id` to the Kafka payload:
```go
kafkaPayload := map[string]interface{}{
    "type":         "private_message",
    "msg_id":       msgID,
    "sender":       senderName,
    "sender_id":    senderID,
    "recipient":    to,
    "recipient_id": recipient.ID,   // ← new
    "text":         req.Content,
    "timestamp":    now.Format(time.RFC3339),
}
```

Update the message-service Kafka consumer to store `recipient_id` when persisting PM messages.

**Known limitation:** existing messages with `null` recipient_id will not appear in the history endpoint. Only messages persisted after this deploy are queryable. Acceptable trade-off — documented here.

---

## 3. Feature 1 — PM File Sharing

### 3.1 Kafka topic

Reuse the existing `file.events` topic — no new topic needed. Extend the event payload with `to`, `recipient_id`, and `is_private` fields:

```json
{
  "file_id": 123,
  "filename": "photo.jpg",
  "size": 45678,
  "from": "alice",
  "to": "bob",
  "recipient_id": 42,
  "room_id": null,
  "is_private": true,
  "timestamp": "2026-03-30T10:00:00Z"
}
```

### 3.2 Backend — file-service

**Prisma schema change** (`services/file-service/prisma/schema.prisma`):
```prisma
model File {
  id           Int      @id @default(autoincrement())
  originalName String
  storedPath   String
  fileSize     Int
  senderId     Int
  senderName   String
  roomId       Int?        // null for PM files
  recipientId  Int?        // set for PM files
  isPrivate    Boolean  @default(false)
  uploadedAt   DateTime @default(now())
}
```

**Upload endpoint** — `POST /files/upload`:
- Accepts `?room_id=X` OR `?recipient=alice` (exactly one required — validated, 400 if both or neither).
- When `recipient` is present: call auth-service to resolve username → `recipientId`; store with `isPrivate=true`, `roomId=null`.
- Kafka event extended with `to`, `recipient_id`, `is_private`.

**Download endpoint** — `GET /files/download/{fileId}`:
- **New authorization check:** if `isPrivate=true`, only `senderId` or `recipientId` may download. Return 403 otherwise.
- This also fixes a pre-existing security gap: room files currently have no membership check (out of scope here, added to tech debt).

### 3.3 Backend — chat-service Kafka consumer

`cmd/server/main.go` file event consumer — add routing:
```go
if isPrivate {
    // PM file: personal delivery to recipient via lobby WS
    manager.SendPersonal(recipientID, wsMsg)
} else {
    // Room file: broadcast to room
    manager.BroadcastToRoom(roomID, wsMsg)
}
```

WS event sent to recipient:
```json
{
  "type": "file_shared",
  "file_id": 123,
  "filename": "photo.jpg",
  "size": 45678,
  "from": "alice",
  "to": "bob",
  "is_private": true,
  "timestamp": "..."
}
```

### 3.4 Frontend

**`fileApi.js`** — new function:
```js
export function uploadPMFile(recipientUsername, file, onProgress) {
  const form = new FormData();
  form.append('file', file);
  return http.post(`/files/upload?recipient=${recipientUsername}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
  });
}
```

**`PMView.jsx`** — add paperclip/attachment button next to the message input. On file select: call `uploadPMFile`, then locally dispatch to PMContext (same self-echo pattern as text PMs — no WS self-echo from server):
```js
pmDispatch({
  type: 'ADD_PM_MESSAGE',
  username: pmState.activePM,
  message: {
    isFile: true, from: user.username, text: res.data.originalName,
    fileId: res.data.id, fileSize: res.data.fileSize,
    isSelf: true, msg_id: `pm-file-${res.data.id}`,
  },
});
```

**`useMultiRoomChat.js`** — extend `file_shared` handler:
```js
case 'file_shared': {
  if (msg.is_private) {
    const otherUser = msg.from === user?.username ? msg.to : msg.from;
    pmDispatch({
      type: 'ADD_PM_MESSAGE', username: otherUser,
      message: {
        isFile: true, from: msg.from, text: msg.filename,
        fileId: msg.file_id, fileSize: msg.size,
        isSelf: false, msg_id: `pm-file-${msg.file_id}`,
      },
    });
  } else {
    // existing room file dispatch (unchanged)
  }
  break;
}
```

**`MessageList.jsx`** — no changes. `renderFileMessage` already works for any message with `isFile: true`.

---

## 4. Feature 2 — PM Persistence

### 4.1 Backend — message-service: auth-service client

Add a lightweight HTTP client in message-service to resolve a username → user_id by calling the auth-service `GET /users/{username}` endpoint. Used only by the PM history endpoint.

### 4.2 Backend — message-service: new endpoint

`GET /messages/pm/history/{username}`

- **Auth:** JWT required → decode `user_id` (current user).
- **Resolve:** call auth-service to get `other_user_id` from `{username}`. Return 404 if user not found.
- **Query:**
```sql
SELECT m.*, r.*
FROM messages m
LEFT JOIN reactions r ON r.message_id = m.message_id
WHERE m.is_private = true
  AND (
    (m.sender_id = :me    AND m.recipient_id = :other)
    OR
    (m.sender_id = :other AND m.recipient_id = :me)
  )
  AND m.is_deleted = false
  AND m.sent_at > :cleared_at   -- UserMessageClear for (me, 'pm', other_user_id), if exists
  AND m.sent_at > :deleted_at   -- DeletedPMConversation for (me, other_user_id), if exists
ORDER BY m.sent_at ASC
LIMIT :limit
```
- **Pagination:** `?limit=50&before=<ISO timestamp>` — `before` adds `AND m.sent_at < :before` for infinite scroll upward.
- **Response:** `MessageWithReactionsResponse[]` — same schema used by room history.

### 4.3 Backend — message-service: DB index (migration)

```sql
CREATE INDEX idx_messages_pm_participants
ON messages (is_private, sender_id, recipient_id)
WHERE is_private = true;
```

Add as a new Alembic migration.

### 4.4 Frontend — storage.js

Three new helpers (same pattern as `getJoinedRooms`):
```js
// Key: chatbox_pm_threads_{username}
// Value: ["alice", "bob"] — usernames only, NO message content
getPMThreadList(username)
savePMThreadList(username, usernames)
addPMThread(currentUsername, partnerUsername)  // idempotent
```

### 4.5 Frontend — PMContext

Add to `initialPMState`:
```js
loadedThreads: {},  // { username: true } — tracks which threads have been fetched
```

New reducer actions:

**`SET_PM_THREAD`** — replaces entire thread (used on history load):
```js
case 'SET_PM_THREAD':
  return { ...state, threads: { ...state.threads, [action.username]: action.messages } };
```

**`MARK_THREAD_LOADED`** — prevents double-fetching:
```js
case 'MARK_THREAD_LOADED':
  return { ...state, loadedThreads: { ...state.loadedThreads, [action.username]: true } };
```

**`INIT_PM_THREAD`** — restores thread key with empty array (sidebar shows conversation without messages):
```js
case 'INIT_PM_THREAD':
  if (state.threads[action.username]) return state; // don't overwrite live messages
  return { ...state, threads: { ...state.threads, [action.username]: [] } };
```

### 4.6 Frontend — pmApi.js

```js
export function getPMHistory(username, { limit = 50, before } = {}) {
  return http.get(`/messages/pm/history/${username}`, {
    params: { limit, ...(before && { before }) },
  });
}
```

### 4.7 Frontend — ChatPage.jsx

**On mount** — restore thread list from localStorage:
```js
useEffect(() => {
  const saved = getPMThreadList(user.username);
  saved.forEach(username => pmDispatch({ type: 'INIT_PM_THREAD', username }));
}, []);
```

**`handleSelectPM`** — lazy-load history on first open:
```js
async function handleSelectPM(username) {
  pmDispatch({ type: 'SET_ACTIVE_PM', username });
  pmDispatch({ type: 'CLEAR_PM_UNREAD', username });
  dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });

  if (!pmState.loadedThreads[username]) {
    try {
      const res = await pmApi.getPMHistory(username);
      pmDispatch({ type: 'SET_PM_THREAD', username, messages: transformPMHistory(res.data) });
      pmDispatch({ type: 'MARK_THREAD_LOADED', username });
    } catch { /* thread stays empty, not a hard failure */ }
  }
}
```

**When new PM arrives via WS** — persist new conversation to localStorage (in `useMultiRoomChat` `private_message` handler):
```js
addPMThread(user.username, otherUser); // idempotent
```

**`transformPMHistory(messages)`** — maps `MessageWithReactionsResponse` from backend to the PMContext message shape:
```js
function transformPMHistory(messages) {
  return messages.map(m => ({
    from: m.sender_name,
    text: m.content,
    msg_id: m.message_id,
    isSelf: m.sender_id === /* current user id — from JWT or context */,
    timestamp: m.sent_at,
    edited_at: m.edited_at,
    is_deleted: m.is_deleted,
    reactions: m.reactions || [],
  }));
}
```

Note: `isSelf` requires knowing the current user's numeric `user_id`. **Required change:** add `user_id` to the login API response in auth-service (`/auth/login`) and store it alongside `username` and `is_global_admin` in `AuthContext`. This is the cleanest approach — avoids JWT parsing on the frontend and makes `user.user_id` available everywhere. `LoginPage.jsx` must be updated to persist `user_id` from the response. `isSelf` then becomes `m.sender_id === user.user_id`.

---

## 5. Testing

### Tests to add

**file-service (TypeScript):**
- Upload with `?recipient=alice` returns 200, stores `isPrivate=true`
- Upload with both `room_id` and `recipient` returns 400
- Upload with neither returns 400
- Download of private file by non-participant returns 403
- Download of private file by sender returns 200
- Download of private file by recipient returns 200
- Kafka event for PM file includes `is_private: true`, `to`, `recipient_id`

**chat-service (Go):**
- Kafka consumer routes `is_private=true` file event to `SendPersonal`, not broadcast
- Kafka consumer routes `is_private=false` file event to `BroadcastToRoom`

**message-service (Python/pytest):**
- `GET /messages/pm/history/{username}` returns 200 with correct messages
- Filters out `is_deleted=true` messages
- Applies `UserMessageClear` filter (messages before `cleared_at` excluded)
- Applies `DeletedPMConversation` filter
- Returns 404 if `{username}` not found in auth-service
- Returns 403 if requester is not a participant
- Pagination: `?before=<timestamp>` returns correct window
- DB index exists on `(is_private, sender_id, recipient_id)`

**frontend (Vitest):**
- `PMContext` reducer: `SET_PM_THREAD`, `MARK_THREAD_LOADED`, `INIT_PM_THREAD` actions
- `handleSelectPM` fetches history when thread not loaded, skips fetch when already loaded
- `useMultiRoomChat` `file_shared` handler routes PM files to `pmDispatch`, room files to `dispatch`
- `PMView` renders attachment button; successful upload dispatches `ADD_PM_MESSAGE`
- `storage.js` helpers: `addPMThread` is idempotent, `getPMThreadList` returns correct list

### Tests to adapt

**auth-service:** existing login tests — verify `user_id` is now present in the login response body.

**message-service:** existing clear/delete filter tests — verify they still pass with the new PM history endpoint using the same filter logic.

**chat-service:** existing PM action tests (`pm_actions_test.go`) — verify `recipient_id` is now present in Kafka payloads.

**frontend:** `ChatPage` tests — update `handleSelectPM` mock expectations to account for lazy history fetch. `AuthContext` tests — verify `user_id` is stored and accessible from `useAuth()`.

### Run all 4 services after implementation

```bash
# frontend
cd frontend && npm test -- --run

# message-service
cd services/message-service && pytest tests/ -v

# chat-service
cd services/chat-service && go test ./...

# file-service
cd services/file-service && npm test
```

All must pass before merging.

---

## 6. Tech Debt

These items are captured here and must be added to the project's tech debt tracker (Jira/Linear):

### TD-1: End-to-End Encryption (E2EE)
- **What:** Encrypt PM content client-side before sending. Server stores ciphertext only.
- **Why:** Currently DB admins or a DB breach exposes plaintext PM content.
- **Scope:** Signal protocol double-ratchet. Requires: key exchange on first contact, client-side encrypt/decrypt, backend stores opaque blobs. Major rewrite of PM send/receive/history pipeline.
- **Prerequisite:** Complete PM persistence feature first (this spec).

### TD-2: Redis Cache for PM History
- **What:** Cache `GET /messages/pm/history/{username}` results in Redis.
- **Why:** Without cache, every page load triggers a DB query per opened conversation. At scale this becomes expensive.
- **Design:** Key `pm_history:{min(uid1,uid2)}_{max(uid1,uid2)}`, TTL 2 min. Invalidated on `ADD_MESSAGE`, `EDIT_MESSAGE`, `DELETE_MESSAGE` events for that pair.
- **Prerequisite:** message-service needs a Redis client added.

### TD-3: Room file download authorization
- **What:** `GET /files/download/{fileId}` has no room-membership check for non-private files.
- **Why:** Any authenticated user can download any room file even if they were never in that room.
- **Scope:** Add membership check via chat-service client or store `roomId` membership at upload time.
