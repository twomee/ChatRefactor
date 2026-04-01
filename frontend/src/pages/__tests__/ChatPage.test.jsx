import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
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
  default: ({ onKick, onMute, onUnmute, onPromote, onStartPM }) => (
    <div data-testid="user-list">
      <button data-testid="trigger-kick" onClick={() => onKick('bob')}>Kick</button>
      <button data-testid="trigger-mute" onClick={() => onMute('bob')}>Mute</button>
      <button data-testid="trigger-unmute" onClick={() => onUnmute('bob')}>Unmute</button>
      <button data-testid="trigger-promote" onClick={() => onPromote('bob')}>Promote</button>
      <button data-testid="trigger-start-pm" onClick={() => onStartPM('bob')}>PM</button>
    </div>
  ),
}));
vi.mock('../../components/pm/PMList', () => ({
  default: ({ onSelectPM }) => (
    <div data-testid="pm-list">
      <button data-testid="open-pm" onClick={() => onSelectPM('alice')}>PM alice</button>
      <button data-testid="open-pm-bob" onClick={() => onSelectPM('bob')}>PM bob</button>
    </div>
  ),
}));
vi.mock('../../components/pm/PMView', () => ({
  default: ({ onScrollToBottom, onClearHistory }) => (
    <div data-testid="pm-view">
      <button data-testid="pm-scroll-bottom" onClick={onScrollToBottom}>scroll</button>
      <button data-testid="pm-clear-history" onClick={onClearHistory}>clear</button>
    </div>
  ),
}));
vi.mock('../../components/common/ConnectionStatus', () => ({
  default: ({ status }) => <div data-testid="connection-status">{status}</div>,
}));
vi.mock('../../components/common/UserDropdown', () => ({
  default: ({ user, onLogout }) => (
    <div data-testid="user-dropdown">
      <span>{user?.username}</span>
      <button data-testid="dropdown-logout" onClick={onLogout}>Logout</button>
    </div>
  ),
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

vi.mock('../../services/messageApi', () => ({
  clearHistory: vi.fn().mockResolvedValue({}),
  editMessage: vi.fn().mockResolvedValue({}),
  deleteMessage: vi.fn().mockResolvedValue({}),
}));

// Mock APIs
vi.mock('../../services/pmApi', () => ({
  sendPM: vi.fn().mockResolvedValue({}),
  getPMHistory: vi.fn().mockResolvedValue({ data: [] }),
  editPM: vi.fn().mockResolvedValue({}),
  deletePM: vi.fn().mockResolvedValue({}),
  addPMReaction: vi.fn().mockResolvedValue({}),
  removePMReaction: vi.fn().mockResolvedValue({}),
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
const mockSendPMTyping = vi.fn();
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
  loadedThreads: {},
  deletedPMs: {},
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
import * as pmApi from '../../services/pmApi';
import * as messageApi from '../../services/messageApi';
import { savePMThreadList } from '../../utils/storage';

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
    sendPMTyping: mockSendPMTyping,
    markAsRead: mockMarkAsRead,
    connectionStatus: 'connected',
  });
}

import ChatPage from '../ChatPage';
import { ToastProvider } from '../../context/ToastContext';

function renderChatPage(options = {}) {
  setupMocks(options);
  return render(
    <ToastProvider>
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    </ToastProvider>,
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
    const headerRoomName = document.querySelector('.header-room-name');
    expect(headerRoomName).toBeInTheDocument();
    expect(headerRoomName).toHaveTextContent('general');
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

  // ── UserDropdown ─────────────────────────────────────────────────────────

  it('renders UserDropdown component', () => {
    renderChatPage();
    expect(screen.getByTestId('user-dropdown')).toBeInTheDocument();
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
        <ToastProvider>
          <MemoryRouter>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>,
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

  // ── Logout via UserDropdown ──────────────────────────────────────────────

  it('calls disconnectAll, authApi.logout, logout context, and navigates to /login', async () => {
    const user = userEvent.setup();
    renderChatPage();

    await user.click(screen.getByTestId('dropdown-logout'));

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

// ── PM view ───────────────────────────────────────────────────────────────────

describe('PM view', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders PM MessageInput when PM is active and no room is selected', () => {
    renderChatPage({
      chatState: { ...defaultChatState, activeRoomId: null },
      pmState: { ...defaultPmState, activePM: 'alice' },
    });
    // PM MessageInput should be in the input panel
    expect(screen.getByTestId('message-input')).toBeInTheDocument();
  });

  it('dispatches CLEAR_PM_UNREAD when PM message list scrolls to bottom', async () => {
    const user = userEvent.setup();
    renderChatPage({
      chatState: { ...defaultChatState, activeRoomId: null },
      pmState: { ...defaultPmState, activePM: 'alice' },
    });
    await user.click(screen.getByTestId('pm-scroll-bottom'));
    expect(mockPmDispatch).toHaveBeenCalledWith({ type: 'CLEAR_PM_UNREAD', username: 'alice' });
  });

  it('clears PM thread locally when onClearHistory fires with no msg_id', async () => {
    const user = userEvent.setup();
    renderChatPage({
      chatState: { ...defaultChatState, activeRoomId: null },
      pmState: {
        ...defaultPmState,
        activePM: 'alice',
        threads: { alice: [{ from: 'alice', text: 'hi', msg_id: null }] },
      },
    });
    await user.click(screen.getByTestId('pm-clear-history'));
    expect(mockPmDispatch).toHaveBeenCalledWith({ type: 'CLEAR_PM_THREAD', username: 'alice' });
  });

  it('calls messageApi.clearHistory when partner msg_id is available', async () => {
    const user = userEvent.setup();
    // msg_id format: pm-{senderId}-{recipientId}-{timestamp}
    // alice is the partner (sender), so parts[1] = partnerId
    renderChatPage({
      chatState: { ...defaultChatState, activeRoomId: null },
      pmState: {
        ...defaultPmState,
        activePM: 'alice',
        threads: { alice: [{ from: 'alice', text: 'hi', msg_id: 'pm-7-3-1234567890' }] },
      },
    });
    await user.click(screen.getByTestId('pm-clear-history'));
    await waitFor(() => {
      expect(messageApi.clearHistory).toHaveBeenCalledWith('pm', 7);
    });
  });
});

// ── Muted banner ──────────────────────────────────────────────────────────────

describe('muted banner', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows muted banner instead of MessageInput when current user is muted', () => {
    renderChatPage({
      chatState: { ...defaultChatState, mutedUsers: { 1: ['testuser'] } },
    });
    expect(screen.getByTestId('muted-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('message-input')).toBeNull();
  });

  it('does not show muted banner when user is not muted', () => {
    renderChatPage();
    expect(screen.queryByTestId('muted-banner')).toBeNull();
    expect(screen.getByTestId('message-input')).toBeInTheDocument();
  });
});

// ── Clear room history ─────────────────────────────────────────────────────────

describe('clear room history', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows confirmation dialog when clear button is clicked', async () => {
    const user = userEvent.setup();
    renderChatPage();
    await user.click(screen.getByTestId('clear-room-history'));
    expect(screen.getByTestId('clear-room-confirm')).toBeInTheDocument();
  });

  it('calls messageApi.clearHistory and dispatches SET_MESSAGES when confirmed', async () => {
    const user = userEvent.setup();
    renderChatPage();
    await user.click(screen.getByTestId('clear-room-history'));
    await user.click(screen.getByTestId('clear-room-yes'));
    await waitFor(() => {
      expect(messageApi.clearHistory).toHaveBeenCalledWith('room', 1);
      expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_MESSAGES', roomId: 1, messages: [] });
    });
  });

  it('dismisses confirmation without calling API when Cancel is clicked', async () => {
    const user = userEvent.setup();
    renderChatPage();
    await user.click(screen.getByTestId('clear-room-history'));
    await user.click(screen.getByTestId('clear-room-no'));
    expect(screen.queryByTestId('clear-room-confirm')).toBeNull();
    expect(messageApi.clearHistory).not.toHaveBeenCalled();
  });
});

// ── UserList action handlers ───────────────────────────────────────────────────

describe('UserList action handlers', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sends kick WS message when onKick fires', async () => {
    const user = userEvent.setup();
    renderChatPage();
    await user.click(screen.getByTestId('trigger-kick'));
    expect(mockSendMessage).toHaveBeenCalledWith(1, expect.objectContaining({ type: 'kick', target: 'bob' }));
  });

  it('sends mute WS message when onMute fires', async () => {
    const user = userEvent.setup();
    renderChatPage();
    await user.click(screen.getByTestId('trigger-mute'));
    expect(mockSendMessage).toHaveBeenCalledWith(1, expect.objectContaining({ type: 'mute', target: 'bob' }));
  });

  it('sends unmute WS message when onUnmute fires', async () => {
    const user = userEvent.setup();
    renderChatPage();
    await user.click(screen.getByTestId('trigger-unmute'));
    expect(mockSendMessage).toHaveBeenCalledWith(1, expect.objectContaining({ type: 'unmute', target: 'bob' }));
  });

  it('sends promote WS message when onPromote fires', async () => {
    const user = userEvent.setup();
    renderChatPage();
    await user.click(screen.getByTestId('trigger-promote'));
    expect(mockSendMessage).toHaveBeenCalledWith(1, expect.objectContaining({ type: 'promote', target: 'bob' }));
  });

  it('opens a PM thread when onStartPM fires', async () => {
    const user = userEvent.setup();
    renderChatPage();
    await user.click(screen.getByTestId('trigger-start-pm'));
    expect(mockPmDispatch).toHaveBeenCalledWith({ type: 'SET_ACTIVE_PM', username: 'bob' });
    expect(mockPmDispatch).toHaveBeenCalledWith({ type: 'CLEAR_PM_UNREAD', username: 'bob' });
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_ACTIVE_ROOM', roomId: null });
  });
});

