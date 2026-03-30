import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

// Mock react-grid-layout to avoid ResizeObserver/layout complexity in jsdom
vi.mock('react-grid-layout', () => ({
  Responsive: ({ children }) => <div data-testid="grid-layout">{children}</div>,
}));
vi.mock('react-grid-layout/legacy', () => ({
  WidthProvider: (Component) => Component,
}));
vi.mock('react-grid-layout/css/styles.css', () => ({}));
vi.mock('react-resizable/css/styles.css', () => ({}));

// Mock all child components to keep tests focused on ChatPage logic
vi.mock('../../components/common/Logo', () => ({
  default: () => <span data-testid="logo">Logo</span>,
}));
vi.mock('../../components/room/RoomList', () => ({
  default: ({ rooms, onSelect }) => (
    <div data-testid="room-list">
      {rooms.map(r => (
        <button key={r.id} data-testid={`room-${r.id}`} onClick={() => onSelect(r.id)}>
          {r.name}
        </button>
      ))}
    </div>
  ),
}));
vi.mock('../../components/chat/MessageList', () => ({
  default: ({ onScrollToBottom, onEditMessage, onDeleteMessage, onAddReaction, onRemoveReaction }) => (
    <div data-testid="message-list">
      <button data-testid="trigger-scroll-bottom" onClick={onScrollToBottom}>scroll</button>
      <button data-testid="trigger-edit" onClick={() => onEditMessage({ msg_id: 'msg1', text: 'hello' })}>edit</button>
      <button data-testid="trigger-delete" onClick={() => onDeleteMessage({ msg_id: 'msg1' })}>delete</button>
      <button data-testid="trigger-add-reaction" onClick={() => onAddReaction('msg1', '👍')}>react</button>
      <button data-testid="trigger-remove-reaction" onClick={() => onRemoveReaction('msg1', '👍')}>unreact</button>
    </div>
  ),
}));
vi.mock('../../components/chat/MessageInput', () => ({
  default: ({ onSend, onTyping, editingMessage, onCancelEdit }) => (
    <div data-testid="message-input">
      <button data-testid="trigger-send" onClick={() => onSend('test message', editingMessage?.msg_id)}>send</button>
      {editingMessage && (
        <>
          <span data-testid="editing-indicator">Editing: {editingMessage.text}</span>
          <button data-testid="trigger-cancel-edit" onClick={onCancelEdit}>cancel</button>
        </>
      )}
      <button data-testid="trigger-typing" onClick={onTyping}>typing</button>
    </div>
  ),
}));
vi.mock('../../components/chat/TypingIndicator', () => ({
  default: ({ typingUsers }) => (
    <div data-testid="typing-indicator">{Object.keys(typingUsers || {}).join(',')}</div>
  ),
}));
vi.mock('../../components/room/UserList', () => ({
  default: () => <div data-testid="user-list">Users</div>,
}));
vi.mock('../../components/pm/PMList', () => ({
  default: ({ onSelectPM }) => (
    <div data-testid="pm-list">
      <button data-testid="open-pm" onClick={() => onSelectPM('alice')}>PM alice</button>
    </div>
  ),
}));
vi.mock('../../components/pm/PMView', () => ({
  default: () => <div data-testid="pm-view">PM View</div>,
}));
vi.mock('../../components/common/ConnectionStatus', () => ({
  default: ({ status }) => <div data-testid="connection-status">{status}</div>,
}));
vi.mock('../../components/settings/SettingsModal', () => ({
  default: ({ open, onClose }) =>
    open ? (
      <div data-testid="settings-modal">
        <button data-testid="close-settings" onClick={onClose}>Close</button>
      </div>
    ) : null,
}));
vi.mock('../../components/chat/SearchModal', () => ({
  default: ({ isOpen, onClose, onNavigate }) =>
    isOpen ? (
      <div data-testid="search-modal">
        <button data-testid="close-search" onClick={onClose}>Close</button>
        <button data-testid="navigate-search" onClick={() => onNavigate(42)}>Go to room 42</button>
      </div>
    ) : null,
}));

// Mock APIs
vi.mock('../../services/pmApi', () => ({
  sendPM: vi.fn().mockResolvedValue({}),
}));
vi.mock('../../services/authApi', () => ({
  logout: vi.fn().mockResolvedValue({}),
}));

// ── Context mocks ─────────────────────────────────────────────────────────────

const mockDispatch = vi.fn();
const mockPmDispatch = vi.fn();
const mockJoinRoom = vi.fn();
const mockExitRoom = vi.fn();
const mockDisconnectAll = vi.fn();
const mockSendMessage = vi.fn();
const mockSendTyping = vi.fn();
const mockMarkAsRead = vi.fn();
const mockLogout = vi.fn();

const defaultChatState = {
  rooms: [
    { id: 1, name: 'general', is_active: true },
    { id: 2, name: 'random', is_active: true },
  ],
  activeRoomId: 1,
  joinedRooms: new Set([1]),
  unreadCounts: {},
  messages: { 1: [{ from: 'alice', text: 'Hello', msg_id: 'msg1' }] },
  onlineUsers: { 1: ['alice', 'bob'] },
  admins: { 1: [] },
  mutedUsers: { 1: [] },
  typingUsers: { 1: {} },
  readPositions: {},
  knownOfflineUsers: new Set(),
};

