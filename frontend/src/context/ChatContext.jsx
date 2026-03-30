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
  readPositions: {},   // { roomId: messageId } — per-user last-read message ID from server
  knownOfflineUsers: new Set(), // Set<username> — users we've positively seen go offline
};

export function chatReducer(state, action) {
  switch (action.type) {

    // ── Session lifecycle ──────────────────────────────────────────────
    case 'RESET':
      return { ...initialState, rooms: state.rooms };


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
      const prevRoomUsers = state.onlineUsers[action.roomId] || [];
      const newOnlineUsers = { ...state.onlineUsers, [action.roomId]: action.users };
      const nextOffline = new Set(state.knownOfflineUsers);
      // User is confirmed online — remove from offline set
      if (action.username) nextOffline.delete(action.username);
      // Detect users who disappeared from this room's list (e.g. missed user_left
      // events during a reconnect). Mark them offline if absent from ALL rooms.
      const newUsersSet = new Set(action.users);
      for (const prevUser of prevRoomUsers) {
        if (!newUsersSet.has(prevUser)) {
          const stillOnline = Object.entries(newOnlineUsers).some(
            ([rid, list]) => String(rid) !== String(action.roomId) && list.includes(prevUser),
          );
          if (!stillOnline) nextOffline.add(prevUser);
        }
      }
      let next = { ...state, onlineUsers: newOnlineUsers, knownOfflineUsers: nextOffline };
      if (action.admins !== undefined) next = { ...next, admins: { ...state.admins, [action.roomId]: action.admins } };
      if (action.muted !== undefined) next = { ...next, mutedUsers: { ...state.mutedUsers, [action.roomId]: action.muted } };
      return next;
    }

    case 'USER_LEFT_ROOM': {
      const newOnlineUsers = { ...state.onlineUsers, [action.roomId]: action.users };
      // Don't mark users offline when they leave a room — they may still be
      // logged in (lobby connected). Only USER_OFFLINE (from lobby disconnect)
      // should mark users as truly offline.
      let next = { ...state, onlineUsers: newOnlineUsers };
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
      const typingUsers = { ...state.typingUsers };
      delete typingUsers[action.roomId];
      const readPositions = { ...state.readPositions };
      delete readPositions[action.roomId];
      // If we've left all rooms we can no longer track anyone's presence — clear
      // stale offline entries so PMs don't show false-positive "Offline" banners.
      const knownOfflineUsers = next.size === 0 ? new Set() : state.knownOfflineUsers;
      return { ...state, joinedRooms: next, messages, onlineUsers, admins, mutedUsers, unreadCounts, typingUsers, readPositions, knownOfflineUsers };
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

    case 'SET_READ_POSITION': {
      return {
        ...state,
        readPositions: { ...state.readPositions, [action.roomId]: action.messageId },
      };
    }

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

    // ── Emoji Reactions ──────────────────────────────────────────────────────
    case 'ADD_REACTION': {
      const roomMsgs = state.messages[action.roomId] || [];
      return {
        ...state,
        messages: {
          ...state.messages,
          [action.roomId]: roomMsgs.map(msg =>
            msg.msg_id === action.msgId
              ? {
                  ...msg,
                  reactions: [
                    ...(msg.reactions || []),
                    { emoji: action.emoji, username: action.username, user_id: action.userId },
                  ],
                }
              : msg
          ),
        },
      };
    }

    case 'REMOVE_REACTION': {
      const roomMsgs = state.messages[action.roomId] || [];
      return {
        ...state,
        messages: {
          ...state.messages,
          [action.roomId]: roomMsgs.map(msg =>
            msg.msg_id === action.msgId
              ? {
                  ...msg,
                  reactions: (msg.reactions || []).filter(
                    r => !(r.emoji === action.emoji && r.username === action.username)
                  ),
                }
              : msg
          ),
        },
      };
    }

    // ── Lobby-level presence (independent of room membership) ──────────
    case 'USER_ONLINE': {
      if (!state.knownOfflineUsers.has(action.username)) return state;
      const nextOffline = new Set(state.knownOfflineUsers);
      nextOffline.delete(action.username);
      return { ...state, knownOfflineUsers: nextOffline };
    }

    case 'USER_OFFLINE': {
      if (state.knownOfflineUsers.has(action.username)) return state;
      const nextOffline = new Set(state.knownOfflineUsers);
      nextOffline.add(action.username);
      return { ...state, knownOfflineUsers: nextOffline };
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
