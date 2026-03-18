// src/hooks/useMultiRoomChat.js
import { useEffect, useRef, useCallback } from 'react';
import { useChat } from '../context/ChatContext';
import { usePM } from '../context/PMContext';
import { useAuth } from '../context/AuthContext';
import http from '../api/http';

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
        // Deduplicate using msg_id (arrives on each joined room's socket).
        // Cap the dedup Set at 500 entries to prevent unbounded growth in long sessions.
        if (msg.msg_id) {
          if (seenMsgIdsRef.current.has(msg.msg_id)) break;
          if (seenMsgIdsRef.current.size >= 500) {
            // Evict the oldest entry (insertion-order first element of the Set)
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
          // Compute surviving rooms BEFORE the loop so that when multiple rooms disappear
          // in the same poll tick, nextJoined is always chosen from rooms that will persist
          // (not from a room that is also about to be exited in a later loop iteration).
          const survivingJoined = [...joined].filter(id => serverIds.has(id));
          joined.forEach(roomId => {
            if (!serverIds.has(roomId)) {
              exitRoomRef.current(roomId);
              if (activeRoomIdRef.current === roomId) {
                // Prefer switching to another joined room; fall back to placeholder
                const nextJoined = survivingJoined.find(id => id !== roomId);
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
