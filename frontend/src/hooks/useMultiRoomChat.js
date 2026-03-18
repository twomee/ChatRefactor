// src/hooks/useMultiRoomChat.js
import { useEffect, useRef, useCallback, startTransition } from 'react';
import { useChat } from '../context/ChatContext';
import { usePM } from '../context/PMContext';
import { useAuth } from '../context/AuthContext';
import { WS_BASE } from '../config/constants';
import { listRooms, getRoomUsers } from '../services/roomApi';
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
  const roomsEtagRef = useRef(null);
  const usersEtagRef = useRef(null);
  const activeRoomIdRef = useRef(state.activeRoomId);
  const stateRef = useRef(state);
  const pmStateRef = useRef(pmState);

  // Keep refs in sync with latest state
  useEffect(() => { activeRoomIdRef.current = state.activeRoomId; }, [state.activeRoomId]);
  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => { pmStateRef.current = pmState; }, [pmState]);
  useEffect(() => { usersEtagRef.current = null; }, [state.activeRoomId]);

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
      socketsRef.current.delete(roomId);
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

  // ── Polling loop ───────────────────────────────────────────────────
  useEffect(() => {
    const poll = async () => {
      try {
        const roomRes = await listRooms(roomsEtagRef.current);

        if (roomRes.status === 200) {
          roomsEtagRef.current = roomRes.headers['etag'] || null;
          // Wrap in startTransition so polling updates (low priority) can't
          // interrupt React Router's startTransition-based route changes.
          startTransition(() => {
            dispatch({ type: 'SET_ROOMS', rooms: roomRes.data });
          });

          const serverIds = new Set(roomRes.data.map(r => r.id));
          const joined = stateRef.current.joinedRooms;
          const survivingJoined = [...joined].filter(id => serverIds.has(id));
          joined.forEach(roomId => {
            if (!serverIds.has(roomId)) {
              exitRoomRef.current(roomId);
              if (activeRoomIdRef.current === roomId) {
                const nextJoined = survivingJoined.find(id => id !== roomId);
                dispatch({ type: 'SET_ACTIVE_ROOM', roomId: nextJoined ?? null });
              }
              window.alert('A room you were in was closed by the admin.');
            }
          });
        }

        const activeId = activeRoomIdRef.current;
        if (activeId) {
          const userRes = await getRoomUsers(activeId, usersEtagRef.current);
          if (userRes.status === 200) {
            usersEtagRef.current = userRes.headers['etag'] || null;
            startTransition(() => {
              dispatch({ type: 'SET_USERS', roomId: activeId, users: userRes.data.users });
            });
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

  // ── Lobby connection — always-on for PM delivery ────────────────────
  useEffect(() => {
    function connectLobby() {
      const ws = new WebSocket(`${WS_BASE}/ws/lobby?token=${token}`);
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleMessageRef.current(msg, null);
      };
      ws.onclose = () => {
        lobbyRef.current = null;
        // Auto-reconnect after 3 s if component is still mounted
        setTimeout(() => {
          if (!lobbyRef.current) connectLobby();
        }, 3000);
      };
      lobbyRef.current = ws;
    }
    connectLobby();
    return () => {
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
