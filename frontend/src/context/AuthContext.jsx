// src/context/AuthContext.jsx
import { createContext, useContext, useState } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);   // { username, is_global_admin }
  const [token, setToken] = useState(null);

  function login(tokenStr, userData) {
    setToken(tokenStr);
    setUser(userData);
    sessionStorage.setItem('token', tokenStr); // Use sessionStorage, NOT localStorage
  }

  function logout() {
    setToken(null);
    setUser(null);
    sessionStorage.removeItem('token');
  }

  return (
    <AuthContext.Provider value={{ user, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
