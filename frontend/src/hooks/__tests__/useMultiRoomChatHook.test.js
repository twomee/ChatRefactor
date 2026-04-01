// src/hooks/__tests__/useMultiRoomChatHook.test.js
// Tests for the useMultiRoomChat React hook (integration-level behaviour).
// The createHandleMessage factory and getBackoffDelay are covered in
// useMultiRoomChat.test.js; this file targets the hook's internal logic.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ── Module mocks ─────────────────────────────────────────────────────────────

vi.mock('../../utils/storage', () => ({
  getJoinedRooms: vi.fn(() => []),
  addJoinedRoom: vi.fn(),
  removeJoinedRoom: vi.fn(),
  addPMThread: vi.fn(),
}));

vi.mock('../../services/roomApi', () => ({
  listRooms: vi.fn(() => Promise.resolve({ status: 200, data: [] })),
  getMessagesSince: vi.fn(() => Promise.resolve({ status: 200, data: [] })),
}));

vi.mock('../../utils/notifications', () => ({
  requestNotificationPermission: vi.fn(),
  sendBrowserNotification: vi.fn(),
}));

vi.mock('../../config/constants', () => ({
  WS_BASE: 'ws://localhost:8003',
  API_BASE: 'http://localhost:8000',
}));

// Context mocks — defined here so tests can mutate them via .mockReturnValue
const mockDispatch = vi.fn();
const mockPmDispatch = vi.fn();
const mockShowToast = vi.fn();

vi.mock('../../context/ChatContext', () => ({
  useChat: vi.fn(),
}));
vi.mock('../../context/PMContext', () => ({
  usePM: vi.fn(),
}));
vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(),
}));
vi.mock('../../context/ToastContext', () => ({
  useToast: vi.fn(),
}));

import { useChat } from '../../context/ChatContext';
import { usePM } from '../../context/PMContext';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { getJoinedRooms } from '../../utils/storage';
import { useMultiRoomChat } from '../useMultiRoomChat';

// ── WebSocket mock factory ────────────────────────────────────────────────────
// WebSocket must be a class so `new WebSocket(...)` works correctly.

let wsInstances;

class MockWebSocket {
  constructor(url) {
    this.url = url;
    this.send = vi.fn();
    this.close = vi.fn();
    this.readyState = MockWebSocket.OPEN;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    wsInstances.push(this);
  }
}
MockWebSocket.OPEN = 1;
MockWebSocket.CLOSING = 2;
MockWebSocket.CLOSED = 3;

// ── Default state fixtures ────────────────────────────────────────────────────

const defaultChatState = {
  activeRoomId: null,
  rooms: [],
  messages: {},
  onlineUsers: {},
  admins: {},
  mutedUsers: {},
  typingUsers: {},
  readPositions: {},
  joinedRooms: new Set(),
  unreadCounts: {},
  knownOfflineUsers: new Set(),
};

const defaultPmState = {
  threads: {},
  pmUnread: {},
  activePM: null,
  loadedThreads: {},
};

