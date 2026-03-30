// src/context/PMContext.jsx
import { createContext, useContext, useReducer } from 'react';

const PMContext = createContext(null);

const initialPMState = {
  threads: {},       // { username: [{ from, text, isSelf, to, timestamp, msg_id }] }
  pmUnread: {},      // { username: number }
  activePM: null,    // username of currently open PM conversation (or null)
  deletedPMs: {},    // { username: deleted_at } — for deleted conversations
  loadedThreads: {}, // { username: true } — tracks which threads have been fetched from server
};

export function pmReducer(state, action) {
  switch (action.type) {
    case 'ADD_PM_MESSAGE': {
      const existing = state.threads[action.username] || [];
      return {
        ...state,
        threads: {
          ...state.threads,
          [action.username]: [...existing, action.message],
        },
      };
    }

    case 'INCREMENT_PM_UNREAD': {
      const current = state.pmUnread[action.username] || 0;
      return {
        ...state,
        pmUnread: { ...state.pmUnread, [action.username]: current + 1 },
      };
    }

    case 'CLEAR_PM_UNREAD':
      if (!state.pmUnread[action.username]) return state;
      return {
        ...state,
        pmUnread: { ...state.pmUnread, [action.username]: 0 },
      };

    case 'SET_ACTIVE_PM':
      return { ...state, activePM: action.username };

    case 'EDIT_PM_MESSAGE': {
      const thread = state.threads[action.username] || [];
      return {
        ...state,
        threads: {
          ...state.threads,
          [action.username]: thread.map(m =>
            m.msg_id === action.msg_id
              ? { ...m, text: action.text, edited_at: new Date().toISOString() }
              : m
          ),
        },
      };
    }

    case 'DELETE_PM_MESSAGE': {
      const thread = state.threads[action.username] || [];
      return {
        ...state,
        threads: {
          ...state.threads,
          [action.username]: thread.map(m =>
            m.msg_id === action.msg_id
              ? { ...m, text: '[deleted]', is_deleted: true }
              : m
          ),
        },
      };
    }

    case 'ADD_PM_REACTION': {
      const thread = state.threads[action.username] || [];
      return {
        ...state,
        threads: {
          ...state.threads,
          [action.username]: thread.map(m => {
            if (m.msg_id !== action.msg_id) return m;
            const reactions = [...(m.reactions || [])];
            reactions.push({ emoji: action.emoji, username: action.reactor, user_id: action.reactor_id });
            return { ...m, reactions };
          }),
        },
      };
    }

    case 'REMOVE_PM_REACTION': {
      const thread = state.threads[action.username] || [];
      return {
        ...state,
        threads: {
          ...state.threads,
          [action.username]: thread.map(m => {
            if (m.msg_id !== action.msg_id) return m;
            const reactions = (m.reactions || []).filter(
              r => !(r.emoji === action.emoji && r.username === action.reactor)
            );
            return { ...m, reactions };
          }),
        },
      };
    }

    case 'CLEAR_PM_THREAD': {
      // Destructure to remove the key; _removed is intentionally unused.
      const { [action.username]: _removed, ...rest } = state.threads; // eslint-disable-line no-unused-vars
      return { ...state, threads: rest };
    }

    case 'DELETE_PM_CONVERSATION': {
      return {
        ...state,
        deletedPMs: { ...state.deletedPMs, [action.username]: new Date().toISOString() },
      };
    }

    case 'RESTORE_PM_CONVERSATION': {
      // Destructure to remove the key; _removed is intentionally unused.
      const { [action.username]: _removed, ...rest } = state.deletedPMs; // eslint-disable-line no-unused-vars
      return { ...state, deletedPMs: rest };
    }

    case 'SET_PM_THREAD':
      return {
        ...state,
        threads: { ...state.threads, [action.username]: action.messages },
      };

    case 'MARK_THREAD_LOADED':
      return {
        ...state,
        loadedThreads: { ...state.loadedThreads, [action.username]: true },
      };

    case 'INIT_PM_THREAD':
      // Don't overwrite a thread that already has live messages
      if (state.threads[action.username]) return state;
      return {
        ...state,
        threads: { ...state.threads, [action.username]: [] },
      };

    default:
      return state;
  }
}

export function PMProvider({ children }) {
  const [pmState, pmDispatch] = useReducer(pmReducer, initialPMState);
  return (
    <PMContext.Provider value={{ pmState, pmDispatch }}>
      {children}
    </PMContext.Provider>
  );
}

export const usePM = () => useContext(PMContext);
