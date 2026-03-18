// src/pages/ChatPage.jsx
import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useChat } from '../context/ChatContext';
import { usePM } from '../context/PMContext';
import { useChatConnection } from '../App';
import * as pmApi from '../services/pmApi';
import * as authApi from '../services/authApi';
import RoomList from '../components/RoomList';
import MessageList from '../components/MessageList';
import MessageInput from '../components/MessageInput';
import UserList from '../components/UserList';
import FileUpload from '../components/FileProgress';
import PMList from '../components/PMList';
import PMView from '../components/PMView';

export default function ChatPage() {
  const { user, logout } = useAuth();
  const { state, dispatch } = useChat();
  const { pmState, pmDispatch } = usePM();
  const navigate = useNavigate();

  const { joinRoom, exitRoom, exitAllRooms, sendMessage } = useChatConnection();

  // ── Handlers ─────────────────────────────────────────────────────────────

  function handleJoinRoom(roomId) {
    // Set active room BEFORE opening the WebSocket so that activeRoomIdRef is
    // already correct when the first WS events (history, user_join) arrive —
    // prevents INCREMENT_UNREAD firing against a stale null activeRoomId.
    // NOTE: The localStorage-restore path (on mount) calls joinRoom() on the hook
    // directly — NOT this handler — so SET_ACTIVE_ROOM is never auto-dispatched
    // during restore; the user's last active room is not overwritten.
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId });
    pmDispatch({ type: 'SET_ACTIVE_PM', username: null }); // joining a room shifts focus to it, closing any open PM view
    joinRoom(roomId);
  }

  function handleExitRoom(roomId) {
    // exitRoom() also dispatches EXIT_ROOM internally, clearing all per-room state
    // (messages, onlineUsers, admins, mutedUsers, unreadCounts) for this room.
    exitRoom(roomId);
    if (state.activeRoomId === roomId) {
      // Switch to next joined room or placeholder.
      // state.joinedRooms still contains roomId here (EXIT_ROOM hasn't rendered yet)
      // so we filter it out manually.
      const remaining = [...state.joinedRooms].filter(id => id !== roomId);
      dispatch({ type: 'SET_ACTIVE_ROOM', roomId: remaining[0] ?? null });
      // Clear any open PM view — the room view takes precedence when switching rooms
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
    exitAllRooms();
    try { await authApi.logout(); } catch (_) {}
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

  // What to show in the main panel
  const showRoom = !!state.activeRoomId;
  const showPM = !showRoom && !!pmState.activePM;

  // Unread clear callbacks
  const handleRoomScrollBottom = useCallback(() => {
    if (state.activeRoomId) dispatch({ type: 'CLEAR_UNREAD', roomId: state.activeRoomId });
  }, [state.activeRoomId, dispatch]);

  const handlePMScrollBottom = useCallback(() => {
    if (pmState.activePM) pmDispatch({ type: 'CLEAR_PM_UNREAD', username: pmState.activePM });
  }, [pmState.activePM, pmDispatch]);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* Header */}
      <div style={{ padding: '8px 16px', borderBottom: '1px solid #ccc', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>cHATBOX</strong>
        <div>
          <span style={{ marginRight: 12 }}>👤 {user?.username}</span>
          {user?.is_global_admin && (
            <button onClick={handleGoToAdmin} style={{ marginRight: 8 }}>Admin Panel</button>
          )}
          <button onClick={handleLogout}>Logout</button>
        </div>
      </div>

      {/* Main layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Left sidebar */}
        <div style={{ width: 210, borderRight: '1px solid #ccc', padding: 8, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
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
          {user?.is_global_admin && (
            <button
              onClick={handleGoToAdmin}
              style={{ marginTop: 'auto', padding: '6px 0', background: '#1976d2', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 'bold' }}
            >
              ⚙ Admin Panel
            </button>
          )}
        </div>

        {/* Center panel */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
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
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: '#999' }}>
              Select a room or conversation to start chatting
            </div>
          )}
        </div>

        {/* Right panel — user list, only in room view */}
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
