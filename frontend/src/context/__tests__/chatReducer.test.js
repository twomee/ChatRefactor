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
  typingUsers: {},
  readPositions: {},
  knownOfflineUsers: new Set(),
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

    it('clears knownOfflineUsers when leaving the last joined room', () => {
      const state = {
        ...initialState,
        joinedRooms: new Set(['r1']),
        onlineUsers: { r1: ['alice'] },
        knownOfflineUsers: new Set(['bob']),
      };
      const next = chatReducer(state, { type: 'EXIT_ROOM', roomId: 'r1' });
      expect(next.joinedRooms.size).toBe(0);
      expect(next.knownOfflineUsers.size).toBe(0);
    });

    it('preserves knownOfflineUsers when still joined to other rooms', () => {
      const state = {
        ...initialState,
        joinedRooms: new Set(['r1', 'r2']),
        onlineUsers: { r1: ['alice'], r2: ['charlie'] },
        knownOfflineUsers: new Set(['bob']),
      };
      const next = chatReducer(state, { type: 'EXIT_ROOM', roomId: 'r1' });
      expect(next.joinedRooms.has('r2')).toBe(true);
      expect(next.knownOfflineUsers.has('bob')).toBe(true);
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

  describe('USER_JOINED_ROOM', () => {
    it('updates online users for the room', () => {
      const next = chatReducer(initialState, {
        type: 'USER_JOINED_ROOM', roomId: 'r1', users: ['alice', 'bob'], username: 'bob',
      });
      expect(next.onlineUsers.r1).toEqual(['alice', 'bob']);
    });

    it('removes username from knownOfflineUsers', () => {
      const state = { ...initialState, knownOfflineUsers: new Set(['bob']) };
      const next = chatReducer(state, {
        type: 'USER_JOINED_ROOM', roomId: 'r1', users: ['alice', 'bob'], username: 'bob',
      });
      expect(next.knownOfflineUsers.has('bob')).toBe(false);
    });

    it('updates admins and muted when provided', () => {
      const next = chatReducer(initialState, {
        type: 'USER_JOINED_ROOM', roomId: 'r1', users: ['alice'], admins: ['alice'], muted: [], username: 'alice',
      });
      expect(next.admins.r1).toEqual(['alice']);
      expect(next.mutedUsers.r1).toEqual([]);
    });

    it('adds disappeared users to knownOfflineUsers when absent from all rooms', () => {
      const state = { ...initialState, onlineUsers: { r1: ['alice', 'bob', 'charlie'] } };
      const next = chatReducer(state, {
        type: 'USER_JOINED_ROOM', roomId: 'r1', users: ['alice', 'charlie'], username: 'alice',
      });
      // bob disappeared from the room and is not in any other room
      expect(next.knownOfflineUsers.has('bob')).toBe(true);
    });

    it('does NOT mark disappeared user offline if still in another room', () => {
      const state = { ...initialState, onlineUsers: { r1: ['alice', 'bob'], r2: ['bob', 'charlie'] } };
      const next = chatReducer(state, {
        type: 'USER_JOINED_ROOM', roomId: 'r1', users: ['alice'], username: 'alice',
      });
      // bob disappeared from r1 but is still in r2
      expect(next.knownOfflineUsers.has('bob')).toBe(false);
    });

    it('handles first join with no previous user list', () => {
      const next = chatReducer(initialState, {
        type: 'USER_JOINED_ROOM', roomId: 'r1', users: ['alice'], username: 'alice',
      });
      // No previous users → no one to mark offline
      expect(next.knownOfflineUsers.size).toBe(0);
    });
  });

  describe('USER_LEFT_ROOM', () => {
    it('updates online users for the room', () => {
      const state = { ...initialState, onlineUsers: { r1: ['alice', 'bob'] } };
      const next = chatReducer(state, {
        type: 'USER_LEFT_ROOM', roomId: 'r1', users: ['alice'], username: 'bob',
      });
      expect(next.onlineUsers.r1).toEqual(['alice']);
    });

    it('does NOT add username to knownOfflineUsers when leaving all rooms (user may still be logged in)', () => {
      const state = { ...initialState, onlineUsers: { r1: ['alice', 'bob'] } };
      const next = chatReducer(state, {
        type: 'USER_LEFT_ROOM', roomId: 'r1', users: ['alice'], username: 'bob',
      });
      // Leaving a room doesn't mean logged out — only USER_OFFLINE marks users offline
      expect(next.knownOfflineUsers.has('bob')).toBe(false);
    });

    it('does NOT add username to knownOfflineUsers when still in another room', () => {
      const state = {
        ...initialState,
        onlineUsers: { r1: ['alice', 'bob'], r2: ['bob'] },
      };
      const next = chatReducer(state, {
        type: 'USER_LEFT_ROOM', roomId: 'r1', users: ['alice'], username: 'bob',
      });
      // bob is still in r2, so should not be offline
      expect(next.knownOfflineUsers.has('bob')).toBe(false);
    });

    it('updates admins and muted when provided', () => {
      const state = { ...initialState, onlineUsers: { r1: ['alice', 'bob'] } };
      const next = chatReducer(state, {
        type: 'USER_LEFT_ROOM', roomId: 'r1', users: ['alice'], admins: ['alice'], muted: [], username: 'bob',
      });
      expect(next.admins.r1).toEqual(['alice']);
      expect(next.mutedUsers.r1).toEqual([]);
    });
  });

  describe('SET_READ_POSITION', () => {
    it('sets read position for a room', () => {
      const next = chatReducer(initialState, {
        type: 'SET_READ_POSITION',
        roomId: 'r1',
        messageId: 'msg-123',
      });
      expect(next.readPositions.r1).toBe('msg-123');
    });

    it('updates existing read position for a room', () => {
      const state = { ...initialState, readPositions: { r1: 'msg-100' } };
      const next = chatReducer(state, {
        type: 'SET_READ_POSITION',
        roomId: 'r1',
        messageId: 'msg-200',
      });
      expect(next.readPositions.r1).toBe('msg-200');
    });

    it('preserves other rooms read positions', () => {
      const state = { ...initialState, readPositions: { r1: 'msg-100', r2: 'msg-50' } };
      const next = chatReducer(state, {
        type: 'SET_READ_POSITION',
        roomId: 'r1',
        messageId: 'msg-200',
      });
      expect(next.readPositions.r1).toBe('msg-200');
      expect(next.readPositions.r2).toBe('msg-50');
    });
  });

  describe('EXIT_ROOM cleans up readPositions', () => {
    it('removes readPositions entry when exiting a room', () => {
      const state = {
        ...initialState,
        joinedRooms: new Set(['r1', 'r2']),
        messages: { r1: [], r2: [] },
        onlineUsers: { r1: [], r2: [] },
        admins: { r1: [], r2: [] },
        mutedUsers: { r1: [], r2: [] },
        unreadCounts: { r1: 0, r2: 0 },
        readPositions: { r1: 'msg-100', r2: 'msg-50' },
      };
      const next = chatReducer(state, { type: 'EXIT_ROOM', roomId: 'r1' });
      expect(next.readPositions.r1).toBeUndefined();
      expect(next.readPositions.r2).toBe('msg-50');
    });
  });

  // ── Phase 1: Typing indicators ────────────────────────────────────────────

  describe('SET_TYPING', () => {
    it('adds a typing user with a timestamp', () => {
      const next = chatReducer(initialState, {
        type: 'SET_TYPING', roomId: 'r1', username: 'alice', isTyping: true,
      });
      expect(next.typingUsers.r1).toHaveProperty('alice');
    });

    it('removes a typing user when isTyping is false', () => {
      const state = {
        ...initialState,
        typingUsers: { r1: { alice: Date.now() } },
      };
      const next = chatReducer(state, {
        type: 'SET_TYPING', roomId: 'r1', username: 'alice', isTyping: false,
      });
      expect(next.typingUsers.r1).not.toHaveProperty('alice');
    });

    it('preserves other typing users when removing one', () => {
      const state = {
        ...initialState,
        typingUsers: { r1: { alice: Date.now(), bob: Date.now() } },
      };
      const next = chatReducer(state, {
        type: 'SET_TYPING', roomId: 'r1', username: 'alice', isTyping: false,
      });
      expect(next.typingUsers.r1).toHaveProperty('bob');
      expect(next.typingUsers.r1).not.toHaveProperty('alice');
    });
  });

  // ── Phase 1: Edit / Delete messages ───────────────────────────────────────

  describe('EDIT_MESSAGE', () => {
    it('updates text and edited_at for the target message', () => {
      const state = {
        ...initialState,
        messages: {
          r1: [
            { msg_id: 'msg1', text: 'original', from: 'alice' },
            { msg_id: 'msg2', text: 'other', from: 'bob' },
          ],
        },
      };
      const next = chatReducer(state, {
        type: 'EDIT_MESSAGE', roomId: 'r1', msgId: 'msg1', text: 'edited', edited_at: '2024-01-01T00:00:00Z',
      });
      expect(next.messages.r1[0].text).toBe('edited');
      expect(next.messages.r1[0].edited_at).toBe('2024-01-01T00:00:00Z');
      // Other messages unchanged
      expect(next.messages.r1[1].text).toBe('other');
    });

    it('returns same state when room has no messages', () => {
      const next = chatReducer(initialState, {
        type: 'EDIT_MESSAGE', roomId: 'r1', msgId: 'msg1', text: 'edited',
      });
      expect(next).toBe(initialState);
    });
  });

  describe('DELETE_MESSAGE', () => {
    it('marks the target message as deleted and sets text to [deleted]', () => {
      const state = {
        ...initialState,
        messages: {
          r1: [{ msg_id: 'msg1', text: 'hello', from: 'alice' }],
        },
      };
      const next = chatReducer(state, {
        type: 'DELETE_MESSAGE', roomId: 'r1', msgId: 'msg1',
      });
      expect(next.messages.r1[0].is_deleted).toBe(true);
      expect(next.messages.r1[0].text).toBe('[deleted]');
    });

    it('returns same state when room has no messages', () => {
      const next = chatReducer(initialState, {
        type: 'DELETE_MESSAGE', roomId: 'r1', msgId: 'msg1',
      });
      expect(next).toBe(initialState);
    });
  });

  // ── Phase 1: Emoji Reactions ──────────────────────────────────────────────

  describe('ADD_REACTION', () => {
    it('appends a reaction to the target message', () => {
      const state = {
        ...initialState,
        messages: {
          r1: [{ msg_id: 'msg1', text: 'hi', reactions: [] }],
        },
      };
      const next = chatReducer(state, {
        type: 'ADD_REACTION', roomId: 'r1', msgId: 'msg1',
        emoji: '👍', username: 'alice', userId: 1,
      });
      expect(next.messages.r1[0].reactions).toHaveLength(1);
      expect(next.messages.r1[0].reactions[0]).toMatchObject({
        emoji: '👍', username: 'alice', user_id: 1,
      });
    });

    it('creates a reactions array when message has no reactions yet', () => {
      const state = {
        ...initialState,
        messages: { r1: [{ msg_id: 'msg1', text: 'hi' }] },
      };
      const next = chatReducer(state, {
        type: 'ADD_REACTION', roomId: 'r1', msgId: 'msg1',
        emoji: '❤️', username: 'bob', userId: 2,
      });
      expect(next.messages.r1[0].reactions).toHaveLength(1);
      expect(next.messages.r1[0].reactions[0].emoji).toBe('❤️');
    });

    it('does not modify other messages', () => {
      const state = {
        ...initialState,
        messages: {
          r1: [
            { msg_id: 'msg1', text: 'hi', reactions: [] },
            { msg_id: 'msg2', text: 'hey', reactions: [] },
          ],
        },
      };
      const next = chatReducer(state, {
        type: 'ADD_REACTION', roomId: 'r1', msgId: 'msg1',
        emoji: '👍', username: 'alice', userId: 1,
      });
      expect(next.messages.r1[1].reactions).toHaveLength(0);
    });
  });

  describe('REMOVE_REACTION', () => {
    it('removes the matching reaction from the target message', () => {
      const state = {
        ...initialState,
        messages: {
          r1: [{
            msg_id: 'msg1',
            text: 'hi',
            reactions: [
              { emoji: '👍', username: 'alice', user_id: 1 },
              { emoji: '❤️', username: 'bob', user_id: 2 },
            ],
          }],
        },
      };
      const next = chatReducer(state, {
        type: 'REMOVE_REACTION', roomId: 'r1', msgId: 'msg1',
        emoji: '👍', username: 'alice',
      });
      expect(next.messages.r1[0].reactions).toHaveLength(1);
      expect(next.messages.r1[0].reactions[0].emoji).toBe('❤️');
    });

    it('handles message with no reactions gracefully', () => {
      const state = {
        ...initialState,
        messages: { r1: [{ msg_id: 'msg1', text: 'hi' }] },
      };
      const next = chatReducer(state, {
        type: 'REMOVE_REACTION', roomId: 'r1', msgId: 'msg1',
        emoji: '👍', username: 'alice',
      });
      expect(next.messages.r1[0].reactions).toHaveLength(0);
    });
  });

  describe('USER_ONLINE', () => {
    it('removes username from knownOfflineUsers', () => {
      const state = { ...initialState, knownOfflineUsers: new Set(['bob']) };
      const next = chatReducer(state, { type: 'USER_ONLINE', username: 'bob' });
      expect(next.knownOfflineUsers.has('bob')).toBe(false);
    });

    it('is a no-op if user is not in knownOfflineUsers', () => {
      const next = chatReducer(initialState, { type: 'USER_ONLINE', username: 'bob' });
      expect(next).toBe(initialState);
    });
  });

  describe('USER_OFFLINE', () => {
    it('adds username to knownOfflineUsers', () => {
      const next = chatReducer(initialState, { type: 'USER_OFFLINE', username: 'bob' });
      expect(next.knownOfflineUsers.has('bob')).toBe(true);
    });

    it('is a no-op if user is already in knownOfflineUsers', () => {
      const state = { ...initialState, knownOfflineUsers: new Set(['bob']) };
      const next = chatReducer(state, { type: 'USER_OFFLINE', username: 'bob' });
      expect(next).toBe(state);
    });
  });

  describe('default', () => {
    it('returns current state for unknown action', () => {
      const next = chatReducer(initialState, { type: 'UNKNOWN_ACTION' });
      expect(next).toBe(initialState);
    });
  });
});
