// src/pages/ChatPage.jsx
import { useCallback, useEffect, useState } from 'react';
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
import PMList from '../components/pm/PMList';
import PMView from '../components/pm/PMView';
import ConnectionStatus from '../components/common/ConnectionStatus';

import { Responsive as ResponsiveGridLayout } from 'react-grid-layout';
import { WidthProvider } from 'react-grid-layout/legacy';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

const Responsive = WidthProvider(ResponsiveGridLayout);

const defaultLayouts = {
  lg: [
    { i: 'sidebar', x: 0, y: 0, w: 3, h: 11, minW: 2, minH: 5 },
    { i: 'messages', x: 3, y: 0, w: 6, h: 8, minW: 4, minH: 5 },
    { i: 'users', x: 9, y: 0, w: 3, h: 11, minW: 2, minH: 5 },
    { i: 'input', x: 3, y: 8, w: 6, h: 3, minW: 4, minH: 3 }
  ]
};

const CHAT_LAYOUT_KEY = 'chatbox-chat-layouts';

function loadLayouts() {
  try {
    const saved = localStorage.getItem(CHAT_LAYOUT_KEY);
    return saved ? JSON.parse(saved) : defaultLayouts;
  } catch {
    return defaultLayouts;
  }
}
function getInitials(name) {
  if (!name) return '?';
  return name.slice(0, 2).toUpperCase();
}

export default function ChatPage() {
  const { user, logout } = useAuth();
  const { state, dispatch } = useChat();
  const { pmState, pmDispatch } = usePM();
  const navigate = useNavigate();
  const [layouts, setLayouts] = useState(loadLayouts);

  const { joinRoom, exitRoom, disconnectAll, sendMessage, connectionStatus } = useChatConnection();

  // Add page-active class on mount so the one-shot aurora animation plays,
  // and remove it on unmount so the login page returns to the static gradient.
  useEffect(() => {
    document.body.classList.add('page-active');
    return () => document.body.classList.remove('page-active');
  }, []);

  function handleLayoutChange(_current, allLayouts) {
    setLayouts(allLayouts);
    try { localStorage.setItem(CHAT_LAYOUT_KEY, JSON.stringify(allLayouts)); } catch { /* storage full */ }
  }

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
      const result = await pmApi.sendPM(pmState.activePM, text);
      pmDispatch({
        type: 'ADD_PM_MESSAGE',
        username: pmState.activePM,
        message: { from: user.username, text, isSelf: true, to: pmState.activePM },
      });

      // Use the server's live_delivered flag to update online/offline status.
      // This is more reliable than knownOfflineUsers for users not in shared rooms.
      if (result.live_delivered === false) {
        dispatch({ type: 'MARK_USER_OFFLINE', username: pmState.activePM });
      } else if (result.live_delivered === true) {
        dispatch({ type: 'MARK_USER_ONLINE', username: pmState.activePM });
      }
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
  const activeRoom = state.rooms.find(r => r.id === state.activeRoomId) || null;
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

  // isRecipientOnline is false only when we've positively observed the PM recipient
  // leave every tracked room (knownOfflineUsers), avoiding false-positive offline banners
  // for users who are online but not in any shared room.
  const isRecipientOnline = pmState.activePM
    ? !state.knownOfflineUsers.has(pmState.activePM)
    : true;

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
      <header className="chat-header glass-panel" style={{ margin: '16px 16px 0', height: 'var(--header-height)', borderRadius: 'var(--radius-lg)' }}>
        {/* Left: logo + active room name */}
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <Logo />
          {activeRoom && (
            <div className="header-room-title">
              <span className="header-room-name">#{activeRoom.name}</span>
              <span className="header-room-sep">|</span>
              <span className="header-room-sub">Team Discussion</span>
            </div>
          )}
        </div>

        {/* Right: user + actions */}
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

      {/* Main layout Dashboard Grid */}
      <div style={{ flex: 1, position: 'relative', overflowY: 'auto', padding: '0 16px 16px' }}>
        <Responsive
          className="layout"
          layouts={layouts}
          onLayoutChange={handleLayoutChange}
          breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
          cols={{ lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }}
          rowHeight={55}
          draggableHandle=".drag-handle"
          margin={[16, 16]}
        >
          {/* Left sidebar */}
          <div key="sidebar" className="glass-panel">
            <div className="drag-handle" style={{ justifyContent: 'flex-end' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
            </div>
            <aside className="sidebar" style={{ flex: 1, overflow: 'hidden', background: 'transparent', width: '100%', border: 'none' }}>
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
                  knownOfflineUsers={state.knownOfflineUsers}
                />
              </div>
            </aside>
          </div>

          {/* Center message panel */}
          <div key="messages" className="glass-panel">
            <div className="drag-handle" style={{ justifyContent: 'flex-end' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
            </div>
            <main className="center-panel" style={{ flex: 1, overflow: 'hidden', background: 'transparent' }}>
              {showRoom && (
                <MessageList
                  messages={activeMessages}
                  onScrollToBottom={handleRoomScrollBottom}
                />
              )}
              {showPM && (
                <PMView
                  username={pmState.activePM}
                  messages={pmMessages}
                  onScrollToBottom={handlePMScrollBottom}
                  isOnline={isRecipientOnline}
                />
              )}
              {!showRoom && !showPM && (
                <div className="empty-state">
                  <div className="empty-state-icon" style={{ background: 'var(--primary-light)', border: 'none' }}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                  </div>
                  <div className="empty-state-title">No conversation selected</div>
                  <div className="empty-state-text">Choose a room or start a private message to begin chatting. Drag panels to customize your workspace!</div>
                </div>
              )}
            </main>
          </div>

          {/* Input Panel */}
          <div key="input" className="glass-panel" style={{ borderRadius: 'var(--radius-xl)' }}>
            <div className="drag-handle" style={{ padding: '4px 12px', borderBottom: 'none', justifyContent: 'flex-end' }}>
               <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
            </div>
            <div style={{ padding: '0 12px 12px', display: 'flex', flexDirection: 'column', justifyContent: 'center', flex: 1 }}>
              {showRoom ? (
                <MessageInput onSend={handleSend} roomName={activeRoom?.name} roomId={state.activeRoomId} />
              ) : showPM ? (
                <MessageInput onSend={handleSendPM} roomName={pmState.activePM} isPM />
              ) : (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>Select a conversation to type...</div>
              )}
            </div>
          </div>

          {/* Right panel */}
          <div key="users" className="glass-panel">
            <div className="drag-handle" style={{ justifyContent: 'flex-end' }}>
               <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
            </div>
            {showRoom ? (
              <div style={{ flex: 1, overflow: 'auto' }}>
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
              </div>
            ) : (
               <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>No room selected</div>
            )}
          </div>
        </Responsive>
      </div>
    </div>
  );
}
