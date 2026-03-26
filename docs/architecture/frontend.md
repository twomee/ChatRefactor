# Frontend Code — Full Explanation

> Written for someone who knows JavaScript/Node.js basics but has never used React.
> Covers every file, every concept, every line that matters.

---

## Table of Contents

1. [What is React? The Mental Model](#1-what-is-react-the-mental-model)
2. [The Toolchain — How the App Starts](#2-the-toolchain--how-the-app-starts)
3. [Configuration & Utilities](#3-configuration--utilities)
4. [Services — API Calls to the Backend](#4-services--api-calls-to-the-backend)
5. [State Management — Context + Reducers](#5-state-management--context--reducers)
6. [The Hook — useMultiRoomChat.js](#6-the-hook--usemultiroomchatjs)
7. [App.jsx — Routing and Layout](#7-appjsx--routing-and-layout)
8. [Pages](#8-pages)
9. [Components](#9-components)
10. [Full Data Flow: Typing "Hello" in a Room](#10-full-data-flow-typing-hello-in-a-room)

---

## 1. What is React? The Mental Model

Before touching any file, you need to understand what React solves.

### The Problem with Plain JavaScript

In plain JS, you manually manipulate the HTML page. If you want to show a new message, you write:

```javascript
document.getElementById('messages').innerHTML += '<div>' + text + '</div>';
```

This gets nightmarish fast. You have to track every element, manually update every piece of HTML, and keep your data (variables) in sync with what's on screen.

### What React Does

React flips this. You describe **what the UI should look like** based on your data. React figures out how to update the HTML.

```
Your Data (state) → React → HTML on screen
                       ↑
          When data changes, React automatically
          updates only the parts of the HTML that changed
```

### Components — The Core Idea

A React component is just a JavaScript function that returns HTML-like code. That's it.

```javascript
function Greeting({ name }) {         // receives "props" (like arguments)
  return <h1>Hello, {name}!</h1>;     // returns "JSX" (HTML-in-JS)
}

// Usage:
<Greeting name="Alice" />   // renders: <h1>Hello, Alice!</h1>
```

### JSX — Why HTML is Inside JavaScript

The `<h1>Hello</h1>` inside a `.jsx` file is not real HTML. It's **JSX** — a syntax that gets compiled by Vite into real JavaScript function calls:

```javascript
// JSX:
<h1>Hello</h1>

// Compiles to:
React.createElement('h1', null, 'Hello')
```

It looks like HTML for readability, but it's JavaScript under the hood.

### State — The Variable That Triggers Re-Renders

```javascript
const [count, setCount] = useState(0);
```

`count` is just a variable. But when you call `setCount(1)`, React knows "something changed" and re-runs the component function, updating the screen.

A plain `let count = 0; count = 1` would **not** update the screen — React wouldn't know about it.

### Props — Passing Data Into Components

Props are like function arguments for components. A parent passes data down to a child:

```javascript
// Parent:
<UserList users={['alice', 'bob']} onKick={handleKick} />

// Child receives them:
function UserList({ users, onKick }) {
  return users.map(u => <div onClick={() => onKick(u)}>{u}</div>);
}
```

---

## 2. The Toolchain — How the App Starts

### `package.json`

```json
"dependencies": {
  "react": "^19.2.4",
  "react-dom": "^19.2.4",
  "react-router-dom": "^7.13.1",
  "axios": "^1.13.6"
},
"devDependencies": {
  "vite": "^8.0.0"
}
```

| Package | Purpose |
|---|---|
| `react` | The React library itself (the logic) |
| `react-dom` | Connects React to the actual browser DOM |
| `react-router-dom` | Handles URL navigation (`/login`, `/chat`, `/admin`) |
| `axios` | HTTP client for calling the backend API (like `requests` in Python) |
| `vite` | Build tool — bundles `.jsx` files into a single `.js` file the browser understands, dev server with hot-reload |

### `index.html`

```html
<div id="root"></div>
<script type="module" src="/src/main.jsx"></script>
```

The entire frontend is one HTML file with one empty `<div id="root">`. React injects everything into that div.

This is called a **Single Page Application (SPA)** — there's only one real HTML page. React fakes navigation by swapping what's rendered inside that div.

### `src/main.jsx`

```javascript
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>
)
```

The entry point. It finds `<div id="root">` and tells React: "take over this div and render `<App />` inside it."

`StrictMode` is a development tool — it intentionally runs things twice to help you find bugs. Has zero effect in production.

---

## 3. Configuration & Utilities

### `src/config/constants.js`

```javascript
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export const WS_BASE = wsBaseEnv || (() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}`;
})();
```

`import.meta.env.VITE_*` is Vite's way of reading `.env` files (equivalent to `os.getenv` in Python).

For WebSockets: if the page is loaded over `https://`, use `wss://` (secure WebSocket). If `http://`, use `ws://`. This auto-detects the correct protocol rather than hardcoding it.

---

### `src/services/http.js`

```javascript
const http = axios.create({ baseURL: API_BASE });

http.interceptors.request.use(config => {
  const token = sessionStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
```

Creates a single Axios instance shared across the whole app.

The **interceptor** is like middleware — it runs before every HTTP request. It automatically reads the JWT token from `sessionStorage` and adds the `Authorization: Bearer <token>` header. You write `http.get('/rooms/')` anywhere in the app without worrying about auth — the interceptor handles it.

**`sessionStorage` vs `localStorage`:**

| | sessionStorage | localStorage |
|---|---|---|
| Cleared when | Tab is closed | Never (manually only) |
| Used for | JWT token (security) | Joined rooms list (persistence) |

Both are browser key-value stores that only hold strings.

---

### `src/utils/storage.js`

```javascript
export function getJoinedRooms(username) {
  const key = `chatbox_joined_rooms_${username ?? 'anonymous'}`;
  return JSON.parse(localStorage.getItem(key) || '[]');
}

export function addJoinedRoom(username, roomId) {
  const saved = getJoinedRooms(username);
  if (!saved.includes(roomId)) {
    localStorage.setItem(key, JSON.stringify([...saved, roomId]));
  }
}
```

The key is per-username (`chatbox_joined_rooms_alice`) so multiple users on the same browser don't interfere with each other.

`localStorage` only stores strings, so `JSON.parse`/`JSON.stringify` converts between arrays and strings.

`...saved` is the **spread operator** — copies all elements of the array into a new array, then appends `roomId`. This is how you add to an array without mutating it.

---

### `src/utils/formatting.js`

```javascript
export function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
```

Pure utility. `toFixed(1)` rounds to 1 decimal place. `1536` → `"1.5 KB"`.

---

## 4. Services — API Calls to the Backend

These are thin wrappers around `http.js`, one file per domain. Same separation-of-concerns idea as the backend's `services/` layer.

### `src/services/authApi.js`

```javascript
export function login(username, password) {
  return http.post('/auth/login', { username, password });
}
```

`http.post` returns a **Promise** — JavaScript's version of async/await. A Promise represents "a value that will arrive in the future." You `await` it to get the result:

```javascript
const res = await authApi.login('alice', 'secret');
// res.data = { access_token: "...", username: "alice", is_global_admin: false }
```

---

### `src/services/fileApi.js`

```javascript
export function uploadFile(roomId, file, onProgress) {
  const form = new FormData();
  form.append('file', file);
  return http.post(`/files/upload?room_id=${roomId}`, form, {
    onUploadProgress: onProgress,
  });
}
```

`FormData` is the browser's way of sending files over HTTP (multipart/form-data).

`onUploadProgress` is a callback Axios calls repeatedly during upload with `{ loaded: bytes_sent, total: total_bytes }` — used to update the progress bar.

```javascript
export function getDownloadUrl(fileId) {
  const token = sessionStorage.getItem('token');
  return `${API_BASE}/files/download/${fileId}?token=${token}`;
}
```

Returns a URL string with the token in the query param. Browser `<a href>` links navigate without setting headers, so the token has to be in the URL instead of the `Authorization` header.

---

## 5. State Management — Context + Reducers

### The Problem: How Do Components Share Data?

You have many components on screen at once (room list, message list, user list). They all need to share the same data. How?

**Wrong approach:** pass data as props down through every component in between — "prop drilling."

**React's solution: Context** — a global store any component can read from directly, without passing props.

```
AuthProvider
  └── any component anywhere can call useAuth()
      and get { user, token, login, logout }
      without anyone passing it as props
```

---

### The Reducer Pattern

Both `ChatContext` and `PMContext` use `useReducer`. Understand this pattern first.

```javascript
const [state, dispatch] = useReducer(reducer, initialState);
```

| Variable | What it is |
|---|---|
| `state` | The current data (read-only) |
| `dispatch` | A function you call to request a state change |
| `reducer` | A function that takes (currentState, action) → newState |

You **never modify state directly**:

```javascript
state.messages.push(newMessage);  // WRONG — React won't know to re-render

dispatch({ type: 'ADD_MESSAGE', roomId: 3, message: newMessage }); // CORRECT
```

Every state update must go through the reducer. This makes all state changes predictable and traceable.

---

### `src/context/AuthContext.jsx`

Holds: `{ user, token, login(), logout() }`

```javascript
const [token, setToken] = useState(() => sessionStorage.getItem('token'));
const [user, setUser] = useState(() => {
  const raw = sessionStorage.getItem('user');
  return raw ? JSON.parse(raw) : null;
});
```

The `() =>` inside `useState` is a **lazy initializer** — runs only once when the component first mounts, not on every re-render. On page refresh, this restores the session from `sessionStorage` automatically.

```javascript
function login(tokenStr, userData) {
  setToken(tokenStr);
  setUser(userData);
  sessionStorage.setItem('token', tokenStr);
  sessionStorage.setItem('user', JSON.stringify(userData));
}
```

When you log in: save to React state (triggers re-render) AND save to `sessionStorage` (survives page refresh). Both must happen together — if you only did one, they'd get out of sync after a refresh.

```javascript
useEffect(() => {
  if (token) ping().catch(() => {});
}, []); // empty array = run once on mount
```

`useEffect` is "run this code as a side effect after render." The empty `[]` means run it once when the component first appears (like a startup hook).

On page load, if a token exists, ping the backend to re-register the user in `manager.logged_in_users`. This handles the case where the backend restarted and lost its in-memory state.

```javascript
return (
  <AuthContext.Provider value={{ user, token, login, logout }}>
    {children}
  </AuthContext.Provider>
);
```

`Provider` makes `{ user, token, login, logout }` available to any component inside it. `{children}` means "render whatever is wrapped inside `<AuthProvider>...</AuthProvider>`."

```javascript
export const useAuth = () => useContext(AuthContext);
```

Any component calls `const { user, login } = useAuth()` — no prop passing needed.

---

### `src/context/ChatContext.jsx`

Holds all room-related state:

```javascript
const initialState = {
  rooms: [],            // [{id, name, is_active}] — the server's room list
  activeRoomId: null,   // which room is currently visible on screen
  joinedRooms: new Set(), // rooms where we have active WebSocket connections
  unreadCounts: {},     // { roomId: number } — unread badge counts
  messages: {},         // { roomId: [messages] }
  onlineUsers: {},      // { roomId: [usernames] }
  admins: {},           // { roomId: [usernames] }
  mutedUsers: {},       // { roomId: [usernames] }
};
```

All data is keyed by `roomId` because you can be in multiple rooms simultaneously. `messages[3]` = the message array for room 3.

**Key reducer cases explained:**

```javascript
case 'EXIT_ROOM': {
  const { [action.roomId]: _m, ...messages } = state.messages;
  // ...
}
```

This is **destructuring with exclusion**. It means: take `state.messages`, put the value at key `roomId` into `_m` (which we discard with `_`), and put everything else into `messages`. Result: `messages` is the object without that room's key. Clean removal in one line.

```javascript
case 'SET_ADMIN':
  return {
    ...state,
    admins: {
      ...state.admins,
      [action.roomId]: [...new Set([...(state.admins[action.roomId] || []), action.username])],
    },
  };
```

Every state update creates a **new object** (`{ ...state }` spreads the old one into a new one). You never mutate existing state — React needs new object references to detect changes.

The `new Set([...existing, newUsername])` de-duplicates — if the user is already in the admin list, adding them again has no effect.

---

### `src/context/PMContext.jsx`

Holds private message state:

```javascript
const initialPMState = {
  threads: {},    // { username: [messages] } — one thread per conversation partner
  pmUnread: {},   // { username: number } — unread badge per conversation
  activePM: null, // which PM conversation is currently open
};
```

Same pattern as `ChatContext` but for private messages. Key is `username` instead of `roomId`.

---

## 6. The Hook — `useMultiRoomChat.js`

### What is a Hook?

A "hook" in React is just a function whose name starts with `use` and uses React's built-in features inside it. It lets you extract reusable stateful logic out of components.

Think of it like a Python class with `__init__` + lifecycle methods, but it's a plain function.

This hook is the **heart of the frontend** — it manages ALL WebSocket connections.

---

### `useRef` vs `useState`

```javascript
const socketsRef = useRef(new Map());    // roomId → WebSocket object
const seenMsgIdsRef = useRef(new Set()); // for PM deduplication
```

| | `useState` | `useRef` |
|---|---|---|
| Change triggers re-render? | **Yes** | **No** |
| Use for | Data that should be shown on screen | Mutable values that don't affect the UI |

WebSocket objects, Maps of sockets, Sets of seen IDs — you don't want the whole UI to re-render every time a socket opens or a message ID is tracked. `useRef` is perfect for this.

```javascript
// Keep refs in sync with latest state
useEffect(() => { activeRoomIdRef.current = state.activeRoomId; }, [state.activeRoomId]);
```

Callbacks like WebSocket's `onmessage` "capture" the value of variables from when they were created. If `onmessage` reads `state.activeRoomId` directly, it'll always see the stale value from when the function was created. By reading `activeRoomIdRef.current` instead, it always gets the latest value.

---

### `joinRoom`

```javascript
const joinRoom = useCallback((roomId, isRetry = false) => {
  if (socketsRef.current.has(roomId)) return;  // already connected, skip

  const ws = new WebSocket(`${WS_BASE}/ws/${roomId}?token=${token}`);
```

`useCallback` memoizes (caches) the function so it's not recreated on every render. Without it, every render would produce a new function reference, potentially causing infinite loops in `useEffect`.

`new WebSocket(url)` opens a WebSocket connection to the backend. The browser handles the HTTP→WebSocket upgrade handshake automatically.

```javascript
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  handleMessageRef.current(msg, roomId);
};
```

`ws.onmessage` is called by the browser every time the server sends data. `event.data` is always a string — `JSON.parse` converts it to a JavaScript object.

```javascript
ws.onclose = (event) => {
  // 4003 = "already in room" — retry once after 1 second
  if (event.code === 4003 && !isRetry) {
    setTimeout(() => { joinRoom(roomId, true); }, 1000);
  }
  // 4001-4004 = permanent failure (auth failed, room closed, etc.) — don't reconnect
  else if (event.code >= 4001 && event.code <= 4004) {
    dispatch({ type: 'EXIT_ROOM', roomId });
  }
  // Unexpected close (server restart, network drop) — reconnect after 2 seconds
  else if (wasOpen && getJoinedRooms(username).includes(roomId)) {
    setTimeout(() => { joinRoom(roomId, true); }, 2000);
  }
};
```

`setTimeout` is JavaScript's "run this after X milliseconds." The reconnection logic handles three cases:
- Deliberate server rejection (4001–4004) → give up
- "Already in room" (4003) → retry once, might be a race condition
- Unexpected drop → reconnect after 2 seconds

---

### `handleMessage` — The Big Switch

This handles every message type the server sends:

```javascript
case 'message':
  dispatch({ type: 'ADD_MESSAGE', roomId: msg.room_id, message: { from: msg.from, text: msg.text } });
  if (msg.room_id !== activeRoomIdRef.current) {
    dispatch({ type: 'INCREMENT_UNREAD', roomId: msg.room_id });
  }
  break;
```

If the message is for the room you're currently looking at, just add it. If it's for a background room, also increment the unread badge counter.

```javascript
case 'private_message': {
  if (msg.msg_id) {
    if (seenMsgIdsRef.current.has(msg.msg_id)) break;  // already seen, skip
    seenMsgIdsRef.current.add(msg.msg_id);
  }
  const otherUser = msg.self ? msg.to : msg.from;
```

A private message can arrive on **two sockets** — the room WebSocket and the lobby WebSocket. Without deduplication, you'd see every PM twice. `seenMsgIdsRef` tracks seen UUIDs to prevent that.

`msg.self` is `true` for messages you sent yourself (the server echoes them back to confirm delivery).

```javascript
case 'room_list_updated':
  startTransition(() => {
    dispatch({ type: 'SET_ROOMS', rooms: msg.rooms });
  });
```

`startTransition` tells React: "this update is low priority, don't interrupt user input for it." The room list update is less urgent than a user actively typing — React can defer it.

---

### The Lobby Connection

```javascript
useEffect(() => {
  let intentionallyClosed = false;

  function connectLobby() {
    const ws = new WebSocket(`${WS_BASE}/ws/lobby?token=${token}`);
    ws.onclose = () => {
      if (!intentionallyClosed && wasOpen) {
        setTimeout(() => { if (!lobbyRef.current) connectLobby(); }, 3000);
      }
    };
    lobbyRef.current = ws;
  }

  connectLobby();

  return () => {               // ← cleanup function
    intentionallyClosed = true;
    lobbyRef.current?.close();
  };
}, [token]);
```

The lobby socket is always-on for receiving private messages without being in a room.

The `return () => { ... }` at the end is the **cleanup function** — React calls it when the component unmounts (user logs out/navigates away). `intentionallyClosed = true` prevents the reconnect logic from firing when WE close it on purpose.

---

## 7. `App.jsx` — Routing and Layout

```javascript
export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ChatProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<AuthenticatedShell />}>
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/admin" element={<AdminGuard><AdminPage /></AdminGuard>} />
            </Route>
            <Route path="*" element={<Navigate to="/login" />} />
          </Routes>
        </ChatProvider>
      </BrowserRouter>
    </AuthProvider>
  );
}
```

**Providers as wrappers:** `AuthProvider` and `ChatProvider` wrap everything. Any component inside them can access their context. This is how context works — the wrapper shares data with all descendants.

**Routes:** `react-router-dom` watches the browser URL. When the URL is `/login`, render `<LoginPage />`. When `/chat`, render `<ChatPage />`. `path="*"` is a catch-all — any unknown URL redirects to `/login`.

### Protected Routes

```javascript
function AuthenticatedShell() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" />;   // redirect if not logged in
  return <PMProvider><ChatConnectionLayer /></PMProvider>;
}
```

If you try to visit `/chat` without being logged in, `user` is null → you get redirected to `/login`. This is called a **protected route** — a guard that checks auth before rendering.

### Outlet — Passing Data Between Routes

```javascript
function ChatConnectionLayer() {
  const chatConn = useMultiRoomChat();   // starts all WebSocket connections
  return <Outlet context={chatConn} />;  // passes them down to child routes
}

// In child route (ChatPage.jsx):
const { joinRoom, exitRoom, sendMessage } = useChatConnection();
// useChatConnection() = useOutletContext() — reads what Outlet passed down
```

Why this matters: WebSocket connections stay alive when navigating between `/chat` and `/admin`. If the connections were created inside `ChatPage`, they'd be destroyed every time you navigate to `/admin`. By creating them in `ChatConnectionLayer` (which wraps both routes), they persist across navigation.

---

## 8. Pages

### `src/pages/LoginPage.jsx`

```javascript
const [mode, setMode] = useState('login');   // 'login' | 'register'
const [username, setUsername] = useState('');
const [password, setPassword] = useState('');
const [error, setError] = useState('');
```

Each piece of form data is its own `useState`. When you type in the username field:

```javascript
<input value={username} onChange={e => setUsername(e.target.value)} />
```

`onChange` fires on every keypress → `setUsername(newValue)` → React re-renders → `value={username}` shows the updated text. This is **controlled input** — React is always the source of truth for what's displayed.

```javascript
async function handleSubmit(e) {
  e.preventDefault();  // ← stop the browser from doing a full page reload
  const res = await authApi.login(username, password);
  login(res.data.access_token, { username: res.data.username, ... });
  navigate('/chat');
}
```

`e.preventDefault()` is crucial. Without it, `<form onSubmit>` causes the browser to reload the page (legacy HTML behavior that would wipe all React state).

```javascript
<button className={`login-tab ${mode === 'login' ? 'active' : ''}`}>
```

`className` is JSX's version of HTML's `class` (because `class` is a reserved word in JavaScript). The ternary adds the `'active'` CSS class conditionally.

---

### `src/pages/ChatPage.jsx`

This is the main layout page. It coordinates between all the contexts and components.

```javascript
const activeMessages = state.messages[state.activeRoomId] || [];
const activeAdmins = state.admins[state.activeRoomId] || [];
const isCurrentUserAdmin = activeAdmins.includes(user?.username);
```

**Derived values** — computed from state every render, not stored separately. `user?.username` is **optional chaining** — if `user` is null/undefined, return `undefined` instead of crashing.

```javascript
const showRoom = !!state.activeRoomId;
const showPM = !showRoom && !!pmState.activePM;
```

`!!` converts a value to a boolean. The center panel shows either a room, OR a PM conversation, OR the "no conversation selected" empty state — never more than one.

```javascript
{showRoom && (
  <>
    <MessageList ... />
    <FileUpload ... />
    <MessageInput ... />
  </>
)}
```

`{showRoom && <Component />}` is **conditional rendering** — if `showRoom` is false, render nothing.

`<>...</>` is a **Fragment** — a wrapper with no real HTML element. Needed because JSX must have a single root element, but you don't want an extra `<div>` in the DOM.

```javascript
function handleKick(target) {
  sendMessage(state.activeRoomId, { type: 'kick', target });
}
```

Kick is not an HTTP call — it's a WebSocket message sent to the backend. `sendMessage` finds the correct socket and calls `ws.send(JSON.stringify({type: 'kick', target: 'bob'}))`.

---

### `src/pages/AdminPage.jsx`

```javascript
useEffect(() => {
  loadData();
  const interval = setInterval(loadData, 3000);  // poll every 3 seconds
  return () => clearInterval(interval);           // cleanup on unmount
}, [loadData]);
```

**Polling** — call the API every 3 seconds to get fresh data. `setInterval` returns an ID; `clearInterval(id)` cancels it. Without the cleanup, the interval would keep running after you leave the admin page — a classic memory leak.

```javascript
const [roomsRes, usersRes] = await Promise.all([
  adminApi.getRooms().catch(() => ({ data: [] })),
  adminApi.getUsers().catch(() => ({ data: { all_online: [], per_room: {} } })),
]);
```

`Promise.all` runs both API calls in **parallel** (not sequentially), halving the wait time. `.catch(() => fallback)` means "if this request fails, return the fallback value instead of crashing."

```javascript
{rooms.map(room => (
  <Fragment key={room.id}>
    <tr>...</tr>
    {expandedRoomFiles === room.id && <tr>...</tr>}
  </Fragment>
))}
```

`Array.map()` in JSX renders a list of elements. `key={room.id}` is required by React to track which element is which when the list updates — without it React can't efficiently update the DOM.

---

## 9. Components

### `chat/MessageList.jsx`

```javascript
const endRef = useRef(null);

useEffect(() => {
  endRef.current?.scrollIntoView({ behavior: 'smooth' });
}, [messages]);
```

`endRef` is attached to an invisible `<div>` at the bottom of the message list:

```javascript
<div ref={endRef} />
```

When `messages` changes (new message arrives), `scrollIntoView` is called on that div — scrolling the chat to the bottom automatically.

```javascript
const handleScroll = useCallback(() => {
  const el = containerRef.current;
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
  if (distanceFromBottom <= 50) {
    onScrollToBottom();   // clears unread badge
  }
}, [onScrollToBottom]);
```

Scroll math: `scrollHeight` = total content height. `scrollTop` = how far down you've scrolled. `clientHeight` = the visible area height.

When `scrollHeight - scrollTop - clientHeight ≤ 50`, you're within 50px of the bottom → clear the unread badge.

**Message rendering — four types:**

```javascript
if (msg.isSystem)  → gray centered system text ("alice has joined the room")
if (msg.isFile)    → attachment icon + download link
if (msg.isPrivate) → "alice → You" private message style
default            → standard chat bubble with avatar + username
```

---

### `room/UserList.jsx` + `common/ContextMenu.jsx`

```javascript
function handleRightClick(e, username) {
  if (username === currentUser) return;   // can't action yourself
  if (!isCurrentUserAdmin) return;        // non-admins don't get a menu
  e.preventDefault();                     // prevent browser's built-in right-click menu
  setMenu({ x: e.clientX, y: e.clientY, target: username });
}
```

`e.clientX/Y` is the mouse position in pixels from the viewport's top-left. The ContextMenu is absolutely positioned at those coordinates:

```javascript
// common/ContextMenu.jsx
<div className="context-menu" style={{ top: y, left: x }} onMouseLeave={onClose}>
```

`onMouseLeave={onClose}` closes the menu when the mouse moves away from it.

```javascript
function handleLeftClick(username) {
  if (username === currentUser) return;
  if (onStartPM) onStartPM(username);  // left-click = open PM conversation
}
```

Left-click a user → open a private message conversation with them.

---

### `chat/FileProgress.jsx` (FileUpload)

```javascript
<label className={`file-upload-label ${uploading ? 'disabled' : ''}`}>
  Attach file
  <input type="file" ref={inputRef} className="file-upload-input" onChange={handleFileChange} />
</label>
```

The `<input type="file">` is hidden (via CSS) and the visible `<label>` acts as the click target. Clicking the label triggers the hidden file input — a standard trick for custom-styled file upload buttons.

```javascript
await uploadFile(roomId, file, (evt) => {
  if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100));
});
```

`evt.loaded / evt.total * 100` = percentage. The progress bar width is set via inline style:

```javascript
<div className="file-progress-fill" style={{ width: `${progress}%` }} />
```

CSS animates the width change. `finally { setUploading(false); setProgress(0); }` always resets — whether upload succeeded or failed.

---

### `chat/MessageInput.jsx`

```javascript
function handleSubmit(e) {
  e.preventDefault();
  if (!text.trim()) return;   // ignore whitespace-only messages
  onSend(text.trim());
  setText('');                // clear input after sending
}
```

Clean, simple. `text.trim()` removes leading/trailing spaces — you can't send a message that's just spaces.

---

### `pm/PMView.jsx`

```javascript
function handleKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
}
```

Press Enter → send. Press Shift+Enter → don't send (allows newlines in the message). Standard chat input behavior.

---

### `pm/PMList.jsx`

```javascript
const usernames = Object.keys(threads);
```

`threads` is `{ alice: [...messages], bob: [...messages] }`. `Object.keys()` gives `['alice', 'bob']` — the list of people you've had conversations with. Each one gets rendered as a clickable row in the sidebar.

---

## 10. Full Data Flow: Typing "Hello" in a Room

Here's the complete journey of a single chat message, from keypress to screen:

```
STEP 1 — User types and hits Send
  MessageInput: onChange → setText("Hello")
  MessageInput: onSubmit → onSend("Hello")
  ChatPage.handleSend() called

STEP 2 — Message sent over WebSocket
  sendMessage(roomId, { type: 'message', text: 'Hello' })
  → socketsRef.current.get(roomId).send(JSON.stringify({...}))
  → WebSocket frame sent to backend

STEP 3 — Backend processes it (routers/websocket.py)
  _handle_chat_message() called
  → checks if user is muted
  → generates UUID msg_id
  → kafka_produce(TOPIC_MESSAGES, ...) → True (or fallback to direct DB save)
  → manager.broadcast(room_id, { type:'message', from:'alice', text:'Hello', ... })
  → redis.publish("room:3", JSON)

STEP 4 — Redis subscriber relays it
  start_subscriber (background task) receives from Redis
  → _local_broadcast_room(3, data)
  → ws.send_json(data) to every WebSocket in room 3

STEP 5 — Browser receives it on the frontend
  ws.onmessage fires for every connected user in room 3
  → handleMessage({ type: 'message', from: 'alice', text: 'Hello', room_id: 3 })
  → case 'message': dispatch({ type: 'ADD_MESSAGE', roomId: 3, message: {...} })
  → ChatContext reducer: adds message to state.messages[3]

STEP 6 — React updates the screen
  MessageList re-renders (messages prop changed)
  → new <div class="msg"> appears at the bottom
  → useEffect fires → scrollIntoView({ behavior: 'smooth' })
  → message visible on screen
```

---

## Appendix: Key Concept Cheat Sheet

| Concept | What it does | Python equivalent |
|---|---|---|
| `useState` | Variable that triggers re-render on change | Instance variable with a setter |
| `useEffect` | Side effects after render (API calls, subscriptions) | `__init__` + lifecycle hooks |
| `useRef` | Mutable value that does NOT trigger re-render | Plain instance variable |
| `useCallback` | Memoize a function so it's not recreated each render | `functools.lru_cache` on a method |
| `useReducer` | State machine for complex state | A class with explicit action methods |
| `useContext` | Read from a Context without prop drilling | Accessing a singleton / global |
| `Context.Provider` | Make data available to all descendants | Dependency injection container |
| `<Route>` | Render a component when URL matches | URL route handler |
| `<Navigate>` | Redirect to another URL | HTTP 302 redirect |
| `props` | Data passed from parent to child component | Function arguments |
| JSX | HTML-like syntax in JavaScript | Jinja2 templates (but in JS) |
| `async/await` | Handle Promises (async operations) | Python's `async/await` |
| `Promise.all` | Run multiple async calls in parallel | `asyncio.gather()` |
