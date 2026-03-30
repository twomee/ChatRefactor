// src/pages/ChatPage.jsx
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useChat } from '../context/ChatContext';
import { usePM } from '../context/PMContext';
import { useChatConnection } from '../layouts/ChatConnectionLayer';
import * as pmApi from '../services/pmApi';
import * as authApi from '../services/authApi';
import * as messageApi from '../services/messageApi';
import Logo from '../components/common/Logo';
import RoomList from '../components/room/RoomList';
import MessageList from '../components/chat/MessageList';
import MessageInput from '../components/chat/MessageInput';
import TypingIndicator from '../components/chat/TypingIndicator';
import UserList from '../components/room/UserList';
import PMList from '../components/pm/PMList';
import PMView from '../components/pm/PMView';
import ConnectionStatus from '../components/common/ConnectionStatus';
import UserDropdown from '../components/common/UserDropdown';
import SearchModal from '../components/chat/SearchModal';

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
export default function ChatPage() {
  const { user, logout } = useAuth();
  const { state, dispatch } = useChat();
  const { pmState, pmDispatch } = usePM();
  const navigate = useNavigate();
  const [layouts, setLayouts] = useState(loadLayouts);

  const { joinRoom, exitRoom, disconnectAll, sendMessage, sendTyping, markAsRead, connectionStatus } = useChatConnection();
  const [editingMessage, setEditingMessage] = useState(null);
  const [editingPMMessage, setEditingPMMessage] = useState(null);
  const markAsReadTimerRef = useRef(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [highlightMessageId, setHighlightMessageId] = useState(null);
  const [clearRoomConfirm, setClearRoomConfirm] = useState(false);

  // Add page-active class on mount so the one-shot aurora animation plays,
  // and remove it on unmount so the login page returns to the static gradient.
  useEffect(() => {
    document.body.classList.add('page-active');
    return () => document.body.classList.remove('page-active');
  }, []);

  // Ctrl+K / Cmd+K keyboard shortcut to open search
  useEffect(() => {
    function handleSearchShortcut(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(prev => !prev);
      }
    }
    globalThis.addEventListener('keydown', handleSearchShortcut);
    return () => globalThis.removeEventListener('keydown', handleSearchShortcut);
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
    setClearRoomConfirm(false);
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

  function handleSend(text, editMsgId) {
    if (!state.activeRoomId) return;
    if (editMsgId) {
      // Edit mode — send edit via WebSocket
      sendMessage(state.activeRoomId, { type: 'edit_message', msg_id: editMsgId, text });
      setEditingMessage(null);
    } else {
      sendMessage(state.activeRoomId, { type: 'message', text });
    }
  }

  function handleEditMessage(msg) {
    setEditingMessage(msg);
  }

  function handleDeleteMessage(msg) {
    if (!state.activeRoomId || !msg.msg_id) return;
    sendMessage(state.activeRoomId, { type: 'delete_message', msg_id: msg.msg_id });
  }

  function handleCancelEdit() {
    setEditingMessage(null);
  }

  async function handleSendPM(text, editMsgId) {
    if (!pmState.activePM) return;
    if (editMsgId) {
      // Edit mode
      try {
        await pmApi.editPM(editMsgId, text);
        pmDispatch({ type: 'EDIT_PM_MESSAGE', username: pmState.activePM, msg_id: editMsgId, text });
        setEditingPMMessage(null);
      } catch (e) {
        globalThis.alert(e.response?.data?.detail || 'Could not edit message');
      }
      return;
    }
    try {
      const res = await pmApi.sendPM(pmState.activePM, text);
      pmDispatch({
        type: 'ADD_PM_MESSAGE',
        username: pmState.activePM,
        message: { from: user.username, text, isSelf: true, to: pmState.activePM, msg_id: res.data?.msg_id },
      });
    } catch (e) {
      globalThis.alert(e.response?.data?.detail || 'Could not send message');
    }
  }

  function handlePMEditMessage(msg) {
    setEditingPMMessage(msg);
  }

  async function handlePMDeleteMessage(msg) {
    if (!msg.msg_id || !pmState.activePM) return;
    try {
      await pmApi.deletePM(msg.msg_id);
      pmDispatch({ type: 'DELETE_PM_MESSAGE', username: pmState.activePM, msg_id: msg.msg_id });
    } catch (e) {
      globalThis.alert(e.response?.data?.detail || 'Could not delete message');
    }
  }

  async function handlePMAddReaction(msgId, emoji) {
    if (!pmState.activePM) return;
    try {
      await pmApi.addPMReaction(msgId, emoji);
      pmDispatch({
        type: 'ADD_PM_REACTION',
        username: pmState.activePM,
        msg_id: msgId,
        emoji,
        reactor: user.username,
        reactor_id: user.user_id,
      });
    } catch { /* ignore */ }
  }

  async function handlePMRemoveReaction(msgId, emoji) {
    if (!pmState.activePM) return;
    try {
      await pmApi.removePMReaction(msgId, emoji);
      pmDispatch({
        type: 'REMOVE_PM_REACTION',
        username: pmState.activePM,
        msg_id: msgId,
        emoji,
        reactor: user.username,
      });
    } catch { /* ignore */ }
  }

  function handleAddReaction(msgId, emoji) {
    if (!state.activeRoomId) return;
    sendMessage(state.activeRoomId, { type: 'add_reaction', msg_id: msgId, emoji });
  }

  function handleRemoveReaction(msgId, emoji) {
    if (!state.activeRoomId) return;
    sendMessage(state.activeRoomId, { type: 'remove_reaction', msg_id: msgId, emoji });
  }

  function handleKick(target) { sendMessage(state.activeRoomId, { type: 'kick', target }); }
  function handleMute(target) { sendMessage(state.activeRoomId, { type: 'mute', target }); }
  function handleUnmute(target) { sendMessage(state.activeRoomId, { type: 'unmute', target }); }
  function handlePromote(target) { sendMessage(state.activeRoomId, { type: 'promote', target }); }

  async function handleSearchNavigate(roomId, messageId) {
    // Navigate to a room from a search result — join if not already joined
    if (roomId) {
      if (!state.joinedRooms.has(roomId)) {
        joinRoom(roomId);
      }
      dispatch({ type: 'SET_ACTIVE_ROOM', roomId });
      dispatch({ type: 'CLEAR_UNREAD', roomId });
      pmDispatch({ type: 'SET_ACTIVE_PM', username: null });
    }

    // If we have a messageId, fetch surrounding context and highlight
    if (messageId && roomId) {
      try {
        const contextRes = await messageApi.getMessageContext(roomId, messageId);
        if (contextRes.data && contextRes.data.length > 0) {
          dispatch({ type: 'SET_MESSAGES', roomId, messages: contextRes.data });
        }
        setHighlightMessageId(messageId);
        // Clear highlight after animation completes
        setTimeout(() => setHighlightMessageId(null), 3000);
      } catch {
        // Fallback: just navigate without scroll — room was already set above
      }
    }
  }

  async function handleLogout() {
    // Close WebSocket connections but keep localStorage so rooms restore on re-login.
    disconnectAll();
    try { await authApi.logout(); } catch { /* best-effort logout */ }
    logout();
    navigate('/login');
  }

  async function handleClearRoomHistory() {
    if (!state.activeRoomId) return;
    try {
      await messageApi.clearHistory('room', state.activeRoomId);
      dispatch({ type: 'SET_MESSAGES', roomId: state.activeRoomId, messages: [] });
    } catch { /* silently ignore — user stays in room */ }
    setClearRoomConfirm(false);
  }

  async function handleClearPMHistory() {
    if (!pmState.activePM) return;
    // Extract partner's user_id from the first available msg_id in the thread.
    // msg_id format: pm-{senderID}-{recipientID}-{UnixNano}
    // The partner's ID is whichever of parts[1]/parts[2] is NOT the current user's ID.
    const thread = pmState.threads[pmState.activePM] || [];
    const msgWithId = thread.find(m => m.msg_id?.startsWith('pm-'));
    if (!msgWithId) return; // no persisted messages — nothing to clear
    const parts = msgWithId.msg_id.split('-');
    const id1 = Number.parseInt(parts[1], 10);
    const id2 = Number.parseInt(parts[2], 10);
    const partnerId = id1 === user.user_id ? id2 : id1;
    if (!partnerId || Number.isNaN(partnerId)) return;
    try {
      await messageApi.clearHistory('pm', partnerId);
      pmDispatch({ type: 'CLEAR_PM_THREAD', username: pmState.activePM });
    } catch { /* silently ignore */ }
  }

  // ── Derived values ────────────────────────────────────────────────────────
  const activeRoom = state.rooms.find(r => r.id === state.activeRoomId) || null;
  const activeMessages = state.messages[state.activeRoomId] || [];
  const activeUsers = state.onlineUsers[state.activeRoomId] || [];
  const activeAdmins = state.admins[state.activeRoomId] || [];
  const activeMuted = state.mutedUsers[state.activeRoomId] || [];
  const activeTypingUsers = state.typingUsers[state.activeRoomId];
  const isCurrentUserAdmin = activeAdmins.includes(user?.username);

  const pmMessages = pmState.activePM
    ? (pmState.threads[pmState.activePM] || []).map(m => ({
        from: m.from,
        text: m.text,
        msg_id: m.msg_id,
        edited_at: m.edited_at,
        is_deleted: m.is_deleted,
        reactions: m.reactions,
      }))
    : [];

  // isRecipientOnline is false only when we've positively observed the PM recipient
  // leave every tracked room (knownOfflineUsers), avoiding false-positive offline banners
  // for users who are online but not in any shared room.
  const isRecipientOnline = pmState.activePM
    ? !state.knownOfflineUsers.has(pmState.activePM)
    : true;

  const lastReadMessageId = state.readPositions[state.activeRoomId] || null;

  const showRoom = !!state.activeRoomId;
  const showPM = !showRoom && !!pmState.activePM;

  // Debounced mark-as-read: when the user scrolls to the bottom, wait 1s
  // then persist the last message as read. This avoids flooding the server
  // with mark_read messages during rapid scrolling.
  const debouncedMarkAsRead = useCallback(() => {
    if (markAsReadTimerRef.current) clearTimeout(markAsReadTimerRef.current);
    markAsReadTimerRef.current = setTimeout(() => {
      // Don't mark as read if the tab isn't visible — prevents updating read
      // position on a background tab the user hasn't actually looked at.
      if (document.hidden) return;
      const roomId = state.activeRoomId;
      if (!roomId) return;
      const msgs = state.messages[roomId];
      if (!msgs || msgs.length === 0) return;
      // Find the last message with a msg_id (system messages don't have one)
      for (let j = msgs.length - 1; j >= 0; j--) {
        if (msgs[j].msg_id) {
          markAsRead(roomId, msgs[j].msg_id);
          break;
        }
      }
    }, 1000);
  }, [state.activeRoomId, state.messages, markAsRead]);

  // Auto-mark as read when selecting a room (if user can see all messages)
  useEffect(() => {
    if (!state.activeRoomId) return;
    debouncedMarkAsRead();
    return () => {
      if (markAsReadTimerRef.current) clearTimeout(markAsReadTimerRef.current);
    };
  }, [state.activeRoomId, debouncedMarkAsRead]);

  const handleRoomScrollBottom = useCallback(() => {
    if (state.activeRoomId) {
      dispatch({ type: 'CLEAR_UNREAD', roomId: state.activeRoomId });
      debouncedMarkAsRead();
    }
  }, [state.activeRoomId, dispatch, debouncedMarkAsRead]);

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
              <span className="header-room-name">{activeRoom.name}</span>
              <span className="header-room-sep">|</span>
              <span className="header-room-sub">Team Discussion</span>
            </div>
          )}
        </div>

        {/* Right: user + actions */}
        <div className="chat-header-actions">
          <button onClick={() => setSearchOpen(true)} className="btn-ghost search-trigger-btn" aria-label="Search messages" title="Search messages (Ctrl+K)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            Search
          </button>
          <ConnectionStatus status={connectionStatus} />
          <UserDropdown user={user} onLogout={handleLogout} />
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
            <div className="drag-handle" />
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
                />
              </div>
            </aside>
          </div>

          {/* Center message panel */}
          <div key="messages" className="glass-panel">
            <div className="drag-handle" />
            <main className="center-panel" style={{ flex: 1, overflow: 'hidden', background: 'transparent' }}>
              {showRoom && (
                <>
                  {/* Room sub-header with clear history */}
                  <div className="room-panel-header">
                    <span className="room-panel-name">{activeRoom?.name}</span>
                    {clearRoomConfirm ? (
                      <div className="clear-history-confirm" data-testid="clear-room-confirm">
                        <span className="clear-history-label">Clear all history?</span>
                        <button className="btn-danger-xs" onClick={handleClearRoomHistory} data-testid="clear-room-yes">Yes</button>
                        <button className="btn-ghost-xs" onClick={() => setClearRoomConfirm(false)} data-testid="clear-room-no">Cancel</button>
                      </div>
                    ) : (
                      <button
                        className="btn-icon-sm clear-history-btn"
                        onClick={() => setClearRoomConfirm(true)}
                        title="Clear room history"
                        data-testid="clear-room-history"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6"/>
                          <path d="M19 6l-1 14H6L5 6"/>
                          <path d="M10 11v6M14 11v6"/>
                          <path d="M9 6V4h6v2"/>
                        </svg>
                      </button>
                    )}
                  </div>
                  <MessageList
                    messages={activeMessages}
                    onScrollToBottom={handleRoomScrollBottom}
                    currentUser={user?.username}
                    lastReadMessageId={lastReadMessageId}
                    onEditMessage={handleEditMessage}
                    onDeleteMessage={handleDeleteMessage}
                    onAddReaction={handleAddReaction}
                    onRemoveReaction={handleRemoveReaction}
                    highlightMessageId={highlightMessageId}
                  />
                  <TypingIndicator typingUsers={activeTypingUsers} />
                </>
              )}
              {showPM && (
                <PMView
                  username={pmState.activePM}
                  messages={pmMessages}
                  onScrollToBottom={handlePMScrollBottom}
                  isOnline={isRecipientOnline}
                  currentUser={user?.username}
                  onEditMessage={handlePMEditMessage}
                  onDeleteMessage={handlePMDeleteMessage}
                  onAddReaction={handlePMAddReaction}
                  onRemoveReaction={handlePMRemoveReaction}
                  onClearHistory={handleClearPMHistory}
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
            <div className="drag-handle" />
            <div style={{ padding: '0 12px 12px', display: 'flex', flexDirection: 'column', justifyContent: 'center', flex: 1 }}>
              {showRoom ? (
                <MessageInput
                  onSend={handleSend}
                  roomName={activeRoom?.name}
                  roomId={state.activeRoomId}
                  onTyping={() => sendTyping(state.activeRoomId)}
                  editingMessage={editingMessage}
                  onCancelEdit={handleCancelEdit}
                />
              ) : showPM ? (
                <MessageInput
                  onSend={handleSendPM}
                  roomName={pmState.activePM}
                  isPM
                  editingMessage={editingPMMessage}
                  onCancelEdit={() => setEditingPMMessage(null)}
                />
              ) : (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>Select a conversation to type...</div>
              )}
            </div>
          </div>

          {/* Right panel */}
          <div key="users" className="glass-panel">
            <div className="drag-handle" />
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

      {/* Search modal (Ctrl+K) */}
      <SearchModal
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        rooms={state.rooms ?? []}
        onNavigate={handleSearchNavigate}
      />
    </div>
  );
}
