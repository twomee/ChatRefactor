// src/context/PMContext.jsx
import { createContext, useContext, useReducer } from 'react';

const PMContext = createContext(null);

const initialPMState = {
  threads: {},    // { username: [{ from, text, isSelf, to, timestamp }] }
  pmUnread: {},   // { username: number }
  activePM: null, // username of currently open PM conversation (or null)
};

function pmReducer(state, action) {
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
