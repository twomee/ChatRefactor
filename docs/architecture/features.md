# Feature Design Decisions

How each feature works and why we made the design choices we did. For technology decisions (infrastructure, libraries, architecture), see [overview.md](overview.md).

---

## Table of Contents

1. [Phase 1 Features](#1-phase-1-features--design--technology-choices)
   - [Message Editing](#11-message-editing)
   - [Message Deletion](#12-message-deletion)
   - [Emoji Reactions](#13-emoji-reactions)
   - [Typing Indicators (Room)](#14-typing-indicators-room)
   - [Typing Indicators (PM)](#15-typing-indicators-pm)
   - [Read Position Tracking](#16-read-position-tracking)
   - [Full-Text Message Search](#17-full-text-message-search)
   - [Link Previews](#18-link-previews)
   - [Two-Factor Authentication (2FA)](#19-two-factor-authentication-2fa)
   - [Browser Notifications](#110-browser-notifications)
   - [Online Presence](#111-online-presence)
   - [Technology Choices Per Service](#112-technology-choices-per-service)
2. [Phase 2 Features — PM Files & Persistence](#2-phase-2-features--pm-files--persistence)
   - [PM File Sharing](#21-pm-file-sharing)
   - [PM History Persistence](#22-pm-history-persistence)
   - [PM Sidebar Persistence](#23-pm-sidebar-persistence)
   - [Instant Logout Presence](#24-instant-logout-presence)
3. [Phase 3 Features — UI/UX Improvements Sprint](#3-phase-3-features--uiux-improvements-sprint)
   - [Room Name Display (No # Prefix)](#31-room-name-display-no--prefix)
   - [Email Registration](#32-email-registration)
   - [Edit Email and Password in Settings](#33-edit-email-and-password-in-settings)
   - [Forgot / Reset Password](#34-forgot--reset-password)
   - [Clear Conversation History](#35-clear-conversation-history)
   - [Delete PM Conversation](#36-delete-pm-conversation)
   - [Command Palette Search](#37-command-palette-search)
   - [Settings Page](#38-settings-page)
   - [User Avatar Dropdown](#39-user-avatar-dropdown)
   - [PM Feature Parity](#310-pm-feature-parity)

---

## 1. Phase 1 Features — Design & Technology Choices

Phase 1 adds 10 production features that transform cHATBOX from a basic chat app into a feature-rich communication platform. Each feature was designed with real-time delivery, data consistency, and security in mind.

### 1.1 Message Editing

**What it does:** Users can edit their own sent messages. The edited content is broadcast to all users in the room in real time, and the message displays an "(edited)" badge.

**How it works:**
1. Frontend sends `{ type: "edit_message", msg_id: "uuid", text: "new content" }` via the room WebSocket
2. Chat service validates ownership (only the original sender can edit) by calling the message-service REST API
3. Message-service updates the `content` column and sets `edited_at = NOW()` in PostgreSQL
4. Chat service broadcasts `{ type: "message_edited", msg_id, text, edited_at }` to all room connections
5. Frontend reducer (`EDIT_MESSAGE`) updates the message in-place in the room's message array

**Why this approach over alternatives:**
- **WebSocket for delivery** (not polling): Edits must appear instantly for all users. Polling would add 1-5 seconds of latency.
- **Server-side ownership check** (not client-only): Prevents malicious clients from editing other users' messages.
- **`edited_at` timestamp** (not a boolean): Enables future features like "show edit history" and provides audit trail.

### 1.2 Message Deletion

**What it does:** Users can soft-delete their own messages. The content is replaced with "[deleted]" for all users.

**How it works:**
1. Frontend sends `{ type: "delete_message", msg_id: "uuid" }` via WebSocket
2. Chat service validates ownership via message-service API
3. Message-service sets `is_deleted = true` in PostgreSQL (content is preserved for audit)
4. Broadcast `{ type: "message_deleted", msg_id }` to all room connections
5. Frontend reducer (`DELETE_MESSAGE`) replaces the message text with "[deleted]"

**Why soft-delete over hard-delete:**
- **Audit trail**: Admins or compliance can review deleted content if needed
- **Referential integrity**: Reactions, read positions, and search indexes that reference the message_id remain valid
- **Undo potential**: A future "undo delete" feature is trivial with soft-delete, impossible with hard-delete

### 1.3 Emoji Reactions

**What it does:** Users can react to messages with any emoji. Reactions are displayed as badges below the message with a count. Clicking an existing reaction toggles it.

**How it works:**
1. User clicks the (+) button on a message, selects an emoji from the picker
2. Frontend sends `{ type: "add_reaction", msg_id, emoji }` via WebSocket
3. Chat service calls message-service to persist the reaction in the `reactions` table
4. Unique constraint `(message_id, user_id, emoji)` prevents duplicate reactions
5. Broadcast `{ type: "reaction_added", msg_id, emoji, username }` to all room connections
6. Frontend reducer (`ADD_REACTION`) adds the reaction to the message's reactions array

**Technology choice — emoji-mart:**
- **Why emoji-mart** over native emoji input or custom picker: emoji-mart provides a fully-featured, accessible picker with search, categories, skin tone support, and recent emoji tracking. It renders as a Web Component with shadow DOM, so its styles don't leak into the app. The alternative (native OS emoji keyboards) varies wildly across platforms and can't be programmatically triggered.
- **Why a `reactions` table** over a JSON column: A separate table allows efficient queries like "find all messages I reacted to" and enforces the unique constraint at the database level. JSON columns require application-level validation and are harder to index.

### 1.4 Typing Indicators (Room)

**What it does:** Shows "X is typing..." below the message input when another user is composing a message in a room.

**How it works:**
1. Frontend detects keystrokes in the message input and sends `{ type: "typing" }` via WebSocket (debounced)
2. Chat service uses `BroadcastRoomExcept` to send the typing event to all room connections EXCEPT the sender (no echo)
3. Frontend reducer (`SET_TYPING`) adds the username to the room's `typingUsers` set
4. A 3-second `setTimeout` auto-clears the typing indicator if no new typing events arrive

**Why 3-second auto-clear:** Users often start typing and then stop without sending. Without auto-clear, stale "is typing" indicators would linger until the user refreshes. 3 seconds is the standard in Slack, Discord, and WhatsApp.

**Why `BroadcastRoomExcept`:** Echoing the typing event back to the sender would cause their own UI to show "You are typing..." which is useless and confusing.

### 1.5 Typing Indicators (PM)

**What it does:** Shows "X is typing..." below the message input when the other user is composing a private message.

**How it works:**
1. Frontend detects keystrokes in the PM message input and sends `{ type: "typing_pm", to: "<username>" }` via the **lobby WebSocket** (the always-on `/ws/lobby` connection)
2. The lobby handler in chat-service resolves the recipient's user ID via `GetUserIDByUsername()` (O(n) scan of connected lobby users)
3. Chat service delivers `{ type: "typing_pm", from: "<sender>" }` to the recipient via `SendPersonal` (lobby personal channel)
4. Frontend `onPMTyping` handler dispatches `SET_PM_TYPING` to PMContext, adding the sender to `pmTypingUsers`
5. A 3-second `setTimeout` auto-clears the typing indicator (same pattern as room typing)
6. `ChatPage` renders `<TypingIndicator>` below `<PMView>` when `pmTypingUsers` has an entry for the active PM partner

**Why the lobby WebSocket (not a dedicated PM WebSocket):**
- The lobby connection is already always-on (one per user) for presence and PM delivery. Adding `typing_pm` to it avoids opening a second WebSocket just for typing events. The lobby is the natural channel for all PM-related real-time events.

**Why `GetUserIDByUsername` (O(n) lookup):**
- The lobby maintains an in-memory map of connected users. With hundreds of concurrent users, an O(n) scan takes microseconds. A dedicated username→ID index would add complexity for negligible performance gain.

**Why not echo to sender:**
- Same as room typing — the sender already knows they're typing. The event is only delivered to the recipient.

**Key files:**
- Backend: `services/chat-service/internal/handler/lobby.go` (handles `typing_pm` messages), `services/chat-service/internal/ws/manager_lobby.go` (`GetUserIDByUsername`)
- Frontend: `frontend/src/hooks/useMultiRoomChat.js` (`onPMTyping`, `sendPMTyping`), `frontend/src/context/PMContext.jsx` (`SET_PM_TYPING` reducer), `frontend/src/pages/ChatPage.jsx` (renders indicator)

### 1.6 Read Position Tracking

**What it does:** Tracks the last message each user has read in each room. On reconnect, a "New messages" divider is rendered between old and new messages.

**How it works:**
1. When the user scrolls to the bottom or clicks a message, the frontend sends `{ type: "mark_read", msg_id }` via WebSocket
2. Chat service stores the read position in the `ReadPositionRepository` (backed by Redis or PostgreSQL)
3. On room join, `sendReadPosition` sends the last-read message ID to the client
4. Frontend reducer (`SET_READ_POSITION`) stores the position per room

**Why server-side tracking over localStorage:**
- **Multi-device**: Read positions sync across devices (phone, desktop, tablet)
- **Server authority**: The server can use read positions for unread count badges and notification decisions

### 1.7 Full-Text Message Search

**What it does:** Users can search across all messages with keyword highlighting and room/sender attribution.

**How it works:**
1. Frontend opens the search modal (Search button or Ctrl+K), debounces input (300ms)
2. API call to `GET /messages/search?q=term&limit=20` via Kong
3. Message-service uses PostgreSQL full-text search: `plainto_tsquery` + `tsvector` column with GIN index
4. Results are ranked by `ts_rank` (relevance) then `sent_at` (recency)
5. Frontend highlights matching terms using regex-based text splitting with `<mark>` elements

**Technology choice — PostgreSQL tsvector over Elasticsearch:**
- **Why PostgreSQL FTS**: For a chat app with thousands of messages, PostgreSQL's built-in full-text search is fast enough (sub-100ms for 100K+ messages with GIN index) and requires zero additional infrastructure. Adding Elasticsearch would mean another service to deploy, monitor, and keep in sync.
- **When to upgrade to Elasticsearch**: If the message volume exceeds millions and search latency or advanced features (fuzzy matching, faceted search, auto-complete) become requirements.
- **SQLite fallback**: Tests use SQLite (in-memory). The DAL detects the dialect and falls back to case-insensitive LIKE search, so tests don't need a PostgreSQL instance.

### 1.8 Link Previews

**What it does:** When a message contains a URL, a compact preview card is rendered below the message with the page's title, description, image, and domain name.

**How it works:**
1. `LinkPreview` component extracts the first URL from message text using a regex
2. Calls `GET /messages/link-preview?url=...` via the message-service
3. Message-service fetches the URL, parses OpenGraph meta tags (`og:title`, `og:description`, `og:image`)
4. Results are cached client-side in a module-level `Map` (lives for the SPA session)
5. Preview card renders with safe image URL validation (rejects `javascript:`, `data:` schemes)

**Security — SSRF protection:**
- The message-service validates URLs before fetching: blocks private IP ranges (10.x, 172.16-31.x, 192.168.x), loopback (127.x), link-local (169.254.x), and cloud metadata endpoints (AWS `169.254.169.254`, GCP metadata)
- DNS resolution is checked BEFORE the HTTP request to prevent DNS rebinding attacks
- Only `http://` and `https://` schemes are allowed

**Why client-side caching over server-side:**
- Preview data rarely changes. Caching in a `Map` avoids redundant API calls when scrolling through messages.
- Server-side caching (Redis) would add complexity without significant benefit at current scale.

### 1.9 Two-Factor Authentication (2FA)

**What it does:** Users can enable TOTP-based 2FA from Settings. After enabling, every login requires both password and a 6-digit code from an authenticator app.

**How it works:**
1. User clicks "Enable 2FA" in Settings
2. Auth-service generates a TOTP secret using `pyotp`, encrypts it with AES-256-GCM, stores in PostgreSQL
3. Frontend displays a QR code (generated by the `qrcode` Python library as a data URI) and a manual entry key
4. User scans with Google Authenticator/Authy and enters the 6-digit code to verify
5. Auth-service verifies the code using `pyotp.TOTP(secret).verify(code)` with a 1-window tolerance
6. On success, `is_2fa_enabled = true` and backup codes are generated

**Technology choices:**
- **pyotp** (TOTP): RFC 6238 compliant, widely used, compatible with all major authenticator apps. The alternative (WebAuthn/FIDO2) requires browser support and hardware keys — overkill for a chat app.
- **AES-256-GCM encryption** for secrets: TOTP secrets must be decryptable (not hashed) because the server needs the plaintext to verify codes. AES-256-GCM provides authenticated encryption with a 96-bit nonce.
- **`TOTP_ENCRYPTION_KEY` env var**: The encryption key is never stored in code or config files. It's injected at runtime via environment variable, following 12-factor app principles.

### 1.10 Browser Notifications

**What it does:** Desktop push notifications when another user @mentions you in a message.

**How it works:**
1. On first message, the frontend calls `requestNotificationPermission()` to get browser permission
2. When a `message` WebSocket event arrives with `mentions` containing the current user's username, `sendBrowserNotification` fires
3. Uses the standard `Notification` API (no service worker required for basic notifications)

**Why the Notification API over a push service (FCM/APNs):**
- The Notification API works immediately without server infrastructure. Push services require a push server, registration tokens, and platform-specific setup.
- For a web-only app where users are actively connected via WebSocket, browser notifications are sufficient.

### 1.11 Online Presence

**What it does:** Shows real-time online/offline status for all users across rooms and DMs.

**How it works:**
1. Each user maintains a **lobby WebSocket** connection independent of room connections
2. On connect, `user_online` is broadcast to all lobby connections
3. On last lobby disconnect (full logout), `user_offline` is broadcast
4. Room connections can close without triggering offline (user may just be switching rooms)
5. A 10-second grace period on room disconnect prevents false "left" events during page refreshes
6. `flushPendingLeaves` cancels all grace timers on full logout for instant offline detection

**Why lobby-based presence over heartbeat polling:**
- **Accurate**: WebSocket close events fire immediately when the connection drops. Polling would require waiting for the next heartbeat interval.
- **Decoupled from rooms**: A user can be online without being in any room (e.g. browsing the room list). Lobby presence captures this.
- **Efficient**: One connection per user for presence vs. polling every N seconds from every client.

---

### 1.12 Technology Choices Per Service

Phase 1 introduced new libraries and modules across all four services. Here's why each was chosen over alternatives.

#### Auth Service (Python/FastAPI)

| Library | What it does | Why this over alternatives |
|---------|-------------|---------------------------|
| **pyotp** | Generates and verifies TOTP codes (RFC 6238) | Only TOTP library needed. Lightweight (no dependencies), RFC-compliant, compatible with Google Authenticator, Authy, and 1Password. Alternative: `django-otp` — too heavy, pulls in Django. Alternative: `python-u2f` — FIDO/U2F requires hardware keys, overkill for a chat app. |
| **qrcode** + **Pillow** | Generates QR code images for the TOTP setup flow | `qrcode` is the standard Python QR library. Pillow is needed as the image backend. The QR is rendered as a base64 data URI so the frontend doesn't need a separate image endpoint. Alternative: client-side QR generation (e.g. `qrcode.react`) — would expose the TOTP secret to the browser's JavaScript context before setup is confirmed, slightly widening the attack surface. |
| **cryptography** (Fernet) | Encrypts TOTP secrets at rest with AES-256-GCM | TOTP secrets must be stored encrypted because they need to be decrypted for verification (unlike passwords which are one-way hashed). `cryptography` is the gold standard for Python crypto — maintained by the PyCA team, audited, and used by pip itself. Alternative: `pycryptodome` — also solid but `cryptography` has better API ergonomics. Alternative: storing secrets in a vault (HashiCorp Vault) — adds operational complexity for marginal security gain at this scale. |
| **Alembic** (migrations 003, 004) | Schema migrations for 2FA columns (`totp_secret`, `is_2fa_enabled`, `backup_codes`) | Already used for auth-service migrations. Migration 003 adds the columns, 004 widens `totp_secret` from 32 chars to 256 to accommodate encrypted ciphertext (base64-encoded AES output is longer than the plaintext). |

#### Chat Service (Go)

| Module/Pattern | What it does | Why this over alternatives |
|----------------|-------------|---------------------------|
| **`net/http` Client** (cross-service calls) | Validates edit/delete ownership by calling message-service REST API | The chat-service (Go) calls `PUT /messages/{id}` and `DELETE /messages/{id}` on the message-service (Python) to validate that the requesting user is the original sender. Alternative: duplicate the ownership check in the chat-service's own database — violates the database-per-service pattern and creates a consistency risk. Alternative: Kafka command/response — too slow for synchronous operations where the user is waiting. |
| **`context.WithCancel`** (grace period) | Manages the 10-second reconnect grace period for room disconnects | Each room disconnect creates a cancellable context. If the user reconnects within 10 seconds (page refresh), the context is cancelled and no `user_left` is broadcast. On full logout, `flushPendingLeaves` cancels all pending contexts. Alternative: `time.Timer` — works but `context.WithCancel` + `select` is more idiomatic Go and composes better with the existing context propagation. |
| **`sync.Mutex`** (pendingLeaves map) | Thread-safe access to the map of pending leave timers | Standard Go mutex for protecting shared state accessed by multiple goroutines (one per WebSocket connection). Alternative: channel-based synchronization — would require a central coordinator goroutine, adding complexity without benefit for a simple map. Alternative: `sync.Map` — optimized for read-heavy workloads with stable keys, but pending leaves are write-heavy (added and deleted frequently). |
| **`BroadcastRoomExcept`** (typing) | Sends typing indicators to all room connections except the sender | A new broadcast variant that skips the originating connection. The sender doesn't need to see their own typing indicator. Alternative: broadcast to everyone and filter client-side — wastes bandwidth and requires the frontend to identify and suppress its own events. |
| **`ReadPositionRepository`** (interface) | Abstracts read position storage behind a Go interface | Allows swapping storage backends (PostgreSQL in production, in-memory mock in tests) without changing the handler code. Follows the Dependency Inversion Principle. Alternative: hardcode Redis/PostgreSQL calls in the handler — couples the handler to a specific storage technology and makes testing harder. |

#### Message Service (Python/FastAPI)

| Library/Module | What it does | Why this over alternatives |
|----------------|-------------|---------------------------|
| **PostgreSQL `tsvector` + GIN index** | Full-text search with relevance ranking | Built into PostgreSQL — no additional infrastructure. `plainto_tsquery` handles natural language input, `ts_rank` sorts by relevance. GIN index makes searches O(log n) instead of O(n). Alternative: Elasticsearch — more powerful (fuzzy search, faceted results, auto-suggestions) but requires deploying, syncing, and monitoring a separate cluster. At our message volume (< 1M), PostgreSQL FTS is fast enough. Alternative: `LIKE '%query%'` — no relevance ranking, no stemming (searching "running" won't find "run"), and full table scans on large datasets. |
| **`beautifulsoup4` + `httpx`** | Parses OpenGraph meta tags from URLs for link previews | `beautifulsoup4` is the standard Python HTML parser — battle-tested, handles malformed HTML gracefully. `httpx` is the modern async HTTP client (replaces `requests` for async code). Alternative: `lxml` — faster parsing but requires C dependencies that complicate Docker builds. Alternative: using a headless browser (Puppeteer) — handles JavaScript-rendered pages but is extremely heavy (200MB+ Chrome binary, 2+ seconds per URL). OpenGraph tags are always in the HTML `<head>` so a simple HTML parser is sufficient. |
| **`ipaddress` module** (SSRF protection) | Validates resolved IPs against blocked network ranges | Python's built-in `ipaddress` module provides `ip_address()` and network containment checks (`ip in network`). Used to block private IPs (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback (127.0.0.0/8), link-local (169.254.0.0/16), and cloud metadata (169.254.169.254/32). Alternative: regex-based URL validation — cannot catch DNS rebinding attacks where a public hostname resolves to a private IP. Our approach resolves DNS first, then validates the IP. |
| **`asyncio.get_running_loop()`** | Runs blocking DNS resolution off the event loop | `socket.getaddrinfo` is blocking (can take seconds for DNS timeouts). Running it in an executor (`loop.run_in_executor`) prevents blocking the FastAPI event loop. Alternative: `aiodns` — async DNS library, but adds a dependency for something we only do occasionally (link preview fetches). The executor approach uses Python's built-in capabilities. |
| **`datetime.now(timezone.utc)`** | Timezone-aware timestamps for `edited_at` | Replaced `datetime.utcnow()` which is deprecated in Python 3.12. `datetime.now(timezone.utc)` returns a timezone-aware datetime, avoiding the "naive vs aware" datetime bugs that plague Python applications. |

#### Frontend (React)

| Library/Module | What it does | Why this over alternatives |
|----------------|-------------|---------------------------|
| **emoji-mart** (`@emoji-mart/data` + `@emoji-mart/react`) | Full-featured emoji picker with search, categories, skin tones, and recent emojis | Renders as a Web Component with Shadow DOM — styles are completely isolated from the app's CSS. Provides 1,800+ emojis with native rendering (no sprite sheets). Alternative: `emoji-picker-react` — renders as regular React components (styles can leak), fewer features, less maintained. Alternative: native OS emoji keyboard — can't be triggered programmatically, varies across platforms, and doesn't work on all browsers. |
| **`useReducer`** (ChatContext) | Manages complex chat state (messages, typing, reactions, read positions, presence per room) | Chat state has 15+ fields with cross-cutting updates (e.g. `USER_LEFT_ROOM` updates `onlineUsers` and optionally `admins` and `mutedUsers` simultaneously). `useReducer` centralizes all state transitions in one place, making them predictable and testable. Alternative: `useState` — would require 15+ separate state variables with interleaved `setState` calls, making race conditions likely. Alternative: Redux/Zustand — adds a dependency for something React's built-in `useReducer` handles perfectly at this scale. |
| **`useCallback` + `useRef`** (WebSocket handlers) | Prevents stale closures in WebSocket message handlers | WebSocket `onmessage` callbacks capture variables from their closure scope. Without `useRef`, the callback would use stale values of `dispatch`, `state`, and `user`. The `handleMessageRef` pattern ensures the callback always calls the latest version. Alternative: recreating WebSocket connections when dependencies change — would cause disconnects and missed messages during re-renders. |
| **`Notification` Web API** | Desktop push notifications for @mentions | Built into all modern browsers — zero dependencies. Shows a native OS notification with title and body. Alternative: Firebase Cloud Messaging (FCM) — requires a server-side push infrastructure, service worker registration, and Firebase project setup. For a web-only app where users are connected via WebSocket, the `Notification` API is simpler. Alternative: in-app toast notifications — don't work when the tab is in the background, which is the primary use case for @mention notifications. |
| **`previewCache` (module-level Map)** | Caches link preview API responses for the session duration | A simple `Map` stored outside the component tree. When a user scrolls through messages, URLs that were already previewed don't trigger new API calls. Alternative: React state/context — would cause re-renders across the component tree when the cache updates. Alternative: `localStorage` — preview data is ephemeral (pages change), so persistent caching would serve stale data. Alternative: server-side Redis cache — adds complexity without significant benefit since each user's session is independent. |
| **CSS `var()` tokens** (glassmorphism theme) | Design tokens for the liquid glass UI | All colors, radii, and blur values are defined as CSS custom properties (`--glass-bg`, `--accent`, `--radius-lg`). This enables the entire theme to be changed by modifying ~20 variables. Alternative: CSS-in-JS (styled-components) — adds runtime overhead and a build dependency. Alternative: Tailwind CSS — would require a major refactor and doesn't naturally support the glassmorphism blur effects. |

---

## 2. Phase 2 Features — PM Files & Persistence

### 2.1 PM File Sharing

**What it does:** Users can upload and download files inside direct message conversations. Images are rendered as inline previews; other file types show a download button. Only the sender and recipient can access a private file.

**Key design decisions:**

**Participant-only authorization in the file-service.** The file-service stores `recipientId` and `isPrivate` on each uploaded file. On download, if `isPrivate` is true, the service verifies `currentUserId === senderId || currentUserId === recipientId` and returns 403 otherwise. This enforces privacy at the service boundary — even if someone guesses a file ID, they cannot download it.

**Recipient lookup via auth-service HTTP client.** The upload endpoint accepts `?recipient=username` (a string). The file-service resolves the username to a numeric user ID by calling the auth-service's internal `/auth/users/by-username/{username}` endpoint. This avoids storing usernames in the files database and keeps user identity authoritative in the auth-service. Alternative: accept `?recipient_id=<int>` from the frontend — would require the frontend to know the partner's numeric ID, which it doesn't store. Alternative: a shared users table — violates database-per-service.

**`file_shared` events routed to personal delivery.** When the file-service publishes a `file.uploaded` event with `is_private=true`, the chat-service's Kafka consumer routes it through the lobby's personal delivery channel (`user:<id>`) instead of broadcasting to a room. The frontend's lobby WebSocket handler receives the `file_shared` event and dispatches it to the PM context.

**Token-based download URL for images.** The `renderFileMessage` component constructs an authenticated download URL with `?token=<jwt>` from `sessionStorage` for use as an `<img src>`. This allows the browser's image renderer to load the file inline without a separate JavaScript fetch. The `downloadFile` service function uses the `Authorization: Bearer` header instead (for the download button), which is more secure (token not in browser history). Both are valid for their respective use cases.

---

### 2.2 PM History Persistence

**What it does:** When a user opens a DM conversation for the first time in a session, the full message history is fetched from the server. Subsequent opens in the same session use the in-memory cache.

**Key design decisions:**

**Lazy-load per conversation, not on login.** History is fetched only when a conversation is first opened (`MARK_THREAD_LOADED` prevents re-fetching). Loading all PM history at login would be expensive and unnecessary — most conversations are never opened in a given session.

**Dedicated `GET /messages/pm/history/{username}` endpoint.** The message-service exposes a specific endpoint for PM history rather than reusing the room history endpoint. Room messages and PM messages have different schemas (`room_id` vs `sender_id`/`recipient_id`) and different access patterns. The endpoint uses a dedicated DB index on `(LEAST(sender_id, recipient_id), GREATEST(sender_id, recipient_id), sent_at)` to efficiently query the symmetric sender/recipient pair without a full table scan.

**`transformPMHistory` maps server schema to frontend schema.** Server returns `sender_name`, `message_id`, `is_file`, `file_id`; frontend uses `from`, `msg_id`, `isFile`, `fileId`. The transform runs once on load and produces the same shape as messages received via WebSocket, so the rest of the rendering pipeline handles both identically.

---

### 2.3 PM Sidebar Persistence

**What it does:** The list of DM conversations (the sidebar) is preserved across page reloads using `localStorage`. Only the list of usernames is stored — not message content.

**Key design decisions:**

**Two-layer storage: in-memory threads + localStorage username list.** `PMContext` holds the full thread state in memory (`{ username: [messages] }`). `localStorage` holds only `chatbox_pm_threads_<currentUser>` — a flat array of partner usernames. On reload, the app reads `localStorage` to restore the sidebar, then lazy-loads message content on first open.

**Clearing history empties the thread, not the contact.** `CLEAR_PM_THREAD` sets `threads[username] = []` rather than deleting the key. Deleting the key removed the user from `PMList` (which derives from `Object.keys(threads)`), causing the icon to disappear until the next reload. "Clear history" means "delete the messages", not "forget this person exists".

---

### 2.4 Instant Logout Presence

**What it does:** When a user logs out, other users see them leave rooms immediately instead of after a ~5-second delay.

**The problem it solves.** The chat-service has a 5-second reconnect grace period on lobby WebSocket disconnects — designed so that page refreshes don't cause spurious "user left" flashes. On logout, this grace period was unnecessary (the user is genuinely gone) but still triggered, delaying the `user_left` broadcast.

**Key design decisions:**

**Explicit `{"type":"logout"}` message over the lobby WebSocket.** On logout, the frontend sends this message before closing the socket. The lobby handler detects it, sets `intentionalLogout = true`, and skips `time.Sleep(lobbyOfflineGrace)`. The distinction is: intentional logout = message then close; page refresh = socket close with no prior message.

**Grace period preserved for page refreshes.** The 5-second grace period still applies for unexpected disconnects. This is important — without it, every page refresh would briefly show all room members as "offline" and trigger spurious `user_left` system messages.

**`flushPendingLeaves` fires immediately on intentional logout.** When `DisconnectLobby` is called without the grace period, it triggers the `onFullLogout` callbacks, which calls `flushPendingLeaves`. This cancels any pending room grace-period timers and immediately broadcasts `user_left` to all rooms the user was in, in one pass.

---

## 3. Phase 3 Features — UI/UX Improvements Sprint

This sprint addressed eleven UX gaps identified after Phase 2 shipped. The changes touch every layer — new database columns and tables, new REST endpoints, new frontend pages, and reshaped component architecture. The unifying theme is: promote the app from a working prototype to a polished product where every surface feels intentional.

---

### 3.1 Room Name Display (No # Prefix)

**What it does:** Room names are displayed without a `#` prefix everywhere in the UI — the sidebar list, the chat header, and search results.

**Key design decisions:**

**Remove at source, not at display.** `#` was a static string prepended in three JSX locations (`RoomList.jsx`, `ChatPage.jsx` header, `SearchModal.jsx` query formatter). The fix was surgical: delete those three string concatenations. Alternative: strip at a single display utility function — overkill for a cosmetic change that lives in three well-defined spots. The `#` was cosmetic chrome, not part of the stored room name, so no database or API changes were needed.

---

### 3.2 Email Registration

**What it does:** Email is now a required field on registration. The auth-service stores it, validates uniqueness, and returns it in the user profile.

**Key design decisions:**

**Nullable at DB level, required at application level.** The migration adds `email VARCHAR(255) UNIQUE` as a nullable column. Nullable allows existing users (created before this migration) to continue working — their rows keep `email = NULL`. New registrations enforce `email: EmailStr` (non-nullable) in the Pydantic `UserRegister` schema. This is the standard "nullable migration, required application logic" pattern for adding columns to a live table without a big-bang data backfill.

**`EmailStr` from Pydantic v2.** Pydantic's `EmailStr` type validates RFC 5322 email format at parse time — no regex needed. It also normalises the local part to lowercase, preventing `User@Example.com` and `user@example.com` from being stored as two different emails. The uniqueness constraint on the DB column is a second line of defence.

**Duplicate email check in the service layer, not the DAL.** `auth_service.register()` calls `user_dal.get_by_email()` before `user_dal.create()`. If the email already exists, it raises `HTTPException(409)` before the INSERT. Alternative: rely on the DB's `UNIQUE` constraint and catch `IntegrityError` — works, but forces you to parse DB error messages to produce a user-friendly response. Explicit pre-check is cleaner and more portable.

---

### 3.3 Edit Email and Password in Settings

**What it does:** Logged-in users can change their email address and password from the settings page. Both operations require the current password as confirmation.

**Key design decisions:**

**Three new auth-service endpoints: `GET /auth/profile`, `PATCH /auth/profile/email`, `PATCH /auth/profile/password`.** Separate endpoints for separate concerns — profile read, email update, password update. This follows the REST principle of resource-oriented design. A single `PATCH /auth/profile` accepting any field would work technically but conflates two security-sensitive operations that have different risk profiles and different validation rules.

**Current password required for both updates.** Changing email or password is a privileged action. Requiring `current_password` in the request body means a session hijack (e.g., someone who grabbed the JWT) cannot silently update credentials — they still need the original password. This is standard for credential-change flows.

**Password hashed with bcrypt in the service layer.** `update_password()` calls `bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())` before `user_dal.update_password()`. The DAL only ever stores hashes — plaintext never reaches the database layer. This is the same pattern used in registration.

**New Pydantic schemas: `UpdateEmailRequest`, `UpdatePasswordRequest`, `ProfileResponse`.** `UpdatePasswordRequest` enforces `min_length=8, max_length=128` on `new_password`. This prevents trivially weak passwords at the validation layer before any business logic runs.

---

### 3.4 Forgot / Reset Password

**What it does:** Users who forget their password enter their email on the login page. They receive a reset link (via email or console in dev). Clicking the link opens a page where they set a new password.

**Key design decisions:**

**Always return 200 on `POST /auth/forgot-password`.** The endpoint looks up the user by email. If found, it generates a token and sends the email. If not found, it does nothing. Either way it returns `{"message": "If that email is registered, you will receive a reset link."}`. This is standard email enumeration prevention — an attacker who submits email addresses to discover which are registered gets no useful signal.

**Token stored in a `password_reset_tokens` table, not in the users row.** The token has `user_id`, `token` (32-byte hex, URL-safe), `expires_at` (1 hour), and `used` flag. This design allows multiple outstanding tokens (e.g., user requests twice) and makes invalidation explicit: mark `used = True` rather than clearing a nullable column on the users table. Tokens are one-time-use: `reset_password()` marks the token used immediately after the password update, inside the same DB transaction.

**SMTP with console fallback (adapter pattern).** `email_service.py` defines an `EmailSender` base class with a `send(to, subject, body)` method. `SMTPEmailSender` uses Python's `smtplib` for production; `ConsoleEmailSender` logs the reset link to stdout for local development. A factory function reads the `SMTP_HOST` environment variable and returns the appropriate sender. This is the **dependency inversion principle** applied to I/O: business logic (generate token, send email) depends on the abstraction (`EmailSender`), not on the transport implementation. Swapping SMTP for SendGrid requires only a new class, not changes to any service logic.

**`ResetPasswordPage` is a public route (no auth required).** Added to `App.jsx` outside the `AuthenticatedShell` wrapper. The token in `?token=xxx` is the credential — no JWT is needed or appropriate on this page.

**Minimum password length 6 characters on reset, 8 in profile settings.** The reset page enforces 6 characters (a common convention for password resets); the profile change page enforces 8. Both are validated frontend + backend (Pydantic on the reset endpoint, Pydantic on the profile endpoint).

---

### 3.5 Clear Conversation History

**What it does:** Users can clear the visible message history for any room or PM conversation. Only their own view is cleared — other participants still see the full history.

**Key design decisions:**

**Per-user watermark table instead of hard deletes.** A new `user_message_clears` table stores `(user_id, context_type, context_id, cleared_at)`. When the user fetches history, the query filters `WHERE sent_at > cleared_at`. This gives each user an independent view of the history — a "clear" is a personal bookmark, not a destructive operation. Hard-deleting messages for one user's clear would destroy history for everyone else.

**Upsert semantics for repeated clears.** `clear_dal.upsert_clear()` uses `ON CONFLICT (user_id, context_type, context_id) DO UPDATE SET cleared_at = NOW()`. If a user clears the same conversation twice, the second clear simply advances the watermark. There is at most one row per `(user, conversation)` pair — no unbounded accumulation.

**`context_type IN ('room', 'pm')` check constraint.** The DB enforces that only valid context types can be stored, preventing application bugs from silently inserting invalid rows.

---

### 3.6 Delete PM Conversation

**What it does:** Users can delete a DM conversation from their sidebar. The conversation disappears for them only — the other participant's view is unaffected. If the deleted partner sends a new message, the conversation is automatically restored.

**Key design decisions:**

**Soft-delete in a separate `deleted_pm_conversations` table.** Storing the deletion as `(user_id, other_user_id, deleted_at)` rather than a flag on the PM thread means the schema stays clean — there is no nullable `deleted_by_user_a` / `deleted_by_user_b` column pair on the conversations table. The separate table also makes "restore on new message" trivial: delete the row from `deleted_pm_conversations` when a new PM arrives from that partner.

**Restore on inbound message.** When the WebSocket delivers a PM from a previously-deleted conversation, the frontend dispatches `RESTORE_PM_CONVERSATION` which removes the entry from `deletedPMs` state and re-adds the thread to the sidebar. This matches user expectation: "I deleted the conversation, but they messaged me again."

---

### 3.7 Command Palette Search

**What it does:** The existing search modal was redesigned as a command palette (triggered by Ctrl+K). Results support full keyboard navigation (up/down to move, Enter to select). Clicking or selecting a result navigates to the room and scrolls to the specific message with a temporary highlight animation.

**Key design decisions:**

**Evolve the existing `SearchModal`, not replace it.** The existing component already had debounce, abort controller cancellation, and highlight logic for query matches. Adding keyboard navigation (`selectedIndex` state, `onKeyDown` handler, `aria-activedescendant`) and scroll-to-message was additive. Alternative: rewrite from scratch — risks losing the abort controller pattern and reintroducing race conditions.

**Context window endpoint for scroll-to-message.** `GET /messages/rooms/{room_id}/context?message_id=xxx&before=25&after=25` returns the 25 messages before and after the target. When navigating to a search result, the frontend replaces the room's message list with this context window and sets `highlightMessageId`. `MessageList` scrolls to the highlighted message and applies a CSS animation (`.msg-highlight`: gold background pulse, fades after 2 seconds). Loading only the context window (50 messages) instead of the full history (potentially thousands) is a performance trade-off — the user sees the relevant message immediately, and the full history is available by scrolling up.

**`message_id` propagated through the navigation chain.** `SearchModal` calls `onNavigate(roomId, messageId)`. `ChatPage.handleSearchNavigate` receives both, joins the room, then calls the context endpoint. The message_id flows end-to-end without being lost at any intermediate step — each layer passes it through explicitly.

---

### 3.8 Settings Page

**What it does:** Settings moved from a slide-over modal to a full page at `/settings`. The page is divided into three sections: Profile (email + password change), Security (2FA setup), and Account (clear history, delete PM conversations).

**Key design decisions:**

**Full page route instead of a modal.** The modal approach (`SettingsModal`) used `position: fixed` overlay and was limited in screen real estate. A full page at `/settings` (added to `App.jsx` inside `AuthenticatedShell`) gives settings a proper URL, supports deep-linking, allows more space for complex forms, and follows the same pattern as `AdminPage`. The old `SettingsModal` component was deleted.

**Reuse of existing `TwoFactorSetup` component.** The Security section drops `<TwoFactorSetup />` directly into the settings page layout. No duplication — the component handles QR code display, TOTP verification, and enable/disable state as a self-contained unit.

**`ProfileSection` as a dedicated component.** The email and password change forms are extracted into `frontend/src/components/settings/ProfileSection.jsx` rather than inlined in `SettingsPage`. This keeps `SettingsPage` as a layout-only component and `ProfileSection` as a form-logic component — single responsibility. `ProfileSection` calls `authApi.getProfile()` on mount to display the current email, then uses `authApi.updateEmail()` / `authApi.updatePassword()` on submit.

---

### 3.9 User Avatar Dropdown

**What it does:** The user avatar in the chat header opens a dropdown menu with three actions: Settings (navigates to `/settings`), Admin Panel (shown only for global admins), and Logout. The dropdown closes on outside click or Escape key.

**Key design decisions:**

**`UserDropdown` as a self-contained component.** The dropdown logic (open state, click-outside detection via `useEffect` + `document.addEventListener`, Escape key handler) lives entirely in `frontend/src/components/common/UserDropdown.jsx`. `ChatPage` no longer manages `settingsOpen` state or separate Settings/Admin/Logout buttons — it just renders `<UserDropdown>`. This moves interaction complexity to the component that owns it.

**Conditional Admin Panel item.** The component receives an `isAdmin` prop. When false, the Admin Panel option is not rendered. This avoids exposing admin navigation to non-admin users and keeps the permission check co-located with the UI element it controls.

**Click-outside via `useRef` + `document` listener.** On mount, a `mousedown` listener is attached to `document`. If the event target is outside the dropdown ref, the menu closes. This is the standard React pattern for click-outside detection — it works regardless of whether the click target has its own event handler.

---

### 3.10 PM Feature Parity

**What it does:** Private messages now support the same edit, delete, and emoji reaction actions as room messages. The PM message styling is unified with the room message renderer — directional labels ("You -> alice") were removed in favour of the standard bubble layout. Both changes apply in real time via WebSocket push to both conversation participants.

**Key design decisions:**

**Unified rendering: remove `isPrivate` flag from PM message mapping.** Previously, `ChatPage` mapped PM messages with `isPrivate: true`, which caused `MessageList` to route them through `renderPrivateMessage()` — a separate renderer that lacked action buttons and used a different visual layout. Removing `isPrivate: true` means both room and PM messages flow through `renderRegularMessage()`. The bubble layout, hover actions (edit/delete/react), and timestamp display are identical. This follows the DRY principle and eliminates a two-codepath maintenance burden.

**`msg_id` returned by `POST /pm/send` and included in WebSocket delivery.** Previously, the PM REST response did not include `msg_id`, so the frontend had no stable identifier for PM messages. The chat-service `pm.go` handler was updated to return `msg_id` in the response body and include it in the WebSocket push to the recipient. `PMContext` was updated to store `msg_id` in each message object so that edit/delete/reaction actions have a stable target.

**New REST endpoints for PM actions in the chat-service.** Four endpoints in `pm_actions.go`:
- `PATCH /pm/edit/:msg_id` — verifies the requester is the original sender, calls the message-service to update the text, then pushes a `pm_message_edited` WebSocket event to both participants via the lobby personal channel.
- `DELETE /pm/delete/:msg_id` — same verification pattern, pushes `pm_message_deleted`.
- `POST /pm/reaction/:msg_id` — adds a reaction, pushes `pm_reaction_added`.
- `DELETE /pm/reaction/:msg_id/:emoji` — removes a reaction, pushes `pm_reaction_removed`.

Putting these in the chat-service (not the message-service) keeps WebSocket broadcast logic in one place. The message-service owns persistence; the chat-service owns real-time delivery. This is the same split used for room message actions.

**WebSocket push via lobby personal channel.** PM action events are routed through `user:<sender_id>` and `user:<recipient_id>` lobby channels rather than a room broadcast. This ensures only the two participants receive the update — no room membership check is needed, and the event cannot leak to uninvolved users.

**`PMContext` reducer handles all new action types.** `EDIT_PM_MESSAGE`, `DELETE_PM_MESSAGE`, `ADD_PM_REACTION`, `REMOVE_PM_REACTION` update the in-memory thread state immutably. The lobby WebSocket handler in `ChatConnectionLayer` dispatches these actions when the corresponding event types arrive. No polling is needed — updates are push-driven.