// ── Search navigation ──────────────────────────────────────────────────────────

describe('search navigation', () => {
  beforeEach(() => vi.clearAllMocks());

  it('does NOT call joinRoom when navigating to a room already in joinedRooms', async () => {
    const user = userEvent.setup();
    // Room 1 is already in joinedRooms (default state)
    renderChatPage({
      chatState: { ...defaultChatState, joinedRooms: new Set([1, 42]) },
    });
    await user.click(screen.getByLabelText('Search messages'));
    await user.click(screen.getByTestId('navigate-search')); // navigates to room 42
    expect(mockJoinRoom).not.toHaveBeenCalled();
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_ACTIVE_ROOM', roomId: 42 });
  });
});

// ── PM persistence on mount ────────────────────────────────────────────────────

describe('PM persistence on mount', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('dispatches INIT_PM_THREAD for each saved PM thread on mount', async () => {
    savePMThreadList('testuser', ['bob', 'carol']);

    await act(async () => {
      renderChatPage({ user: { username: 'testuser', is_global_admin: false } });
    });

    expect(mockPmDispatch).toHaveBeenCalledWith({ type: 'INIT_PM_THREAD', username: 'bob' });
    expect(mockPmDispatch).toHaveBeenCalledWith({ type: 'INIT_PM_THREAD', username: 'carol' });
  });

  it('does not dispatch INIT_PM_THREAD when there are no saved threads', async () => {
    // No saved thread list — localStorage is clear

    await act(async () => {
      renderChatPage({ user: { username: 'testuser', is_global_admin: false } });
    });

    const initCalls = mockPmDispatch.mock.calls.filter(c => c[0]?.type === 'INIT_PM_THREAD');
    expect(initCalls).toHaveLength(0);
  });
});

