// src/context/ChatContext.jsx
import { createContext, useContext, useReducer } from 'react';

const ChatContext = createContext(null);

const initialState = {
  rooms: [],          // list of { id, name }
  activeRoomId: null,
  messages: {},       // { room_id: [{ from, text, timestamp }] }
  onlineUsers: {},    // { room_id: [username] }
  admins: {},         // { room_id: [username] }
  mutedUsers: {},     // { room_id: [username] }
};

function chatReducer(state, action) {
  switch (action.type) {
    case 'SET_ROOMS':
      return { ...state, rooms: action.rooms };
    case 'SET_ACTIVE_ROOM':
      return { ...state, activeRoomId: action.roomId };
    case 'ADD_MESSAGE': {
      const roomMsgs = state.messages[action.roomId] || [];
      return {
        ...state,
        messages: { ...state.messages, [action.roomId]: [...roomMsgs, action.message] },
      };
    }
    case 'SET_USERS':
      return { ...state, onlineUsers: { ...state.onlineUsers, [action.roomId]: action.users } };
    case 'SET_ADMIN':
      return {
        ...state,
        admins: {
          ...state.admins,
          [action.roomId]: [...(state.admins[action.roomId] || []), action.username],
        },
      };
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
