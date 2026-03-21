// src/layouts/ChatConnectionLayer.jsx
import { Outlet, useOutletContext } from 'react-router-dom';
import { useMultiRoomChat } from '../hooks/useMultiRoomChat';

// Lives inside PMProvider so useMultiRoomChat (which uses usePM) has access.
// WebSocket connections persist across /chat ↔ /admin navigation.
export default function ChatConnectionLayer() {
  const chatConn = useMultiRoomChat();
  return <Outlet context={chatConn} />;
}

// Hook for child routes to access WebSocket functions
export function useChatConnection() {
  return useOutletContext();
}