// ── handleSelectPM lazy history loading ───────────────────────────────────────

describe('handleSelectPM lazy history loading', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('calls getPMHistory on first open and dispatches SET_PM_THREAD and MARK_THREAD_LOADED', async () => {
    const user = userEvent.setup();
    const historyMsg = {
      message_id: 'msg-1',
      sender_name: 'bob',
      content: 'hello',
      sent_at: new Date().toISOString(),
      is_private: true,
      reactions: [],
    };
    pmApi.getPMHistory.mockResolvedValue({ data: [historyMsg] });

    // loadedThreads is empty — 'bob' has not been loaded yet
    renderChatPage({
      pmState: { ...defaultPmState, loadedThreads: {} },
    });

    await user.click(screen.getByTestId('open-pm-bob'));
    await act(async () => {});

    expect(pmApi.getPMHistory).toHaveBeenCalledWith('bob');
    expect(mockPmDispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'SET_PM_THREAD', username: 'bob' }),
    );
    expect(mockPmDispatch).toHaveBeenCalledWith({ type: 'MARK_THREAD_LOADED', username: 'bob' });
  });

  it('does NOT call getPMHistory if thread is already loaded', async () => {
    const user = userEvent.setup();

    // loadedThreads marks 'bob' as already fetched
    renderChatPage({
      pmState: { ...defaultPmState, loadedThreads: { bob: true } },
    });

    await user.click(screen.getByTestId('open-pm-bob'));
    await act(async () => {});

    expect(pmApi.getPMHistory).not.toHaveBeenCalled();
    expect(mockPmDispatch).not.toHaveBeenCalledWith(
      expect.objectContaining({ type: 'MARK_THREAD_LOADED' }),
    );
  });

  it('always dispatches SET_ACTIVE_PM and CLEAR_PM_UNREAD regardless of loaded state', async () => {
    const user = userEvent.setup();

    renderChatPage({
      pmState: { ...defaultPmState, loadedThreads: { bob: true } },
    });

    await user.click(screen.getByTestId('open-pm-bob'));

    expect(mockPmDispatch).toHaveBeenCalledWith({ type: 'SET_ACTIVE_PM', username: 'bob' });
    expect(mockPmDispatch).toHaveBeenCalledWith({ type: 'CLEAR_PM_UNREAD', username: 'bob' });
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_ACTIVE_ROOM', roomId: null });
  });

  it('does not throw when getPMHistory rejects — thread stays empty', async () => {
    const user = userEvent.setup();
    pmApi.getPMHistory.mockRejectedValue(new Error('Network error'));

    renderChatPage({
      pmState: { ...defaultPmState, loadedThreads: {} },
    });

    // Should not throw
    await user.click(screen.getByTestId('open-pm-bob'));
    await act(async () => {});

    // MARK_THREAD_LOADED is still dispatched even on failure (so we don't retry on every click)
    expect(mockPmDispatch).toHaveBeenCalledWith({ type: 'MARK_THREAD_LOADED', username: 'bob' });
  });
});

