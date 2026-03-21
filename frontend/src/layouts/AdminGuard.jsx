// src/layouts/AdminGuard.jsx
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Admin-only guard (does not re-mount PMProvider)
export default function AdminGuard({ children }) {
  const { user } = useAuth();
  if (!user?.is_global_admin) return <Navigate to="/chat" />;
  return children;
}
