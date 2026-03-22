import { describe, it, expect } from 'vitest';
import { chatReducer } from '../ChatContext';

const initialState = {
  rooms: [],
  activeRoomId: null,
  joinedRooms: new Set(),
  unreadCounts: {},
  messages: {},
  onlineUsers: {},
  admins: {},
  mutedUsers: {},
};

describe('chatReducer', () => {
  describe('SET_ROOMS', () => {
    it('replaces rooms list', () => {
      const rooms = [{ id: '1', name: 'general' }];
      const next = chatReducer(initialState, { type: 'SET_ROOMS', rooms });
      expect(next.rooms).toEqual(rooms);
    });
  });

  describe('SET_ACTIVE_ROOM', () => {
    it('sets active room ID', () => {
      const next = chatReducer(initialState, { type: 'SET_ACTIVE_ROOM', roomId: 'r1' });
      expect(next.activeRoomId).toBe('r1');
    });

    it('can set active room to null', () => {
      const state = { ...initialState, activeRoomId: 'r1' };
      const next = chatReducer(state, { type: 'SET_ACTIVE_ROOM', roomId: null });
      expect(next.activeRoomId).toBeNull();
    });
  });

  describe('SET_HISTORY', () => {
    it('sets message history for a room', () => {
      const messages = [{ from: 'alice', text: 'hi' }];
      const next = chatReducer(initialState, { type: 'SET_HISTORY', roomId: 'r1', messages });
      expect(next.messages.r1).toEqual(messages);
    });

    it('replaces existing history', () => {
      const state = { ...initialState, messages: { r1: [{ from: 'old', text: 'old' }] } };
      const newMsgs = [{ from: 'new', text: 'new' }];
      const next = chatReducer(state, { type: 'SET_HISTORY', roomId: 'r1', messages: newMsgs });
      expect(next.messages.r1).toEqual(newMsgs);
    });
  });

  describe('ADD_MESSAGE', () => {
    it('appends a message to an existing room', () => {
      const state = { ...initialState, messages: { r1: [{ from: 'alice', text: 'first' }] } };
      const msg = { from: 'bob', text: 'second' };
      const next = chatReducer(state, { type: 'ADD_MESSAGE', roomId: 'r1', message: msg });
      expect(next.messages.r1).toHaveLength(2);
      expect(next.messages.r1[1]).toEqual(msg);
    });

    it('creates room message array if it does not exist', () => {
      const msg = { from: 'alice', text: 'hello' };
      const next = chatReducer(initialState, { type: 'ADD_MESSAGE', roomId: 'r1', message: msg });
      expect(next.messages.r1).toEqual([msg]);
    });
  });

  describe('SET_USERS', () => {
    it('sets online users for a room', () => {
      const next = chatReducer(initialState, { type: 'SET_USERS', roomId: 'r1', users: ['alice', 'bob'] });
      expect(next.onlineUsers.r1).toEqual(['alice', 'bob']);
    });
  });

  describe('SET_ADMINS', () => {
    it('sets admins for a room', () => {
      const next = chatReducer(initialState, { type: 'SET_ADMINS', roomId: 'r1', admins: ['alice'] });
      expect(next.admins.r1).toEqual(['alice']);
    });
  });

  describe('SET_ADMIN', () => {
    it('adds a single admin to a room', () => {
      const state = { ...initialState, admins: { r1: ['alice'] } };
      const next = chatReducer(state, { type: 'SET_ADMIN', roomId: 'r1', username: 'bob' });
      expect(next.admins.r1).toContain('alice');
      expect(next.admins.r1).toContain('bob');
    });

    it('does not duplicate an existing admin', () => {
      const state = { ...initialState, admins: { r1: ['alice'] } };
      const next = chatReducer(state, { type: 'SET_ADMIN', roomId: 'r1', username: 'alice' });
      expect(next.admins.r1).toEqual(['alice']);
    });
  });

  describe('SET_MUTED_USERS / ADD_MUTED / REMOVE_MUTED', () => {
    it('sets muted users for a room', () => {
      const next = chatReducer(initialState, { type: 'SET_MUTED_USERS', roomId: 'r1', muted: ['bob'] });
      expect(next.mutedUsers.r1).toEqual(['bob']);
    });

    it('adds a muted user', () => {
      const state = { ...initialState, mutedUsers: { r1: ['bob'] } };
      const next = chatReducer(state, { type: 'ADD_MUTED', roomId: 'r1', username: 'charlie' });
      expect(next.mutedUsers.r1).toEqual(['bob', 'charlie']);
    });

    it('removes a muted user', () => {
      const state = { ...initialState, mutedUsers: { r1: ['bob', 'charlie'] } };
      const next = chatReducer(state, { type: 'REMOVE_MUTED', roomId: 'r1', username: 'bob' });
      expect(next.mutedUsers.r1).toEqual(['charlie']);
    });
  });

  describe('JOIN_ROOM', () => {
    it('adds room to joinedRooms set', () => {
      const next = chatReducer(initialState, { type: 'JOIN_ROOM', roomId: 'r1' });
      expect(next.joinedRooms.has('r1')).toBe(true);
    });

    it('is idempotent — returns same state if room already joined', () => {
      const state = { ...initialState, joinedRooms: new Set(['r1']) };
      const next = chatReducer(state, { type: 'JOIN_ROOM', roomId: 'r1' });
      expect(next).toBe(state);
    });
  });

  describe('EXIT_ROOM', () => {
    it('removes room from joinedRooms and cleans up all related state', () => {
      const state = {
        ...initialState,
        joinedRooms: new Set(['r1', 'r2']),
        messages: { r1: [{ text: 'hi' }], r2: [{ text: 'hey' }] },
        onlineUsers: { r1: ['alice'], r2: ['bob'] },
        admins: { r1: ['alice'], r2: [] },
        mutedUsers: { r1: [], r2: [] },
        unreadCounts: { r1: 5, r2: 0 },
      };
      const next = chatReducer(state, { type: 'EXIT_ROOM', roomId: 'r1' });

      expect(next.joinedRooms.has('r1')).toBe(false);
      expect(next.joinedRooms.has('r2')).toBe(true);
      expect(next.messages.r1).toBeUndefined();
      expect(next.messages.r2).toBeDefined();
      expect(next.onlineUsers.r1).toBeUndefined();
      expect(next.unreadCounts.r1).toBeUndefined();
    });

    it('is idempotent — returns same state if room not joined', () => {
      const next = chatReducer(initialState, { type: 'EXIT_ROOM', roomId: 'nonexistent' });
      expect(next).toBe(initialState);
    });
  });

  describe('INCREMENT_UNREAD', () => {
    it('increments unread count for a room', () => {
      const next = chatReducer(initialState, { type: 'INCREMENT_UNREAD', roomId: 'r1' });
      expect(next.unreadCounts.r1).toBe(1);
    });

    it('increments existing count', () => {
      const state = { ...initialState, unreadCounts: { r1: 3 } };
      const next = chatReducer(state, { type: 'INCREMENT_UNREAD', roomId: 'r1' });
      expect(next.unreadCounts.r1).toBe(4);
    });
  });

  describe('CLEAR_UNREAD', () => {
    it('resets unread count to 0', () => {
      const state = { ...initialState, unreadCounts: { r1: 5 } };
      const next = chatReducer(state, { type: 'CLEAR_UNREAD', roomId: 'r1' });
      expect(next.unreadCounts.r1).toBe(0);
    });

    it('is idempotent — returns same state if no unread', () => {
      const next = chatReducer(initialState, { type: 'CLEAR_UNREAD', roomId: 'r1' });
      expect(next).toBe(initialState);
    });
  });

  describe('default', () => {
    it('returns current state for unknown action', () => {
      const next = chatReducer(initialState, { type: 'UNKNOWN_ACTION' });
      expect(next).toBe(initialState);
    });
  });
});