// ── PM typing indicator ───────────────────────────────────────────────────────

describe('PM typing indicator', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders TypingIndicator in PM view when the active partner is typing', () => {
    const ts = Date.now();
    renderChatPage({
      pmState: {
        ...defaultPmState,
        activePM: 'alice',
        threads: { alice: [] },
        pmTypingUsers: { alice: ts },
      },
      chatState: { ...defaultChatState, activeRoomId: null, joinedRooms: new Set() },
    });

    const indicator = screen.getByTestId('typing-indicator');
    expect(indicator).toBeInTheDocument();
    expect(indicator.textContent).toContain('alice');
  });

  it('renders empty TypingIndicator when active PM partner is not typing', () => {
    renderChatPage({
      pmState: {
        ...defaultPmState,
        activePM: 'alice',
        threads: { alice: [] },
        pmTypingUsers: {},
      },
      chatState: { ...defaultChatState, activeRoomId: null, joinedRooms: new Set() },
    });

    const indicator = screen.getByTestId('typing-indicator');
    expect(indicator.textContent).toBe('');
  });

  it('calls sendPMTyping with the active PM username when typing in PM input', async () => {
    const user = userEvent.setup();
    renderChatPage({
      pmState: {
        ...defaultPmState,
        activePM: 'alice',
        threads: { alice: [] },
        pmTypingUsers: {},
      },
      chatState: { ...defaultChatState, activeRoomId: null, joinedRooms: new Set() },
    });

    await user.click(screen.getByTestId('trigger-typing'));
    expect(mockSendPMTyping).toHaveBeenCalledWith('alice');
  });

  it('does not show typing indicator for a different user than the active PM', () => {
    renderChatPage({
      pmState: {
        ...defaultPmState,
        activePM: 'alice',
        threads: { alice: [] },
        // bob is typing but alice is the active PM — indicator should be empty
        pmTypingUsers: { bob: Date.now() },
      },
      chatState: { ...defaultChatState, activeRoomId: null, joinedRooms: new Set() },
    });

    const indicator = screen.getByTestId('typing-indicator');
    expect(indicator.textContent).toBe('');
  });
});
