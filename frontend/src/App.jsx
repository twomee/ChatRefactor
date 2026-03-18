// src/App.jsx
import { BrowserRouter, Routes, Route, Navigate, Outlet, useOutletContext } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ChatProvider } from './context/ChatContext';
import { PMProvider } from './context/PMContext';
import { useMultiRoomChat } from './hooks/useMultiRoomChat';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import AdminPage from './pages/AdminPage';

// Wraps ALL authenticated routes — PMProvider + WebSocket connections persist
// across /chat ↔ /admin so the admin can receive PMs on any page.
function AuthenticatedShell() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" />;
  return <PMProvider><ChatConnectionLayer /></PMProvider>;
}

// Lives inside PMProvider so useMultiRoomChat (which uses usePM) has access.
// WebSocket connections persist across /chat ↔ /admin navigation.
function ChatConnectionLayer() {
  const chatConn = useMultiRoomChat();
  return <Outlet context={chatConn} />;
}

// Admin-only guard (does not re-mount PMProvider)
function AdminGuard({ children }) {
  const { user } = useAuth();
  if (!user?.is_global_admin) return <Navigate to="/chat" />;
  return children;
}

// Hook for child routes to access WebSocket functions
export function useChatConnection() {
  return useOutletContext();
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ChatProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
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
