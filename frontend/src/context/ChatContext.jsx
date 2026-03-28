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
  typingUsers: {},     // { roomId: { username: timestamp } } — ephemeral typing indicators
  knownOfflineUsers: new Set(), // Set<username> — users we've positively seen go offline
};

export function chatReducer(state, action) {
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

    // ── Presence-aware room join/leave (atomically update onlineUsers + knownOfflineUsers) ──
    case 'USER_JOINED_ROOM': {
      const newOnlineUsers = { ...state.onlineUsers, [action.roomId]: action.users };
      // User is confirmed online — remove from offline set
      const nextOffline = new Set(state.knownOfflineUsers);
      if (action.username) nextOffline.delete(action.username);
      let next = { ...state, onlineUsers: newOnlineUsers, knownOfflineUsers: nextOffline };
      if (action.admins !== undefined) next = { ...next, admins: { ...state.admins, [action.roomId]: action.admins } };
      if (action.muted !== undefined) next = { ...next, mutedUsers: { ...state.mutedUsers, [action.roomId]: action.muted } };
      return next;
    }

    case 'USER_LEFT_ROOM': {
      const newOnlineUsers = { ...state.onlineUsers, [action.roomId]: action.users };
      // Only mark offline if user is absent from every tracked room after this update
      const nextOffline = new Set(state.knownOfflineUsers);
      if (action.username) {
        const stillOnline = Object.values(newOnlineUsers).some(list => list.includes(action.username));
        if (!stillOnline) nextOffline.add(action.username);
      }
      let next = { ...state, onlineUsers: newOnlineUsers, knownOfflineUsers: nextOffline };
      if (action.admins !== undefined) next = { ...next, admins: { ...state.admins, [action.roomId]: action.admins } };
      if (action.muted !== undefined) next = { ...next, mutedUsers: { ...state.mutedUsers, [action.roomId]: action.muted } };
      return next;
    }

    // ── New actions ────────────────────────────────────────────────────────
    case 'JOIN_ROOM': {
      // Idempotent — no-op (and no re-render) if room is already joined
      if (state.joinedRooms.has(action.roomId)) return state;
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
      const { [action.roomId]: _ty, ...typingUsers } = state.typingUsers || {};
      // If we've left all rooms we can no longer track anyone's presence — clear
      // stale offline entries so PMs don't show false-positive "Offline" banners.
      const knownOfflineUsers = next.size === 0 ? new Set() : state.knownOfflineUsers;
      return { ...state, joinedRooms: next, messages, onlineUsers, admins, mutedUsers, unreadCounts, typingUsers, knownOfflineUsers };
    }

    case 'INCREMENT_UNREAD': {
      const current = state.unreadCounts[action.roomId] || 0;
      return {
        ...state,
        unreadCounts: { ...state.unreadCounts, [action.roomId]: current + 1 },
      };
    }

    case 'CLEAR_UNREAD':
      if (!state.unreadCounts[action.roomId]) return state;
      return {
        ...state,
        unreadCounts: { ...state.unreadCounts, [action.roomId]: 0 },
      };

    case 'SET_TYPING': {
      const { roomId, username, isTyping } = action;
      const current = state.typingUsers?.[roomId] || {};
      const updated = { ...current };
      if (isTyping) {
        updated[username] = Date.now();
      } else {
        delete updated[username];
      }
      return {
        ...state,
        typingUsers: { ...state.typingUsers, [roomId]: updated },
      };
    }

    case 'EDIT_MESSAGE': {
      const roomMsgs = state.messages[action.roomId];
      if (!roomMsgs) return state;
      const updated = roomMsgs.map(m =>
        m.msg_id === action.msgId
          ? { ...m, text: action.text, edited_at: action.edited_at }
          : m
      );
      return {
        ...state,
        messages: { ...state.messages, [action.roomId]: updated },
      };
    }

    case 'DELETE_MESSAGE': {
      const roomMsgs = state.messages[action.roomId];
      if (!roomMsgs) return state;
      const updated = roomMsgs.map(m =>
        m.msg_id === action.msgId
          ? { ...m, text: '[deleted]', is_deleted: true }
          : m
      );
      return {
        ...state,
        messages: { ...state.messages, [action.roomId]: updated },
      };
    }

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
