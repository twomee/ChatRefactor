// src/hooks/__tests__/useMultiRoomChat.test.js
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock storage so we can verify addPMThread is called without touching localStorage
vi.mock('../../utils/storage', async () => {
  const actual = await vi.importActual('../../utils/storage');
  return {
    ...actual,
    addPMThread: vi.fn(),
    getJoinedRooms: vi.fn(() => []),
  };
});

// Mock other dependencies to avoid importing full contexts
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

import { addPMThread } from '../../utils/storage';
import { sendBrowserNotification } from '../../utils/notifications';
import { createHandleMessage, getBackoffDelay } from '../useMultiRoomChat';

// ── Shared test harness ───────────────────────────────────────────────────────

function makeRefs(overrides = {}) {
  return {
    dispatch: vi.fn(),
    pmDispatch: vi.fn(),
    user: { username: 'alice' },
    activeRoomIdRef: { current: null },
    seenMsgIdsRef: { current: new Set() },
    pmStateRef: { current: { threads: {}, activePM: null } },
    lastMsgTimeRef: { current: new Map() },
    exitRoomRef: { current: vi.fn() },
    stateRef: { current: { rooms: [], joinedRooms: new Set() } },
    showToast: vi.fn(),
    ...overrides,
  };
}

describe('createHandleMessage', () => {
  let refs;

  beforeEach(() => {
    refs = makeRefs();
    vi.clearAllMocks();
  });

  function handle(msg, roomId) {
    return createHandleMessage(refs)(msg, roomId);
  }

  // ── history ──────────────────────────────────────────────────────────────

  describe('history event', () => {
    it('dispatches SET_HISTORY with room_id and messages', () => {
      handle({ type: 'history', room_id: 1, messages: [{ text: 'hi' }] });
      expect(refs.dispatch).toHaveBeenCalledWith({
        type: 'SET_HISTORY',
        roomId: 1,
        messages: [{ text: 'hi' }],
      });
    });

    it('tracks timestamp on history', () => {
      handle({ type: 'history', room_id: 1, messages: [] });
      expect(refs.lastMsgTimeRef.current.has(1)).toBe(true);
    });
  });

  // ── user_join / user_left ────────────────────────────────────────────────

  describe('user_join event', () => {
    it('dispatches USER_JOINED_ROOM and a system message', () => {
      handle({ type: 'user_join', room_id: 1, users: ['alice', 'bob'], admins: [], muted: [], username: 'bob' });
      expect(refs.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'USER_JOINED_ROOM', roomId: 1, username: 'bob' }));
      expect(refs.dispatch).toHaveBeenCalledWith(expect.objectContaining({
        type: 'ADD_MESSAGE',
        message: expect.objectContaining({ isSystem: true, text: 'bob joined the room' }),
      }));
    });

    it('does not emit system message when silent: true', () => {
      handle({ type: 'user_join', room_id: 1, users: [], admins: [], muted: [], username: 'bob', silent: true });
      const addMsgCalls = refs.dispatch.mock.calls.filter(([a]) => a.type === 'ADD_MESSAGE');
      expect(addMsgCalls).toHaveLength(0);
    });
  });

  describe('user_left event', () => {
    it('dispatches USER_LEFT_ROOM and a system message', () => {
      handle({ type: 'user_left', room_id: 1, users: ['alice'], admins: [], muted: [], username: 'bob' });
      expect(refs.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'USER_LEFT_ROOM', roomId: 1 }));
      expect(refs.dispatch).toHaveBeenCalledWith(expect.objectContaining({
        type: 'ADD_MESSAGE',
        message: expect.objectContaining({ text: 'bob left the room' }),
      }));
    });

    it('does not emit system message when silent: true', () => {
      handle({ type: 'user_left', room_id: 1, users: [], admins: [], muted: [], username: 'bob', silent: true });
      const addMsgCalls = refs.dispatch.mock.calls.filter(([a]) => a.type === 'ADD_MESSAGE');
      expect(addMsgCalls).toHaveLength(0);
    });
  });

  // ── system message ────────────────────────────────────────────────────────

  describe('system event', () => {
    it('dispatches ADD_MESSAGE with isSystem: true', () => {
      handle({ type: 'system', room_id: 2, text: 'Server restarted' });
      expect(refs.dispatch).toHaveBeenCalledWith({
        type: 'ADD_MESSAGE',
        roomId: 2,
        message: { isSystem: true, text: 'Server restarted' },
      });
    });
  });

  // ── message ───────────────────────────────────────────────────────────────

  describe('message event', () => {
    it('dispatches ADD_MESSAGE for a new room message', () => {
      handle({ type: 'message', room_id: 1, from: 'bob', text: 'hi', msg_id: 'msg-1' });
      expect(refs.dispatch).toHaveBeenCalledWith(expect.objectContaining({
        type: 'ADD_MESSAGE',
        roomId: 1,
        message: expect.objectContaining({ from: 'bob', text: 'hi', msg_id: 'msg-1' }),
      }));
    });

    it('increments unread when message is in a background room', () => {
      refs.activeRoomIdRef.current = 2; // different from room_id 1
      handle({ type: 'message', room_id: 1, from: 'bob', text: 'hey', msg_id: 'msg-2' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'INCREMENT_UNREAD', roomId: 1 });
    });

    it('does not increment unread for the active room', () => {
      refs.activeRoomIdRef.current = 1;
      handle({ type: 'message', room_id: 1, from: 'bob', text: 'hey', msg_id: 'msg-3' });
      expect(refs.dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'INCREMENT_UNREAD' }));
    });

    it('deduplicates messages with the same msg_id', () => {
      handle({ type: 'message', room_id: 1, from: 'bob', text: 'dupe', msg_id: 'dup-1' });
      handle({ type: 'message', room_id: 1, from: 'bob', text: 'dupe', msg_id: 'dup-1' });
      const addCalls = refs.dispatch.mock.calls.filter(([a]) => a.type === 'ADD_MESSAGE');
      expect(addCalls).toHaveLength(1);
    });

    it('evicts oldest msg_id when seen set exceeds 500 entries', () => {
      for (let i = 0; i < 500; i++) {
        refs.seenMsgIdsRef.current.add(`old-${i}`);
      }
      handle({ type: 'message', room_id: 1, from: 'bob', text: 'new', msg_id: 'new-1' });
      expect(refs.seenMsgIdsRef.current.size).toBe(500);
      expect(refs.seenMsgIdsRef.current.has('new-1')).toBe(true);
    });

    it('sends browser notification when current user is @mentioned', () => {
      handle({ type: 'message', room_id: 1, from: 'bob', text: '@alice check this', msg_id: 'msg-m1', mentions: ['alice'] });
      expect(sendBrowserNotification).toHaveBeenCalledWith('@bob mentioned you', '@alice check this');
    });

    it('sends browser notification for @mention_room', () => {
      handle({ type: 'message', room_id: 1, from: 'bob', text: '@room everyone', msg_id: 'msg-m2', mention_room: true });
      expect(sendBrowserNotification).toHaveBeenCalled();
    });

    it('does not notify when no @mention', () => {
      handle({ type: 'message', room_id: 1, from: 'bob', text: 'hello world', msg_id: 'msg-m3' });
      expect(sendBrowserNotification).not.toHaveBeenCalled();
    });
  });

  // ── private_message ───────────────────────────────────────────────────────

  describe('private_message event', () => {
    it('calls addPMThread when a PM arrives from another user', () => {
      handle({ type: 'private_message', from: 'bob', to: 'alice', text: 'hello', msg_id: 'pm-1', self: false });
      expect(addPMThread).toHaveBeenCalledWith('alice', 'bob');
    });

    it('calls addPMThread when current user sends a PM (self: true)', () => {
      handle({ type: 'private_message', from: 'alice', to: 'bob', text: 'hey', msg_id: 'pm-2', self: true });
      expect(addPMThread).toHaveBeenCalledWith('alice', 'bob');
    });

    it('dispatches ADD_PM_MESSAGE', () => {
      handle({ type: 'private_message', from: 'bob', to: 'alice', text: 'hi', msg_id: 'pm-3', self: false });
      expect(refs.pmDispatch).toHaveBeenCalledWith(expect.objectContaining({
        type: 'ADD_PM_MESSAGE', username: 'bob',
      }));
    });

    it('increments PM unread when sender is not the activePM', () => {
      refs.pmStateRef.current.activePM = null;
      handle({ type: 'private_message', from: 'bob', to: 'alice', text: 'hi', msg_id: 'pm-4', self: false });
      expect(refs.pmDispatch).toHaveBeenCalledWith({ type: 'INCREMENT_PM_UNREAD', username: 'bob' });
    });

    it('does not increment PM unread when sender is the activePM', () => {
      refs.pmStateRef.current.activePM = 'bob';
      handle({ type: 'private_message', from: 'bob', to: 'alice', text: 'hi', msg_id: 'pm-5', self: false });
      expect(refs.pmDispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'INCREMENT_PM_UNREAD' }));
    });

    it('deduplicates PM messages by msg_id', () => {
      handle({ type: 'private_message', from: 'bob', to: 'alice', text: 'dupe', msg_id: 'pm-dup', self: false });
      handle({ type: 'private_message', from: 'bob', to: 'alice', text: 'dupe', msg_id: 'pm-dup', self: false });
      const addCalls = refs.pmDispatch.mock.calls.filter(([a]) => a.type === 'ADD_PM_MESSAGE');
      expect(addCalls).toHaveLength(1);
    });
  });

  // ── pm_message_edited ─────────────────────────────────────────────────────

  describe('pm_message_edited event', () => {
    it('dispatches EDIT_PM_MESSAGE for the matching thread', () => {
      refs.pmStateRef.current.threads = { bob: [{ msg_id: 'pm-1', text: 'old' }] };
      handle({ type: 'pm_message_edited', msg_id: 'pm-1', text: 'new text' });
      expect(refs.pmDispatch).toHaveBeenCalledWith({
        type: 'EDIT_PM_MESSAGE', username: 'bob', msg_id: 'pm-1', text: 'new text',
      });
    });

    it('does nothing if msg_id is not found in any thread', () => {
      refs.pmStateRef.current.threads = { bob: [{ msg_id: 'pm-99', text: 'other' }] };
      handle({ type: 'pm_message_edited', msg_id: 'pm-999', text: 'new' });
      expect(refs.pmDispatch).not.toHaveBeenCalled();
    });
  });

  // ── pm_message_deleted ────────────────────────────────────────────────────

  describe('pm_message_deleted event', () => {
    it('dispatches DELETE_PM_MESSAGE for the matching thread', () => {
      refs.pmStateRef.current.threads = { bob: [{ msg_id: 'pm-2', text: 'bye' }] };
      handle({ type: 'pm_message_deleted', msg_id: 'pm-2' });
      expect(refs.pmDispatch).toHaveBeenCalledWith({
        type: 'DELETE_PM_MESSAGE', username: 'bob', msg_id: 'pm-2',
      });
    });

    it('does nothing if msg_id is not found', () => {
      refs.pmStateRef.current.threads = {};
      handle({ type: 'pm_message_deleted', msg_id: 'nope' });
      expect(refs.pmDispatch).not.toHaveBeenCalled();
    });
  });

  // ── pm_reaction_added ─────────────────────────────────────────────────────

  describe('pm_reaction_added event', () => {
    it('dispatches ADD_PM_REACTION for the matching thread', () => {
      refs.pmStateRef.current.threads = { bob: [{ msg_id: 'pm-3' }] };
      handle({ type: 'pm_reaction_added', msg_id: 'pm-3', emoji: '👍', reactor: 'bob', reactor_id: 2 });
      expect(refs.pmDispatch).toHaveBeenCalledWith({
        type: 'ADD_PM_REACTION', username: 'bob', msg_id: 'pm-3', emoji: '👍', reactor: 'bob', reactor_id: 2,
      });
    });

    it('does nothing if msg_id not found', () => {
      refs.pmStateRef.current.threads = {};
      handle({ type: 'pm_reaction_added', msg_id: 'nope', emoji: '👍' });
      expect(refs.pmDispatch).not.toHaveBeenCalled();
    });
  });

  // ── pm_reaction_removed ───────────────────────────────────────────────────

  describe('pm_reaction_removed event', () => {
    it('dispatches REMOVE_PM_REACTION for the matching thread', () => {
      refs.pmStateRef.current.threads = { bob: [{ msg_id: 'pm-4' }] };
      handle({ type: 'pm_reaction_removed', msg_id: 'pm-4', emoji: '❤️', reactor: 'alice' });
      expect(refs.pmDispatch).toHaveBeenCalledWith({
        type: 'REMOVE_PM_REACTION', username: 'bob', msg_id: 'pm-4', emoji: '❤️', reactor: 'alice',
      });
    });

    it('does nothing if msg_id not found', () => {
      refs.pmStateRef.current.threads = {};
      handle({ type: 'pm_reaction_removed', msg_id: 'nope', emoji: '❤️' });
      expect(refs.pmDispatch).not.toHaveBeenCalled();
    });
  });

  // ── file_shared ───────────────────────────────────────────────────────────

  describe('file_shared event routing', () => {
    it('dispatches ADD_PM_MESSAGE to pmDispatch for PM files (sender is other user)', () => {
      handle({ type: 'file_shared', is_private: true, from: 'bob', to: 'alice', filename: 'photo.jpg', file_id: 42, size: 1024, timestamp: '2024-01-01T00:00:00Z' });
      expect(refs.pmDispatch).toHaveBeenCalledWith(expect.objectContaining({
        type: 'ADD_PM_MESSAGE', username: 'bob', message: expect.objectContaining({ isFile: true, from: 'bob', text: 'photo.jpg' }),
      }));
      expect(refs.dispatch.mock.calls.filter(([a]) => a.type === 'ADD_MESSAGE')).toHaveLength(0);
    });

    it('dispatches ADD_PM_MESSAGE to pmDispatch for PM files (sender is current user)', () => {
      handle({ type: 'file_shared', is_private: true, from: 'alice', to: 'bob', filename: 'doc.pdf', file_id: 99, size: 2048 });
      expect(refs.pmDispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'ADD_PM_MESSAGE', username: 'bob' }));
    });

    it('dispatches ADD_MESSAGE to room dispatch for room files', () => {
      handle({ type: 'file_shared', is_private: false, from: 'bob', room_id: 5, filename: 'image.png', file_id: 7, size: 512 });
      expect(refs.dispatch).toHaveBeenCalledWith(expect.objectContaining({
        type: 'ADD_MESSAGE', roomId: 5, message: expect.objectContaining({ isFile: true }),
      }));
    });

    it('increments unread for background room file', () => {
      refs.activeRoomIdRef.current = 99;
      handle({ type: 'file_shared', is_private: false, from: 'bob', room_id: 5, filename: 'a.zip', file_id: 8, size: 100 });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'INCREMENT_UNREAD', roomId: 5 });
    });
  });

  // ── message_edited / message_deleted ─────────────────────────────────────

  describe('message_edited event', () => {
    it('dispatches EDIT_MESSAGE', () => {
      handle({ type: 'message_edited', room_id: 1, msg_id: 'msg-1', text: 'edited', edited_at: '2024-01-01' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'EDIT_MESSAGE', roomId: 1, msgId: 'msg-1', text: 'edited', edited_at: '2024-01-01' });
    });
  });

  describe('message_deleted event', () => {
    it('dispatches DELETE_MESSAGE', () => {
      handle({ type: 'message_deleted', room_id: 1, msg_id: 'msg-2' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'DELETE_MESSAGE', roomId: 1, msgId: 'msg-2' });
    });
  });

  // ── kicked ────────────────────────────────────────────────────────────────

  describe('kicked event', () => {
    it('calls exitRoomRef and shows a danger toast', () => {
      refs.stateRef.current.rooms = [{ id: 3, name: 'lobby' }];
      handle({ type: 'kicked', room_id: 3 });
      expect(refs.exitRoomRef.current).toHaveBeenCalledWith(3);
      expect(refs.showToast).toHaveBeenCalledWith('danger', 'Removed from room', 'You were kicked from #lobby');
    });

    it('changes active room when kicked from the current active room', () => {
      refs.activeRoomIdRef.current = 3;
      refs.stateRef.current.joinedRooms = new Set([3, 4]);
      handle({ type: 'kicked', room_id: 3 });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'SET_ACTIVE_ROOM', roomId: 4 });
    });

    it('sets active room to null when no other rooms available', () => {
      refs.activeRoomIdRef.current = 3;
      refs.stateRef.current.joinedRooms = new Set([3]);
      handle({ type: 'kicked', room_id: 3 });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'SET_ACTIVE_ROOM', roomId: null });
    });
  });

  // ── muted / unmuted / new_admin ───────────────────────────────────────────

  describe('muted event', () => {
    it('dispatches ADD_MUTED', () => {
      handle({ type: 'muted', room_id: 1, username: 'bob' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'ADD_MUTED', roomId: 1, username: 'bob' });
    });
  });

  describe('unmuted event', () => {
    it('dispatches REMOVE_MUTED', () => {
      handle({ type: 'unmuted', room_id: 1, username: 'bob' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'REMOVE_MUTED', roomId: 1, username: 'bob' });
    });
  });

  describe('new_admin event', () => {
    it('dispatches SET_ADMIN', () => {
      handle({ type: 'new_admin', room_id: 1, username: 'carol' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'SET_ADMIN', roomId: 1, username: 'carol' });
    });
  });

  // ── room_list_updated ─────────────────────────────────────────────────────

  describe('room_list_updated event', () => {
    it('dispatches SET_ROOMS', () => {
      const rooms = [{ id: 1, name: 'general' }];
      handle({ type: 'room_list_updated', rooms });
      expect(refs.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_ROOMS', rooms }));
    });

    it('exits rooms that were removed from the server list', () => {
      refs.stateRef.current.joinedRooms = new Set([1, 2]);
      refs.activeRoomIdRef.current = 1;
      handle({ type: 'room_list_updated', rooms: [{ id: 1, name: 'general' }] });
      expect(refs.exitRoomRef.current).toHaveBeenCalledWith(2);
    });
  });

  // ── chat_closed ───────────────────────────────────────────────────────────

  describe('chat_closed event', () => {
    it('exits the closed room and shows a warning toast', () => {
      refs.activeRoomIdRef.current = 5;
      handle({ type: 'chat_closed', room_id: 5, detail: 'Room was closed by admin' });
      expect(refs.exitRoomRef.current).toHaveBeenCalledWith(5);
      expect(refs.showToast).toHaveBeenCalledWith('warning', 'Room closed', 'Room was closed by admin');
    });

    it('uses roomId fallback when room_id is absent', () => {
      handle({ type: 'chat_closed', detail: 'closed' }, 7);
      expect(refs.exitRoomRef.current).toHaveBeenCalledWith(7);
    });

    it('uses default message when detail is absent', () => {
      handle({ type: 'chat_closed', room_id: 5 });
      expect(refs.showToast).toHaveBeenCalledWith('warning', 'Room closed', 'This room has been closed');
    });

    it('sets active room to null when the closed room was active', () => {
      refs.activeRoomIdRef.current = 5;
      handle({ type: 'chat_closed', room_id: 5 });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'SET_ACTIVE_ROOM', roomId: null });
    });
  });

  // ── typing ────────────────────────────────────────────────────────────────

  describe('typing event', () => {
    it('dispatches SET_TYPING with isTyping: true', () => {
      vi.useFakeTimers();
      handle({ type: 'typing', room_id: 1, username: 'bob' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'SET_TYPING', roomId: 1, username: 'bob', isTyping: true });
      vi.useRealTimers();
    });

    it('dispatches SET_TYPING with isTyping: false after 3 seconds', () => {
      vi.useFakeTimers();
      handle({ type: 'typing', room_id: 1, username: 'bob' });
      vi.advanceTimersByTime(3000);
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'SET_TYPING', roomId: 1, username: 'bob', isTyping: false });
      vi.useRealTimers();
    });
  });

  // ── read_position ─────────────────────────────────────────────────────────

  describe('read_position event', () => {
    it('dispatches SET_READ_POSITION', () => {
      handle({ type: 'read_position', room_id: 1, last_read_message_id: 'msg-42' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'SET_READ_POSITION', roomId: 1, messageId: 'msg-42' });
    });
  });

  // ── reaction_added / reaction_removed ─────────────────────────────────────

  describe('reaction_added event', () => {
    it('dispatches ADD_REACTION', () => {
      handle({ type: 'reaction_added', room_id: 1, msg_id: 'm1', emoji: '👍', username: 'bob', user_id: 2 });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'ADD_REACTION', roomId: 1, msgId: 'm1', emoji: '👍', username: 'bob', userId: 2 });
    });
  });

  describe('reaction_removed event', () => {
    it('dispatches REMOVE_REACTION', () => {
      handle({ type: 'reaction_removed', room_id: 1, msg_id: 'm1', emoji: '👍', username: 'bob' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'REMOVE_REACTION', roomId: 1, msgId: 'm1', emoji: '👍', username: 'bob' });
    });
  });

  // ── user_online / user_offline ────────────────────────────────────────────

  describe('user_online event', () => {
    it('dispatches USER_ONLINE', () => {
      handle({ type: 'user_online', username: 'carol' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'USER_ONLINE', username: 'carol' });
    });
  });

  describe('user_offline event', () => {
    it('dispatches USER_OFFLINE', () => {
      handle({ type: 'user_offline', username: 'carol' });
      expect(refs.dispatch).toHaveBeenCalledWith({ type: 'USER_OFFLINE', username: 'carol' });
    });
  });

  // ── error ─────────────────────────────────────────────────────────────────

  describe('error event', () => {
    it('shows a danger toast with the error detail', () => {
      handle({ type: 'error', detail: 'Token expired' });
      expect(refs.showToast).toHaveBeenCalledWith('danger', 'Error', 'Token expired');
    });

    it('shows a fallback message when detail is absent', () => {
      handle({ type: 'error' });
      expect(refs.showToast).toHaveBeenCalledWith('danger', 'Error', 'Something went wrong');
    });
  });

  // ── unknown / default ─────────────────────────────────────────────────────

  describe('unknown event type', () => {
    it('does not throw and ignores the event', () => {
      expect(() => handle({ type: 'UNKNOWN_EVENT' })).not.toThrow();
      expect(refs.dispatch).not.toHaveBeenCalled();
      expect(refs.pmDispatch).not.toHaveBeenCalled();
    });
  });
});

// ── getBackoffDelay ───────────────────────────────────────────────────────────

describe('getBackoffDelay', () => {
  it('returns a delay close to 1000ms for attempt 0', () => {
    const delay = getBackoffDelay(0);
    // 1000ms ± 20% jitter
    expect(delay).toBeGreaterThanOrEqual(800);
    expect(delay).toBeLessThanOrEqual(1200);
  });

  it('grows exponentially — attempt 1 is roughly double attempt 0', () => {
    // Mock Math.random to return 0 (no jitter) so we can test deterministically
    vi.spyOn(Math, 'random').mockReturnValue(0.5); // jitter = 0
    const d0 = getBackoffDelay(0);
    const d1 = getBackoffDelay(1);
    expect(d1).toBeCloseTo(d0 * 2, 0);
    vi.restoreAllMocks();
  });

  it('is capped at 30000ms for large attempt numbers', () => {
    const delay = getBackoffDelay(20); // 1000 * 2^20 >> 30000
    expect(delay).toBeLessThanOrEqual(30000);
  });

  it('always returns a positive number', () => {
    for (let i = 0; i < 10; i++) {
      expect(getBackoffDelay(i)).toBeGreaterThan(0);
    }
  });
});
