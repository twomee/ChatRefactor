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
};

function chatReducer(state, action) {
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
      return { ...state, joinedRooms: next, messages, onlineUsers, admins, mutedUsers, unreadCounts };
    }

    case 'INCREMENT_UNREAD': {
      const current = state.unreadCounts[action.roomId] || 0;
      return {
        ...state,
        unreadCounts: { ...state.unreadCounts, [action.roomId]: current + 1 },
      };
    }

    case 'CLEAR_UNREAD':
      return {
        ...state,
        unreadCounts: { ...state.unreadCounts, [action.roomId]: 0 },
      };

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
