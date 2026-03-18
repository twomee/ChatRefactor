// src/App.jsx
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ChatProvider } from './context/ChatContext';
import { PMProvider } from './context/PMContext';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import AdminPage from './pages/AdminPage';

// Wraps ALL authenticated routes as a single parent — PMProvider mounts once
// so PM state survives /chat ↔ /admin navigation.
// Unmounts (resetting PM state) when user is redirected to /login on logout.
function AuthenticatedShell() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" />;
  return <PMProvider><Outlet /></PMProvider>;
}

// Admin-only guard (does not re-mount PMProvider)
function AdminGuard({ children }) {
  const { user } = useAuth();
  if (!user?.is_global_admin) return <Navigate to="/chat" />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ChatProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            {/* Single AuthenticatedShell parent keeps PMProvider alive across /chat and /admin */}
            <Route element={<AuthenticatedShell />}>
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/admin" element={<AdminGuard><AdminPage /></AdminGuard>} />
            </Route>
            <Route path="*" element={<Navigate to="/login" />} />
          </Routes>
        </ChatProvider>
      </BrowserRouter>
    </AuthProvider>
  );
}