function setupContextMocks(overrides = {}) {
  useChat.mockReturnValue({ state: overrides.chatState ?? defaultChatState, dispatch: mockDispatch });
  usePM.mockReturnValue({ pmState: overrides.pmState ?? defaultPmState, pmDispatch: mockPmDispatch });
  useAuth.mockReturnValue({ token: 'test-token', user: { username: 'alice' } });
  useToast.mockReturnValue({ showToast: mockShowToast });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useMultiRoomChat hook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    wsInstances = [];
    globalThis.WebSocket = MockWebSocket;
    setupContextMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ── Initialization ──────────────────────────────────────────────────────────

  it('initializes with connectionStatus = "connected"', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    expect(result.current.connectionStatus).toBe('connected');
  });

  it('returns all expected function handles', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    const { joinRoom, exitRoom, exitAllRooms, disconnectAll, sendMessage, sendTyping, markAsRead } = result.current;
    expect(typeof joinRoom).toBe('function');
    expect(typeof exitRoom).toBe('function');
    expect(typeof exitAllRooms).toBe('function');
    expect(typeof disconnectAll).toBe('function');
    expect(typeof sendMessage).toBe('function');
    expect(typeof sendTyping).toBe('function');
    expect(typeof markAsRead).toBe('function');
  });

  it('creates a lobby WebSocket on mount', () => {
    renderHook(() => useMultiRoomChat());
    // At least one WS created for the lobby
    expect(wsInstances.some(ws => ws.url.includes('/ws/lobby'))).toBe(true);
  });

  it('restores joined rooms from localStorage on mount', () => {
    getJoinedRooms.mockReturnValue([1, 2]);
    renderHook(() => useMultiRoomChat());
    expect(wsInstances.some(ws => ws.url.includes('/ws/1'))).toBe(true);
    expect(wsInstances.some(ws => ws.url.includes('/ws/2'))).toBe(true);
  });

  // ── joinRoom ────────────────────────────────────────────────────────────────

  it('creates a WebSocket for a new room', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    const countBefore = wsInstances.length;
    act(() => result.current.joinRoom(5));
    expect(wsInstances.length).toBeGreaterThan(countBefore);
    expect(wsInstances.some(ws => ws.url.includes('/ws/5'))).toBe(true);
  });

  it('does not open a second socket if the room is already joined', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(5));
    const countBefore = wsInstances.length;
    act(() => result.current.joinRoom(5));
    expect(wsInstances.length).toBe(countBefore);
  });

  it('dispatches JOIN_ROOM when joining a new room', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(5));
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'JOIN_ROOM', roomId: 5 });
  });

  it('passes silent param in WS URL when silent: true', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(5, { silent: true }));
    expect(wsInstances.some(ws => ws.url.includes('silent=1'))).toBe(true);
  });

  // ── exitRoom ────────────────────────────────────────────────────────────────

  it('closes the socket and dispatches EXIT_ROOM', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(3));
    const ws = wsInstances.find(w => w.url.includes('/ws/3'));
    expect(ws).toBeDefined();

    act(() => result.current.exitRoom(3));
    expect(ws.close).toHaveBeenCalled();
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'EXIT_ROOM', roomId: 3 });
  });

  it('does nothing when exiting a room that has no socket', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    expect(() => act(() => result.current.exitRoom(999))).not.toThrow();
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'EXIT_ROOM', roomId: 999 });
  });

  // ── sendMessage ──────────────────────────────────────────────────────────────

  it('sends JSON payload through the room socket', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(2));

    // Simulate socket open
    const ws = wsInstances[wsInstances.length - 1];
    ws.readyState = MockWebSocket.OPEN;

    act(() => result.current.sendMessage(2, { type: 'message', text: 'hello' }));
    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'message', text: 'hello' }));
  });

  it('does not send when socket is not open', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(2));
    const ws = wsInstances[wsInstances.length - 1];
    ws.readyState = MockWebSocket.CLOSED;

    act(() => result.current.sendMessage(2, { type: 'message', text: 'hello' }));
    expect(ws.send).not.toHaveBeenCalled();
  });

  it('does nothing when sendMessage is called for a room with no socket', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    expect(() => act(() => result.current.sendMessage(999, { type: 'message' }))).not.toThrow();
  });

  // ── sendTyping ───────────────────────────────────────────────────────────────

  it('sends typing event through the room socket', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(4));
    const ws = wsInstances[wsInstances.length - 1];
    ws.readyState = MockWebSocket.OPEN;

    act(() => result.current.sendTyping(4));
    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'typing' }));
  });

  // ── sendPMTyping ──────────────────────────────────────────────────────────────

  it('sends typing_pm event through the lobby socket', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    const lobbyWs = wsInstances.find(ws => ws.url.includes('/ws/lobby'));
    expect(lobbyWs).toBeDefined();
    lobbyWs.readyState = MockWebSocket.OPEN;

    act(() => result.current.sendPMTyping('alice'));
    expect(lobbyWs.send).toHaveBeenCalledWith(JSON.stringify({ type: 'typing_pm', to: 'alice' }));
  });

  it('does nothing when sendPMTyping is called with no recipient', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    const lobbyWs = wsInstances.find(ws => ws.url.includes('/ws/lobby'));
    expect(lobbyWs).toBeDefined();
    lobbyWs.readyState = MockWebSocket.OPEN;

    act(() => result.current.sendPMTyping(null));
    const pmTypingCalls = (lobbyWs.send.mock?.calls ?? []).filter(([msg]) => {
      try { return JSON.parse(msg).type === 'typing_pm'; } catch { return false; }
    });
    expect(pmTypingCalls).toHaveLength(0);
  });

  // ── markAsRead ───────────────────────────────────────────────────────────────

  it('sends mark_read event and dispatches SET_READ_POSITION', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(6));
    const ws = wsInstances[wsInstances.length - 1];
    ws.readyState = MockWebSocket.OPEN;

    act(() => result.current.markAsRead(6, 'msg-42'));
    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'mark_read', msg_id: 'msg-42' }));
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_READ_POSITION', roomId: 6, messageId: 'msg-42' });
  });

  it('does nothing when roomId or messageId is falsy', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.markAsRead(null, 'msg-1'));
    act(() => result.current.markAsRead(1, null));
    const sendCalls = wsInstances.flatMap(w => w.send.mock?.calls ?? []);
    const markReadCalls = sendCalls.filter(([msg]) => {
      try { return JSON.parse(msg).type === 'mark_read'; } catch { return false; }
    });
    expect(markReadCalls).toHaveLength(0);
  });

  // ── disconnectAll ─────────────────────────────────────────────────────────

  it('closes all sockets and dispatches RESET', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(1));
    act(() => result.current.joinRoom(2));

    act(() => result.current.disconnectAll());
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'RESET' });
  });

  // ── WebSocket onopen/onclose/onmessage ─────────────────────────────────────

  it('handles incoming messages via ws.onmessage', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(7));
    const ws = wsInstances[wsInstances.length - 1];

    act(() => {
      ws.onmessage({ data: JSON.stringify({ type: 'system', room_id: 7, text: 'test' }) });
    });

    expect(mockDispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'ADD_MESSAGE' }));
  });

  it('silently ignores malformed WS messages (non-JSON)', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(7));
    const ws = wsInstances[wsInstances.length - 1];

    expect(() => act(() => {
      ws.onmessage({ data: 'not-json{{{' });
    })).not.toThrow();
  });

  it('marks reconnecting status when ws closes unexpectedly', async () => {
    vi.useFakeTimers();
    getJoinedRooms.mockReturnValue([8]);
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(8));
    const ws = wsInstances.find(w => w.url.includes('/ws/8'));

    // Simulate socket opening then abnormal closure
    await act(async () => {
      ws.onopen?.();
      ws.onclose?.({ code: 1006 });
    });

    expect(result.current.connectionStatus).toBe('reconnecting');
    vi.useRealTimers();
  });

  it('dispatches EXIT_ROOM on permanent failure codes (4001)', () => {
    const { result } = renderHook(() => useMultiRoomChat());
    act(() => result.current.joinRoom(9));
    const ws = wsInstances[wsInstances.length - 1];

    act(() => ws.onclose?.({ code: 4001 }));
    expect(mockDispatch).toHaveBeenCalledWith({ type: 'EXIT_ROOM', roomId: 9 });
  });
});