const defaultPmState = {
  threads: {},
  pmUnread: {},
  activePM: null,
};

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(),
}));
vi.mock('../../context/ChatContext', () => ({
  useChat: vi.fn(),
}));
vi.mock('../../context/PMContext', () => ({
  usePM: vi.fn(),
}));
vi.mock('../../layouts/ChatConnectionLayer', () => ({
  useChatConnection: vi.fn(),
}));

import { useAuth } from '../../context/AuthContext';
import { useChat } from '../../context/ChatContext';
import { usePM } from '../../context/PMContext';
import { useChatConnection } from '../../layouts/ChatConnectionLayer';
import * as authApi from '../../services/authApi';

// ── Helpers ───────────────────────────────────────────────────────────────────

function setupMocks({
  user = { username: 'testuser', is_global_admin: false },
  chatState = defaultChatState,
  pmState = defaultPmState,
} = {}) {
  useAuth.mockReturnValue({ user, logout: mockLogout });
  useChat.mockReturnValue({ state: chatState, dispatch: mockDispatch });
  usePM.mockReturnValue({ pmState, pmDispatch: mockPmDispatch });
  useChatConnection.mockReturnValue({
    joinRoom: mockJoinRoom,
    exitRoom: mockExitRoom,
    disconnectAll: mockDisconnectAll,
    sendMessage: mockSendMessage,
    sendTyping: mockSendTyping,
    markAsRead: mockMarkAsRead,
    connectionStatus: 'connected',
  });
}

import ChatPage from '../ChatPage';

