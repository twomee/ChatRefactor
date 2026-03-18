// src/hooks/useMultiRoomChat.js
import { useEffect, useRef, useCallback, startTransition } from 'react';
import { useChat } from '../context/ChatContext';
import { usePM } from '../context/PMContext';
import { useAuth } from '../context/AuthContext';
import { WS_BASE } from '../config/constants';
import { listRooms } from '../services/roomApi';
import { getJoinedRooms, addJoinedRoom, removeJoinedRoom } from '../utils/storage';

export function useMultiRoomChat() {
  const { state, dispatch } = useChat();
  const { pmState, pmDispatch } = usePM();
  const { token, user } = useAuth();
  const username = user?.username ?? 'anonymous';

  // Mutable refs — changes don't need re-renders
  const socketsRef = useRef(new Map());
  const lobbyRef = useRef(null);              // lobby WebSocket for PM delivery
  const seenMsgIdsRef = useRef(new Set());
  const activeRoomIdRef = useRef(state.activeRoomId);
  const stateRef = useRef(state);
  const pmStateRef = useRef(pmState);

  // Keep refs in sync with latest state
  useEffect(() => { activeRoomIdRef.current = state.activeRoomId; }, [state.activeRoomId]);
  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => { pmStateRef.current = pmState; }, [pmState]);

  // ── Message handler ────────────────────────────────────────────────
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
        break;

      case 'kicked': {
        const roomName = stateRef.current.rooms.find(r => r.id === msg.room_id)?.name || 'a room';
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

      case 'room_list_updated':
        startTransition(() => {
          dispatch({ type: 'SET_ROOMS', rooms: msg.rooms });
        });
        // Auto-exit rooms that no longer exist on the server
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

      case 'error':
        window.alert(msg.detail);
        break;

      default:
        break;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch, pmDispatch]);

  // ── Stable refs for functions that call each other ──────────────────
  const handleMessageRef = useRef(handleMessage);
  useEffect(() => { handleMessageRef.current = handleMessage; }, [handleMessage]);

  const exitRoomRef = useRef(() => {});
  const exitAllRoomsRef = useRef(() => {});

  // ── joinRoom ───────────────────────────────────────────────────────
  const joinRoom = useCallback((roomId, isRetry = false) => {
    if (socketsRef.current.has(roomId)) return;

    if (!isRetry) {
      dispatch({ type: 'JOIN_ROOM', roomId });
      addJoinedRoom(username, roomId);
    }

    const ws = new WebSocket(`${WS_BASE}/ws/${roomId}?token=${token}`);

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      handleMessageRef.current(msg, roomId);
    };

    ws.onclose = (event) => {
      // Only clean up if this is still the active socket for this room
      // (StrictMode double-mount can fire stale onclose for the first socket)
      if (socketsRef.current.get(roomId) === ws) {
        socketsRef.current.delete(roomId);
      }
      if (event.code === 4003 && !isRetry) {
        setTimeout(() => {
          if (getJoinedRooms(username).includes(roomId)) {
            joinRoom(roomId, true);
          }
        }, 1000);
      } else if (event.code === 4003 && isRetry) {
        dispatch({ type: 'EXIT_ROOM', roomId });
        removeJoinedRoom(username, roomId);
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
  }, [username, dispatch]);

  // ── exitAllRooms ───────────────────────────────────────────────────
  const exitAllRooms = useCallback(() => {
    [...socketsRef.current.keys()].forEach(roomId => exitRoom(roomId));
  }, [exitRoom]);

  useEffect(() => { exitRoomRef.current = exitRoom; }, [exitRoom]);
  useEffect(() => { exitAllRoomsRef.current = exitAllRooms; }, [exitAllRooms]);

  // ── sendMessage ────────────────────────────────────────────────────
  const sendMessage = useCallback((roomId, payload) => {
    const ws = socketsRef.current.get(roomId);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  // ── Lobby connection — always-on for PM delivery ────────────────────
  useEffect(() => {
    let intentionallyClosed = false;

    function connectLobby() {
      const ws = new WebSocket(`${WS_BASE}/ws/lobby?token=${token}`);
      let wasOpen = false;

      ws.onopen = () => { wasOpen = true; };
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleMessageRef.current(msg, null);
      };
      ws.onclose = () => {
        // Only clean up if this is still the active lobby socket
        if (lobbyRef.current === ws) {
          lobbyRef.current = null;
        }
        // Only reconnect if the connection was previously established
        // (not a 403/auth rejection) and we didn't close intentionally.
        if (!intentionallyClosed && wasOpen) {
          setTimeout(() => {
            if (!lobbyRef.current) connectLobby();
          }, 3000);
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // ── Mount: restore joined rooms from localStorage ──────────────────
  useEffect(() => {
    const saved = getJoinedRooms(username);
    saved.forEach(roomId => joinRoom(roomId));

    return () => {
      socketsRef.current.forEach(ws => ws.close());
      socketsRef.current.clear();
      seenMsgIdsRef.current.clear();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { joinRoom, exitRoom, exitAllRooms, sendMessage };
}
