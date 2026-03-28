// src/context/AuthContext.jsx
import { createContext, useContext, useState, useEffect } from 'react';
import { ping } from '../services/authApi';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // Lazy initialisers so that a page refresh restores the session without
  // requiring a new login. Both token and user object are written together
  // so they can never be out of sync across reloads.
  const [token, setToken] = useState(() => sessionStorage.getItem('token'));
  const [user, setUser] = useState(() => {
    const raw = sessionStorage.getItem('user');
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      sessionStorage.removeItem('user');
      return null;
    }
  });

  // Re-register with backend on every app load so logged_in_users survives server restarts
  useEffect(() => {
    if (token) {
      ping().catch(() => {});
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function login(tokenStr, userData) {
    setToken(tokenStr);
    setUser(userData);
    sessionStorage.setItem('token', tokenStr);
    sessionStorage.setItem('user', JSON.stringify(userData));
  }

  function logout() {
    setToken(null);
    setUser(null);
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('user');
  }

  return (
    <AuthContext.Provider value={{ user, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