function renderChatPage(options = {}) {
  setupMocks(options);
  return render(
    <MemoryRouter>
      <ChatPage />
    </MemoryRouter>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Basic rendering ───────────────────────────────────────────────────────

  it('renders the page header with logo and user badge', () => {
    renderChatPage();
    expect(screen.getByTestId('logo')).toBeInTheDocument();
    expect(screen.getByText('testuser')).toBeInTheDocument();
  });

  it('renders connection status indicator', () => {
    renderChatPage();
    expect(screen.getByTestId('connection-status')).toHaveTextContent('connected');
  });

  it('renders the active room name in the header', () => {
    renderChatPage();
    expect(screen.getByText('#general')).toBeInTheDocument();
  });

  it('renders MessageList when a room is active', () => {
    renderChatPage();
    expect(screen.getByTestId('message-list')).toBeInTheDocument();
  });

  it('renders TypingIndicator when a room is active', () => {
    renderChatPage();
    expect(screen.getByTestId('typing-indicator')).toBeInTheDocument();
  });

  it('renders MessageInput when a room is active', () => {
    renderChatPage();
    expect(screen.getByTestId('message-input')).toBeInTheDocument();
  });

  it('shows empty-state when no room or PM is active', () => {
    renderChatPage({
      chatState: { ...defaultChatState, activeRoomId: null },
    });
    expect(screen.getByText('No conversation selected')).toBeInTheDocument();
  });

  it('shows PMView instead of MessageList when PM is active', () => {
    renderChatPage({
      chatState: { ...defaultChatState, activeRoomId: null },
      pmState: { ...defaultPmState, activePM: 'alice' },
    });
    expect(screen.getByTestId('pm-view')).toBeInTheDocument();
    expect(screen.queryByTestId('message-list')).toBeNull();
  });

  it('does NOT show Admin button for non-admin users', () => {
    renderChatPage({ user: { username: 'testuser', is_global_admin: false } });
    expect(screen.queryByText('Admin')).toBeNull();
  });

  it('shows Admin button for global admin users', () => {
    renderChatPage({ user: { username: 'admin', is_global_admin: true } });
    expect(screen.getByText('Admin')).toBeInTheDocument();
  });

  // ── Settings modal ────────────────────────────────────────────────────────

  it('opens Settings modal when settings button is clicked', async () => {
    const user = userEvent.setup();
    renderChatPage();

    expect(screen.queryByTestId('settings-modal')).toBeNull();
    await user.click(screen.getByLabelText('Settings'));
    expect(screen.getByTestId('settings-modal')).toBeInTheDocument();
  });

  it('closes Settings modal when its onClose fires', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByLabelText('Settings'));
    await user.click(screen.getByTestId('close-settings'));
    expect(screen.queryByTestId('settings-modal')).toBeNull();
  });

  // ── Search modal ──────────────────────────────────────────────────────────

  it('opens Search modal when search button is clicked', async () => {
    const user = userEvent.setup();
    renderChatPage();

    expect(screen.queryByTestId('search-modal')).toBeNull();
    await user.click(screen.getByLabelText('Search messages'));
    expect(screen.getByTestId('search-modal')).toBeInTheDocument();
  });

  it('opens Search modal via Ctrl+K keyboard shortcut', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.keyboard('{Control>}k{/Control}');
    expect(screen.getByTestId('search-modal')).toBeInTheDocument();
  });

  it('closes Search modal when its onClose fires', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByLabelText('Search messages'));
    await user.click(screen.getByTestId('close-search'));
    expect(screen.queryByTestId('search-modal')).toBeNull();
  });

  it('navigates to a room from search — joins if not in joinedRooms', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByLabelText('Search messages'));
    // navigate-search button calls onNavigate(42) — room 42 is NOT in joinedRooms
    await user.click(screen.getByTestId('navigate-search'));

    expect(mockJoinRoom).toHaveBeenCalledWith(42);
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_ACTIVE_ROOM', roomId: 42 });
  });

  // ── Message actions ───────────────────────────────────────────────────────

  it('puts ChatPage into edit mode when onEditMessage fires', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByTestId('trigger-edit'));
    expect(screen.getByTestId('editing-indicator')).toHaveTextContent('Editing: hello');
  });

  it('cancels edit mode when onCancelEdit fires', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByTestId('trigger-edit'));
    await user.click(screen.getByTestId('trigger-cancel-edit'));
    expect(screen.queryByTestId('editing-indicator')).toBeNull();
  });

  it('sends edit_message WS event when in edit mode and onSend fires', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByTestId('trigger-edit'));
    await user.click(screen.getByTestId('trigger-send'));

    expect(mockSendMessage).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ type: 'edit_message', msg_id: 'msg1' }),
    );
  });

  it('sends a regular message event when not in edit mode', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByTestId('trigger-send'));
    expect(mockSendMessage).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ type: 'message', text: 'test message' }),
    );
  });

  it('does not send message when no active room', () => {
    renderChatPage({ chatState: { ...defaultChatState, activeRoomId: null } });

    // MessageInput is not rendered in empty state
    expect(screen.queryByTestId('trigger-send')).toBeNull();
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('sends delete_message WS event via onDeleteMessage', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByTestId('trigger-delete'));
    expect(mockSendMessage).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ type: 'delete_message', msg_id: 'msg1' }),
    );
  });

  it('sends add_reaction WS event via onAddReaction', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByTestId('trigger-add-reaction'));
    expect(mockSendMessage).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ type: 'add_reaction', msg_id: 'msg1', emoji: '👍' }),
    );
  });

  it('sends remove_reaction WS event via onRemoveReaction', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByTestId('trigger-remove-reaction'));
    expect(mockSendMessage).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ type: 'remove_reaction', msg_id: 'msg1', emoji: '👍' }),
    );
  });

  it('calls sendTyping when onTyping fires from MessageInput', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByTestId('trigger-typing'));
    expect(mockSendTyping).toHaveBeenCalledWith(1);
  });

  // ── Room scroll / mark as read ────────────────────────────────────────────

  it('dispatches CLEAR_UNREAD on scroll to bottom', () => {
    renderChatPage();

    fireEvent.click(screen.getByTestId('trigger-scroll-bottom'));
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'CLEAR_UNREAD', roomId: 1 });
  });

  it('calls markAsRead after 1s debounce when scrolling to bottom', async () => {
    vi.useFakeTimers();
    try {
      setupMocks();
      render(
        <MemoryRouter>
          <ChatPage />
        </MemoryRouter>,
      );

      fireEvent.click(screen.getByTestId('trigger-scroll-bottom'));
      // markAsRead is debounced — should NOT be called immediately
      expect(mockMarkAsRead).not.toHaveBeenCalled();

      // Advance past the 1s debounce
      await act(async () => {
        vi.advanceTimersByTime(1100);
      });

      expect(mockMarkAsRead).toHaveBeenCalledWith(1, 'msg1');
    } finally {
      vi.useRealTimers();
    }
  });

  // ── Admin navigation ──────────────────────────────────────────────────────

  it('navigates to /admin when Admin button is clicked', async () => {
    const user = userEvent.setup();
    renderChatPage({ user: { username: 'admin', is_global_admin: true } });

    await user.click(screen.getByText('Admin'));
    expect(mockNavigate).toHaveBeenCalledWith('/admin');
  });

  // ── Logout ────────────────────────────────────────────────────────────────

  it('calls disconnectAll, authApi.logout, logout context, and navigates to /login', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByText('Logout'));

    expect(mockDisconnectAll).toHaveBeenCalled();
    await act(async () => {}); // flush the async authApi.logout()
    expect(authApi.logout).toHaveBeenCalled();
    expect(mockLogout).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/login');
  });

  // ── Layout persistence ────────────────────────────────────────────────────

  it('loads layouts from localStorage if present', () => {
    const saved = JSON.stringify({ lg: [{ i: 'sidebar', x: 0, y: 0, w: 2, h: 5 }] });
    localStorage.setItem('chatbox-chat-layouts', saved);
    renderChatPage();
    localStorage.removeItem('chatbox-chat-layouts');
    // No throw === pass
  });

  it('falls back to defaultLayouts when localStorage value is invalid JSON', () => {
    localStorage.setItem('chatbox-chat-layouts', 'not-valid-json');
    renderChatPage();
    localStorage.removeItem('chatbox-chat-layouts');
    // No throw === pass
  });
});
