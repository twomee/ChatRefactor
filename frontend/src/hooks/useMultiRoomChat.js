// src/hooks/useMultiRoomChat.js
import { useEffect, useRef, useCallback, useState, startTransition } from 'react';
import { useChat } from '../context/ChatContext';
import { usePM } from '../context/PMContext';
import { useAuth } from '../context/AuthContext';
import { WS_BASE } from '../config/constants';
import { listRooms, getMessagesSince } from '../services/roomApi';
import { getJoinedRooms, addJoinedRoom, removeJoinedRoom } from '../utils/storage';
import { requestNotificationPermission, sendBrowserNotification } from '../utils/notifications';

// ── Exponential backoff helper ──────────────────────────────────────────────
const BACKOFF_BASE_MS = 1000;
const BACKOFF_MAX_MS = 30000;

function getBackoffDelay(attempt) {
  const delay = BACKOFF_BASE_MS * Math.pow(2, attempt);
  // Add ±20 % jitter to prevent thundering herd on server restart
  const jitter = delay * 0.2 * (Math.random() * 2 - 1);
  return Math.min(delay + jitter, BACKOFF_MAX_MS);
}

export function useMultiRoomChat() {
  const { state, dispatch } = useChat();
  const { pmState, pmDispatch } = usePM();
  const { token, user } = useAuth();
  const username = user?.username ?? 'anonymous';

  // ── Connection status ─────────────────────────────────────────────────────
  // 'connected' | 'reconnecting' | 'disconnected'
  const [connectionStatus, setConnectionStatus] = useState('connected');
  const reconnectingRoomsRef = useRef(new Set());

  function updateConnectionStatus() {
    if (reconnectingRoomsRef.current.size > 0) {
      setConnectionStatus('reconnecting');
    } else {
      setConnectionStatus('connected');
    }
  }

  // Mutable refs — changes don't need re-renders
  const socketsRef = useRef(new Map());
  const lobbyRef = useRef(null);
  const seenMsgIdsRef = useRef(new Set());
  const activeRoomIdRef = useRef(state.activeRoomId);
  const stateRef = useRef(state);
  const pmStateRef = useRef(pmState);
  const retryCountsRef = useRef(new Map());     // roomId → attempt number
  const lobbyRetryRef = useRef(0);
  const lastMsgTimeRef = useRef(new Map());     // roomId → ISO timestamp
  const closingAllRef = useRef(false);          // true during disconnectAll to suppress reconnects

  // Keep refs in sync with latest state
  useEffect(() => { activeRoomIdRef.current = state.activeRoomId; }, [state.activeRoomId]);
  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => { pmStateRef.current = pmState; }, [pmState]);

  // ── Message replay after reconnect ────────────────────────────────────────
  function replayMissedMessages(roomId) {
    const since = lastMsgTimeRef.current.get(roomId);
    if (!since) return;

    getMessagesSince(roomId, since).then(res => {
      if (res.status !== 200 || !Array.isArray(res.data)) return;
      for (const m of res.data) {
        if (m.message_id && seenMsgIdsRef.current.has(m.message_id)) continue;
        if (m.message_id) seenMsgIdsRef.current.add(m.message_id);

        if (!m.is_private) {
          dispatch({
            type: 'ADD_MESSAGE',
            roomId: m.room_id,
            message: { from: m.sender, text: m.content },
          });
        }
      }
    }).catch(() => {});
  }

  // ── Track last message timestamp ──────────────────────────────────────────
  function trackTimestamp(roomId) {
    lastMsgTimeRef.current.set(roomId, new Date().toISOString());
  }

  // ── Message handler ────────────────────────────────────────────────────────
  const handleMessage = useCallback((msg, roomId) => {
    switch (msg.type) {
      case 'history':
        dispatch({ type: 'SET_HISTORY', roomId: msg.room_id, messages: msg.messages });
        trackTimestamp(msg.room_id);
        break;

      case 'user_join':
        dispatch({ type: 'USER_JOINED_ROOM', roomId: msg.room_id, users: msg.users, admins: msg.admins, muted: msg.muted, username: msg.username });
        if (msg.username) dispatch({ type: 'ADD_MESSAGE', roomId: msg.room_id, message: { isSystem: true, text: `${msg.username} joined the room` } });
        break;
      case 'user_left':
        dispatch({ type: 'USER_LEFT_ROOM', roomId: msg.room_id, users: msg.users, admins: msg.admins, muted: msg.muted, username: msg.username });
        if (msg.username) dispatch({ type: 'ADD_MESSAGE', roomId: msg.room_id, message: { isSystem: true, text: `${msg.username} left the room` } });
        break;

      case 'system':
        dispatch({ type: 'ADD_MESSAGE', roomId: msg.room_id, message: { isSystem: true, text: msg.text } });
        trackTimestamp(msg.room_id);
        break;

      case 'message': {
        // Deduplicate by msg_id to prevent duplicates from overlapping
        // connections (e.g. stale JWT sessions with different user IDs).
        if (msg.msg_id) {
          if (seenMsgIdsRef.current.has(msg.msg_id)) break;
          if (seenMsgIdsRef.current.size >= 500) {
            seenMsgIdsRef.current.delete(seenMsgIdsRef.current.values().next().value);
          }
          seenMsgIdsRef.current.add(msg.msg_id);
        }
        dispatch({ type: 'ADD_MESSAGE', roomId: msg.room_id, message: { from: msg.from, text: msg.text, msg_id: msg.msg_id } });
        if (msg.room_id !== activeRoomIdRef.current) {
          dispatch({ type: 'INCREMENT_UNREAD', roomId: msg.room_id });
        }
        trackTimestamp(msg.room_id);

        // Send browser notification when the current user is @mentioned.
        const currentUsername = user?.username;
        if (currentUsername && (msg.mentions?.includes(currentUsername.toLowerCase()) || msg.mention_room)) {
          sendBrowserNotification(
            `@${msg.from} mentioned you`,
            msg.text.substring(0, 100)
          );
        }
        break;
      }

      case 'private_message': {
        if (msg.msg_id) {
          if (seenMsgIdsRef.current.has(msg.msg_id)) break;
          if (seenMsgIdsRef.current.size >= 500) {
            seenMsgIdsRef.current.delete(seenMsgIdsRef.current.values().next().value);
          }
          seenMsgIdsRef.current.add(msg.msg_id);
        }
        const otherUser = msg.self ? msg.to : msg.from;
        pmDispatch({
          type: 'ADD_PM_MESSAGE',
          username: otherUser,
          message: { from: msg.from, text: msg.text, isSelf: !!msg.self, to: msg.to },
        });
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
        trackTimestamp(msg.room_id);
        break;

      case 'message_edited':
        dispatch({
          type: 'EDIT_MESSAGE',
          roomId: msg.room_id,
          msgId: msg.msg_id,
          text: msg.text,
          edited_at: msg.edited_at,
        });
        break;

      case 'message_deleted':
        dispatch({
          type: 'DELETE_MESSAGE',
          roomId: msg.room_id,
          msgId: msg.msg_id,
        });
        break;

      case 'kicked': {
        const kickedRoomId = msg.room_id;
        const roomName = stateRef.current.rooms.find(r => r.id === kickedRoomId)?.name || 'a room';
        exitRoomRef.current(kickedRoomId);
        if (activeRoomIdRef.current === kickedRoomId) {
          const next = [...stateRef.current.joinedRooms].find(id => id !== kickedRoomId);
          dispatch({ type: 'SET_ACTIVE_ROOM', roomId: next ?? null });
        }
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

      case 'room_list_updated':
        startTransition(() => {
          dispatch({ type: 'SET_ROOMS', rooms: msg.rooms });
        });
        {
          const serverIds = new Set(msg.rooms.map(r => r.id));
          const joined = stateRef.current.joinedRooms;
          joined.forEach(id => {
            if (!serverIds.has(id)) {
              exitRoomRef.current(id);
              if (activeRoomIdRef.current === id) {
                const next = [...joined].find(jid => jid !== id && serverIds.has(jid));
                dispatch({ type: 'SET_ACTIVE_ROOM', roomId: next ?? null });
              }
            }
          });
        }
        break;

      case 'chat_closed': {
        const closedId = msg.room_id ?? roomId;
        exitRoomRef.current(closedId);
        if (activeRoomIdRef.current === closedId) {
          dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });
        }
        window.alert(msg.detail || 'Room was closed');
        break;
      }

      case 'typing':
        dispatch({
          type: 'SET_TYPING',
          roomId: msg.room_id,
          username: msg.username,
          isTyping: true,
        });
        // Auto-clear after 3 seconds — if the sender stops typing (or
        // disconnects) we don't want a stale indicator lingering.
        setTimeout(() => {
          dispatch({
            type: 'SET_TYPING',
            roomId: msg.room_id,
            username: msg.username,
            isTyping: false,
          });
        }, 3000);
        break;

      case 'error':
        window.alert(msg.detail);
        break;

      default:
        break;
    }

  }, [dispatch, pmDispatch]);

  // ── Stable refs for functions that call each other ──────────────────
  const handleMessageRef = useRef(handleMessage);
  useEffect(() => { handleMessageRef.current = handleMessage; }, [handleMessage]);

  const exitRoomRef = useRef(() => {});
  const exitAllRoomsRef = useRef(() => {});

  // ── joinRoom (with exponential backoff on reconnect) ──────────────────────
  const joinRoom = useCallback((roomId, isRetry = false) => {
    if (socketsRef.current.has(roomId)) return;

    if (!isRetry) {
      dispatch({ type: 'JOIN_ROOM', roomId });
      addJoinedRoom(username, roomId);
      retryCountsRef.current.set(roomId, 0);
    }

    const ws = new WebSocket(`${WS_BASE}/ws/${roomId}?token=${token}`);
    let wasOpen = false;

    ws.onopen = () => {
      wasOpen = true;
      retryCountsRef.current.set(roomId, 0);
      reconnectingRoomsRef.current.delete(roomId);
      updateConnectionStatus();
      if (isRetry) replayMissedMessages(roomId);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessageRef.current(msg, roomId);
      } catch { /* drop malformed message */ }
    };

    ws.onclose = (event) => {
      if (socketsRef.current.get(roomId) === ws) {
        socketsRef.current.delete(roomId);
      }

      // 4003 = "already in room" — retry once then give up
      if (event.code === 4003 && !isRetry) {
        reconnectingRoomsRef.current.add(roomId);
        updateConnectionStatus();
        setTimeout(() => {
          if (getJoinedRooms(username).includes(roomId)) {
            joinRoom(roomId, true);
          }
        }, 1000);
      } else if (event.code === 4003 && isRetry) {
        dispatch({ type: 'EXIT_ROOM', roomId });
        removeJoinedRoom(username, roomId);
        reconnectingRoomsRef.current.delete(roomId);
        retryCountsRef.current.delete(roomId);
        updateConnectionStatus();
      }
      // 4001–4004: permanent failures — don't reconnect
      else if (event.code >= 4001 && event.code <= 4004) {
        dispatch({ type: 'EXIT_ROOM', roomId });
        removeJoinedRoom(username, roomId);
        reconnectingRoomsRef.current.delete(roomId);
        retryCountsRef.current.delete(roomId);
        updateConnectionStatus();
      }
      // Unexpected closure — auto-reconnect with exponential backoff.
      // Reconnect both when the connection was open (server went down mid-session)
      // AND when a retry failed to open (server still starting up).
      // Skip if disconnectAll() was called (logout in progress).
      else if (!closingAllRef.current && getJoinedRooms(username).includes(roomId)) {
        const attempt = (retryCountsRef.current.get(roomId) || 0) + 1;
        retryCountsRef.current.set(roomId, attempt);
        // If the connection never opened, use a fixed 5s delay (server probably starting)
        const delay = wasOpen ? getBackoffDelay(attempt - 1) : 5000;

        reconnectingRoomsRef.current.add(roomId);
        updateConnectionStatus();

        setTimeout(() => {
          if (!socketsRef.current.has(roomId) && getJoinedRooms(username).includes(roomId)) {
            joinRoom(roomId, true);
          }
        }, delay);
      }
    };

    socketsRef.current.set(roomId, ws);
  }, [token, username, dispatch]);

  // ── exitRoom ───────────────────────────────────────────────────────
  const exitRoom = useCallback((roomId) => {
    const ws = socketsRef.current.get(roomId);
    if (ws) {
      ws.close();
      socketsRef.current.delete(roomId);
    }
    dispatch({ type: 'EXIT_ROOM', roomId });
    removeJoinedRoom(username, roomId);
    retryCountsRef.current.delete(roomId);
    reconnectingRoomsRef.current.delete(roomId);
    lastMsgTimeRef.current.delete(roomId);
    updateConnectionStatus();
  }, [username, dispatch]);

  // ── exitAllRooms ───────────────────────────────────────────────────
  const exitAllRooms = useCallback(() => {
    [...socketsRef.current.keys()].forEach(roomId => exitRoom(roomId));
  }, [exitRoom]);

  // ── disconnectAll (logout) — close ALL sockets (rooms + lobby) ──
  const disconnectAll = useCallback(() => {
    // Prevent onclose handlers from scheduling reconnections
    closingAllRef.current = true;
    // Close all room sockets
    socketsRef.current.forEach(ws => ws.close());
    socketsRef.current.clear();
    // Close the lobby socket so the server removes us from the online list
    if (lobbyRef.current) {
      lobbyRef.current.close();
      lobbyRef.current = null;
    }
  }, []);

  useEffect(() => { exitRoomRef.current = exitRoom; }, [exitRoom]);
  useEffect(() => { exitAllRoomsRef.current = exitAllRooms; }, [exitAllRooms]);

  // ── sendMessage ────────────────────────────────────────────────────
  const sendMessage = useCallback((roomId, payload) => {
    const ws = socketsRef.current.get(roomId);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }, []);

  // ── sendTyping — notify the room that the current user is typing ──
  const sendTyping = useCallback((roomId) => {
    const ws = socketsRef.current.get(roomId);
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'typing' }));
    }
  }, []);

  // ── Initial room list fetch (once on mount) ─────────────────────────
  useEffect(() => {
    listRooms().then(res => {
      if (res.status === 200) {
        startTransition(() => {
          dispatch({ type: 'SET_ROOMS', rooms: res.data });
        });
      }
    }).catch(() => {});

  }, [dispatch]);

  // ── Lobby connection — always-on with exponential backoff ────────────
  useEffect(() => {
    let intentionallyClosed = false;

    function connectLobby() {
      const ws = new WebSocket(`${WS_BASE}/ws/lobby?token=${token}`);
      let wasOpen = false;
      let authRejected = false;

      ws.onopen = () => {
        wasOpen = true;
        lobbyRetryRef.current = 0;
      };
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          handleMessageRef.current(msg, null);
        } catch { /* drop malformed message */ }
      };
      ws.onclose = (event) => {
        if (lobbyRef.current === ws) {
          lobbyRef.current = null;
        }
        if (event.code === 4001) authRejected = true;
        if (!intentionallyClosed && !authRejected) {
          const attempt = lobbyRetryRef.current++;
          const delay = wasOpen ? getBackoffDelay(attempt) : 5000;
          setTimeout(() => {
            if (!lobbyRef.current) connectLobby();
          }, delay);
        }
      };
      lobbyRef.current = ws;
    }
    connectLobby();
    return () => {
      intentionallyClosed = true;
      const ws = lobbyRef.current;
      if (ws) { lobbyRef.current = null; ws.close(); }
    };

  }, [token]);

  // ── Mount: restore joined rooms from localStorage ──────────────────
  useEffect(() => {
    requestNotificationPermission();
    const saved = getJoinedRooms(username);
    saved.forEach(roomId => joinRoom(roomId));

    return () => {
      socketsRef.current.forEach(ws => ws.close());
      socketsRef.current.clear();
      seenMsgIdsRef.current.clear();
      retryCountsRef.current.clear();
      reconnectingRoomsRef.current.clear();
      lastMsgTimeRef.current.clear();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { joinRoom, exitRoom, exitAllRooms, disconnectAll, sendMessage, sendTyping, connectionStatus };
}
