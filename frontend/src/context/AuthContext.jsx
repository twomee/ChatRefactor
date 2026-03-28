// src/context/AuthContext.jsx
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
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

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('user');
  }, []);

  // Re-register with backend on every app load so logged_in_users survives server restarts.
  // If the token is rejected (401), force logout so stale sessions don't get stuck
  // in a "reconnecting" loop (e.g., after a server rebuild changes SECRET_KEY).
  useEffect(() => {
    if (token) {
      ping().catch((err) => {
        if (err?.response?.status === 401) {
          console.warn('Session token rejected by server — forcing logout');
          logout();
        }
      });
    }
  }, [token, logout]);

  function login(tokenStr, userData) {
    setToken(tokenStr);
    setUser(userData);
    sessionStorage.setItem('token', tokenStr);
    sessionStorage.setItem('user', JSON.stringify(userData));
  }

  return (
    <AuthContext.Provider value={{ user, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
