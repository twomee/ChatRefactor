// src/pages/ChatPage.jsx
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useChat } from '../context/ChatContext';
import http from '../api/http';
import { connectToRoom, sendMessage, disconnectFromRoom } from '../api/websocket';
import RoomList from '../components/RoomList';
import MessageList from '../components/MessageList';
import MessageInput from '../components/MessageInput';
import UserList from '../components/UserList';
import FileUpload from '../components/FileProgress';

export default function ChatPage() {
  const { user, token, logout } = useAuth();
  const { state, dispatch } = useChat();
  const navigate = useNavigate();
  const [closedRooms, setClosedRooms] = useState(new Set());

  // Load rooms on mount
  useEffect(() => {
    http.get('/rooms/').then(res => {
      dispatch({ type: 'SET_ROOMS', rooms: res.data });
    });
  }, []);

  function refreshRooms() {
    return http.get('/rooms/').then(res => {
      dispatch({ type: 'SET_ROOMS', rooms: res.data });
      // Only rooms returned by /rooms/ are active; clear stale closed state for active rooms
      const activeIds = new Set(res.data.map(r => r.id));
      setClosedRooms(prev => {
        const next = new Set(prev);
        activeIds.forEach(id => next.delete(id));
        return next;
      });
      return res.data;
    });
  }

  function handleSelectRoom(roomId) {
    if (state.activeRoomId && state.activeRoomId !== roomId) {
      disconnectFromRoom(state.activeRoomId);
    }
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId });
    // Refresh room list before connecting to get latest is_active status
    refreshRooms();
    connectToRoom(roomId, token, (msg) => handleWsMessage(msg, roomId));
  }

  function handleWsMessage(msg, roomId) {
    switch (msg.type) {
      case 'history':
        dispatch({ type: 'SET_HISTORY', roomId: msg.room_id, messages: msg.messages });
        break;

      case 'user_join':
      case 'user_left':
        dispatch({ type: 'SET_USERS', roomId: msg.room_id, users: msg.users });
        if (msg.admins) dispatch({ type: 'SET_ADMINS', roomId: msg.room_id, admins: msg.admins });
        if (msg.muted !== undefined) dispatch({ type: 'SET_MUTED_USERS', roomId: msg.room_id, muted: msg.muted });
        break;

      case 'system':
        dispatch({
          type: 'ADD_MESSAGE',
          roomId: msg.room_id,
          message: { isSystem: true, text: msg.text },
        });
        break;

      case 'message':
        dispatch({
          type: 'ADD_MESSAGE',
          roomId: msg.room_id,
          message: { from: msg.from, text: msg.text },
        });
        break;

      case 'private_message':
        dispatch({
          type: 'ADD_MESSAGE',
          roomId,
          message: {
            from: msg.from,
            text: msg.text,
            isPrivate: true,
            to: msg.to,
            isSelf: msg.self || false,
          },
        });
        break;

      case 'file_shared':
        dispatch({
          type: 'ADD_MESSAGE',
          roomId: msg.room_id,
          message: {
            isFile: true,
            from: msg.from,
            text: msg.filename,
            fileId: msg.file_id,
            fileSize: msg.size,
          },
        });
        break;

      case 'kicked':
        disconnectFromRoom(msg.room_id);
        dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });
        alert('You were kicked from the room');
        break;

      case 'muted':
        dispatch({ type: 'ADD_MUTED', roomId: msg.room_id, username: msg.username });
        break;

      case 'unmuted':
        dispatch({ type: 'REMOVE_MUTED', roomId: msg.room_id, username: msg.username });
        break;

      case 'new_admin':
        dispatch({ type: 'SET_ADMIN', roomId: msg.room_id, username: msg.username });
        break;

      case 'chat_closed':
        setClosedRooms(prev => new Set([...prev, msg.room_id ?? roomId]));
        disconnectFromRoom(msg.room_id ?? roomId);
        refreshRooms();
        alert(msg.detail);
        break;

      case 'error':
        alert(msg.detail);
        break;

      default:
        break;
    }
  }

  function handleSend(text) {
    if (!state.activeRoomId) return;
    sendMessage(state.activeRoomId, { type: 'message', text });
  }

  function handleKick(target) {
    sendMessage(state.activeRoomId, { type: 'kick', target });
  }

  function handleMute(target) {
    sendMessage(state.activeRoomId, { type: 'mute', target });
  }

  function handleUnmute(target) {
    sendMessage(state.activeRoomId, { type: 'unmute', target });
  }

  function handlePromote(target) {
    sendMessage(state.activeRoomId, { type: 'promote', target });
  }

  function handleLogout() {
    if (state.activeRoomId) disconnectFromRoom(state.activeRoomId);
    logout();
    navigate('/login');
  }

  const activeMessages = state.messages[state.activeRoomId] || [];
  const activeUsers = state.onlineUsers[state.activeRoomId] || [];
  const activeAdmins = state.admins[state.activeRoomId] || [];
  const activeMuted = state.mutedUsers[state.activeRoomId] || [];
  const isRoomClosed = state.activeRoomId ? closedRooms.has(state.activeRoomId) : false;
  const isCurrentUserAdmin = activeAdmins.includes(user?.username);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* Header */}
      <div style={{ padding: '8px 16px', borderBottom: '1px solid #ccc', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>cHATBOX</strong>
        <div>
          <span style={{ marginRight: 12 }}>👤 {user?.username}</span>
          {user?.is_global_admin && (
            <button onClick={() => navigate('/admin')} style={{ marginRight: 8 }}>Admin Panel</button>
          )}
          <button onClick={handleLogout}>Logout</button>
        </div>
      </div>

      {/* Main layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <RoomList rooms={state.rooms} activeRoomId={state.activeRoomId} onSelect={handleSelectRoom} />

        {/* Chat area */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          {state.activeRoomId ? (
            <>
              {isRoomClosed && (
                <div style={{ padding: '8px 12px', background: '#ffebee', color: '#c62828', borderBottom: '1px solid #ef9a9a', fontWeight: 'bold' }}>
                  🔒 This room is closed. Messaging is disabled.
                </div>
              )}
              <MessageList messages={activeMessages} />
              {!isRoomClosed && (
                <>
                  <FileUpload roomId={state.activeRoomId} />
                  <MessageInput onSend={handleSend} />
                </>
              )}
            </>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: '#999' }}>
              Select a room to start chatting
            </div>
          )}
        </div>

        <UserList
          users={activeUsers}
          admins={activeAdmins}
          mutedUsers={activeMuted}
          currentUser={user?.username}
          isCurrentUserAdmin={isCurrentUserAdmin}
          onKick={handleKick}
          onMute={handleMute}
          onUnmute={handleUnmute}
          onPromote={handlePromote}
        />
      </div>
    </div>
  );
}
