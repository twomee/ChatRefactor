// src/layouts/AuthenticatedShell.jsx
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { PMProvider } from '../context/PMContext';
import ChatConnectionLayer from './ChatConnectionLayer';

// Wraps ALL authenticated routes — PMProvider + WebSocket connections persist
// across /chat ↔ /admin so the admin can receive PMs on any page.
export default function AuthenticatedShell() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" />;
  return <PMProvider><ChatConnectionLayer /></PMProvider>;
}
