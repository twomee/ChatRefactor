// src/pages/ChatPage.jsx
import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useChat } from '../context/ChatContext';
import { usePM } from '../context/PMContext';
import { useChatConnection } from '../layouts/ChatConnectionLayer';
import * as pmApi from '../services/pmApi';
import * as authApi from '../services/authApi';
import Logo from '../components/common/Logo';
import RoomList from '../components/room/RoomList';
import MessageList from '../components/chat/MessageList';
import MessageInput from '../components/chat/MessageInput';
import UserList from '../components/room/UserList';
import FileUpload from '../components/chat/FileProgress';
import PMList from '../components/pm/PMList';
import PMView from '../components/pm/PMView';
import ConnectionStatus from '../components/common/ConnectionStatus';

function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

export default function ChatPage() {
  const { user, logout } = useAuth();
  const { state, dispatch } = useChat();
  const { pmState, pmDispatch } = usePM();
  const navigate = useNavigate();

  const { joinRoom, exitRoom, disconnectAll, sendMessage, connectionStatus } = useChatConnection();

  // ── Handlers ─────────────────────────────────────────────────────────────

  function handleJoinRoom(roomId) {
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId });
    pmDispatch({ type: 'SET_ACTIVE_PM', username: null });
    joinRoom(roomId);
  }

  function handleExitRoom(roomId) {
    exitRoom(roomId);
    if (state.activeRoomId === roomId) {
      const remaining = [...state.joinedRooms].filter(id => id !== roomId);
      dispatch({ type: 'SET_ACTIVE_ROOM', roomId: remaining[0] ?? null });
      pmDispatch({ type: 'SET_ACTIVE_PM', username: null });
    }
  }

  function handleSelectRoom(roomId) {
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId });
    dispatch({ type: 'CLEAR_UNREAD', roomId });
    pmDispatch({ type: 'SET_ACTIVE_PM', username: null });
  }

  function handleSelectPM(username) {
    pmDispatch({ type: 'SET_ACTIVE_PM', username });
    pmDispatch({ type: 'CLEAR_PM_UNREAD', username });
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });
  }

  function handleStartPM(username) {
    pmDispatch({ type: 'SET_ACTIVE_PM', username });
    pmDispatch({ type: 'CLEAR_PM_UNREAD', username });
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });
  }

  function handleSend(text) {
    if (!state.activeRoomId) return;
    sendMessage(state.activeRoomId, { type: 'message', text });
  }

  async function handleSendPM(text) {
    if (!pmState.activePM) return;
    try {
      await pmApi.sendPM(pmState.activePM, text);
      pmDispatch({
        type: 'ADD_PM_MESSAGE',
        username: pmState.activePM,
        message: { from: user.username, text, isSelf: true, to: pmState.activePM },
      });
    } catch (e) {
      window.alert(e.response?.data?.detail || 'Could not send message');
    }
  }

  function handleKick(target) { sendMessage(state.activeRoomId, { type: 'kick', target }); }
  function handleMute(target) { sendMessage(state.activeRoomId, { type: 'mute', target }); }
  function handleUnmute(target) { sendMessage(state.activeRoomId, { type: 'unmute', target }); }
  function handlePromote(target) { sendMessage(state.activeRoomId, { type: 'promote', target }); }

  function handleGoToAdmin() {
    pmDispatch({ type: 'SET_ACTIVE_PM', username: null });
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });
    navigate('/admin');
  }

  async function handleLogout() {
    // Close WebSocket connections but keep localStorage so rooms restore on re-login.
    disconnectAll();
    try { await authApi.logout(); } catch { /* best-effort logout */ }
    logout();
    navigate('/login');
  }

  // ── Derived values ────────────────────────────────────────────────────────
  const activeMessages = state.messages[state.activeRoomId] || [];
  const activeUsers = state.onlineUsers[state.activeRoomId] || [];
  const activeAdmins = state.admins[state.activeRoomId] || [];
  const activeMuted = state.mutedUsers[state.activeRoomId] || [];
  const isCurrentUserAdmin = activeAdmins.includes(user?.username);

  const pmMessages = pmState.activePM
    ? (pmState.threads[pmState.activePM] || []).map(m => ({
        isPrivate: true,
        from: m.from,
        text: m.text,
        isSelf: m.isSelf,
        to: m.to,
      }))
    : [];

  const showRoom = !!state.activeRoomId;
  const showPM = !showRoom && !!pmState.activePM;

  const handleRoomScrollBottom = useCallback(() => {
    if (state.activeRoomId) dispatch({ type: 'CLEAR_UNREAD', roomId: state.activeRoomId });
  }, [state.activeRoomId, dispatch]);

  const handlePMScrollBottom = useCallback(() => {
    if (pmState.activePM) pmDispatch({ type: 'CLEAR_PM_UNREAD', username: pmState.activePM });
  }, [pmState.activePM, pmDispatch]);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="chat-layout">
      {/* Header */}
      <header className="chat-header">
        <Logo />
        <div className="chat-header-actions">
          <ConnectionStatus status={connectionStatus} />
          <div className="user-badge">
            <div className="user-avatar">{getInitials(user?.username)}</div>
            {user?.username}
          </div>
          {user?.is_global_admin && (
            <button onClick={handleGoToAdmin} className="btn-ghost">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/>
              </svg>
              Admin
            </button>
          )}
          <button onClick={handleLogout} className="btn-ghost">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Logout
          </button>
        </div>
      </header>

      {/* Main layout */}
      <div className="chat-main">
        {/* Left sidebar */}
        <aside className="sidebar">
          <div className="sidebar-content">
            <RoomList
              rooms={state.rooms}
              joinedRooms={state.joinedRooms}
              activeRoomId={state.activeRoomId}
              unreadCounts={state.unreadCounts}
              onJoin={handleJoinRoom}
              onExit={handleExitRoom}
              onSelect={handleSelectRoom}
            />
            <PMList
              threads={pmState.threads}
              pmUnread={pmState.pmUnread}
              activePM={pmState.activePM}
              onSelectPM={handleSelectPM}
            />
          </div>
          {user?.is_global_admin && (
            <div className="sidebar-footer">
              <button onClick={handleGoToAdmin} className="btn-primary">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3"/>
                  <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/>
                </svg>
                Admin Panel
              </button>
            </div>
          )}
        </aside>

        {/* Center panel */}
        <main className="center-panel">
          {showRoom && (
            <>
              <MessageList
                messages={activeMessages}
                onScrollToBottom={handleRoomScrollBottom}
              />
              <FileUpload roomId={state.activeRoomId} />
              <MessageInput onSend={handleSend} />
            </>
          )}
          {showPM && (
            <PMView
              username={pmState.activePM}
              messages={pmMessages}
              onSend={handleSendPM}
              onScrollToBottom={handlePMScrollBottom}
            />
          )}
          {!showRoom && !showPM && (
            <div className="empty-state">
              <div className="empty-state-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <div className="empty-state-title">No conversation selected</div>
              <div className="empty-state-text">
                Choose a room or start a private message to begin chatting
              </div>
            </div>
          )}
        </main>

        {/* Right panel */}
        {showRoom && (
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
            onStartPM={handleStartPM}
          />
        )}
      </div>
    </div>
  );
}
