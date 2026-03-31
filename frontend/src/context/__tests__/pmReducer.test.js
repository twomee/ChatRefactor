import { describe, it, expect } from 'vitest';
import { pmReducer } from '../PMContext';

const initialState = {
  threads: {},
  pmUnread: {},
  activePM: null,
  deletedPMs: {},
  loadedThreads: {},
};

describe('pmReducer', () => {
  describe('ADD_PM_MESSAGE', () => {
    it('adds a message to a new thread', () => {
      const msg = { from: 'alice', text: 'hi', isSelf: false, to: 'me' };
      const next = pmReducer(initialState, { type: 'ADD_PM_MESSAGE', username: 'alice', message: msg });
      expect(next.threads.alice).toEqual([msg]);
    });

    it('appends to an existing thread', () => {
      const first = { from: 'alice', text: 'hi', isSelf: false, to: 'me' };
      const state = { ...initialState, threads: { alice: [first] } };
      const second = { from: 'me', text: 'hey', isSelf: true, to: 'alice' };
      const next = pmReducer(state, { type: 'ADD_PM_MESSAGE', username: 'alice', message: second });
      expect(next.threads.alice).toHaveLength(2);
      expect(next.threads.alice[1]).toEqual(second);
    });

    it('does not affect other threads', () => {
      const state = { ...initialState, threads: { bob: [{ text: 'yo' }] } };
      const msg = { from: 'alice', text: 'hi' };
      const next = pmReducer(state, { type: 'ADD_PM_MESSAGE', username: 'alice', message: msg });
      expect(next.threads.bob).toEqual([{ text: 'yo' }]);
      expect(next.threads.alice).toEqual([msg]);
    });
  });

  describe('INCREMENT_PM_UNREAD', () => {
    it('increments from zero', () => {
      const next = pmReducer(initialState, { type: 'INCREMENT_PM_UNREAD', username: 'alice' });
      expect(next.pmUnread.alice).toBe(1);
    });

    it('increments existing count', () => {
      const state = { ...initialState, pmUnread: { alice: 2 } };
      const next = pmReducer(state, { type: 'INCREMENT_PM_UNREAD', username: 'alice' });
      expect(next.pmUnread.alice).toBe(3);
    });
  });

  describe('CLEAR_PM_UNREAD', () => {
    it('clears unread count for a user', () => {
      const state = { ...initialState, pmUnread: { alice: 5 } };
      const next = pmReducer(state, { type: 'CLEAR_PM_UNREAD', username: 'alice' });
      expect(next.pmUnread.alice).toBe(0);
    });

    it('is idempotent — returns same state if no unread', () => {
      const next = pmReducer(initialState, { type: 'CLEAR_PM_UNREAD', username: 'alice' });
      expect(next).toBe(initialState);
    });
  });

  describe('SET_ACTIVE_PM', () => {
    it('sets the active PM conversation', () => {
      const next = pmReducer(initialState, { type: 'SET_ACTIVE_PM', username: 'alice' });
      expect(next.activePM).toBe('alice');
    });

    it('can set to null', () => {
      const state = { ...initialState, activePM: 'alice' };
      const next = pmReducer(state, { type: 'SET_ACTIVE_PM', username: null });
      expect(next.activePM).toBeNull();
    });
  });

  describe('EDIT_PM_MESSAGE', () => {
    it('updates text and adds edited_at for matching msg_id', () => {
      const state = {
        ...initialState,
        threads: { alice: [{ msg_id: 'pm-1', from: 'me', text: 'hello' }] },
      };
      const next = pmReducer(state, {
        type: 'EDIT_PM_MESSAGE',
        username: 'alice',
        msg_id: 'pm-1',
        text: 'hello edited',
      });
      expect(next.threads.alice[0].text).toBe('hello edited');
      expect(next.threads.alice[0].edited_at).toBeDefined();
    });

    it('does not modify messages with different msg_id', () => {
      const state = {
        ...initialState,
        threads: { alice: [
          { msg_id: 'pm-1', from: 'me', text: 'first' },
          { msg_id: 'pm-2', from: 'me', text: 'second' },
        ]},
      };
      const next = pmReducer(state, {
        type: 'EDIT_PM_MESSAGE',
        username: 'alice',
        msg_id: 'pm-1',
        text: 'first edited',
      });
      expect(next.threads.alice[0].text).toBe('first edited');
      expect(next.threads.alice[1].text).toBe('second');
    });
  });

  describe('DELETE_PM_MESSAGE', () => {
    it('replaces text with [deleted] and sets is_deleted', () => {
      const state = {
        ...initialState,
        threads: { alice: [{ msg_id: 'pm-1', from: 'me', text: 'hello' }] },
      };
      const next = pmReducer(state, {
        type: 'DELETE_PM_MESSAGE',
        username: 'alice',
        msg_id: 'pm-1',
      });
      expect(next.threads.alice[0].text).toBe('[deleted]');
      expect(next.threads.alice[0].is_deleted).toBe(true);
    });
  });

  describe('ADD_PM_REACTION', () => {
    it('adds a reaction to a message', () => {
      const state = {
        ...initialState,
        threads: { alice: [{ msg_id: 'pm-1', from: 'me', text: 'hi' }] },
      };
      const next = pmReducer(state, {
        type: 'ADD_PM_REACTION',
        username: 'alice',
        msg_id: 'pm-1',
        emoji: '👍',
        reactor: 'alice',
        reactor_id: 2,
      });
      expect(next.threads.alice[0].reactions).toHaveLength(1);
      expect(next.threads.alice[0].reactions[0]).toEqual({
        emoji: '👍',
        username: 'alice',
        user_id: 2,
      });
    });

    it('appends to existing reactions', () => {
      const state = {
        ...initialState,
        threads: { alice: [{
          msg_id: 'pm-1',
          from: 'me',
          text: 'hi',
          reactions: [{ emoji: '❤️', username: 'bob', user_id: 3 }],
        }]},
      };
      const next = pmReducer(state, {
        type: 'ADD_PM_REACTION',
        username: 'alice',
        msg_id: 'pm-1',
        emoji: '👍',
        reactor: 'alice',
        reactor_id: 2,
      });
      expect(next.threads.alice[0].reactions).toHaveLength(2);
    });
  });

  describe('REMOVE_PM_REACTION', () => {
    it('removes a specific reaction by emoji and username', () => {
      const state = {
        ...initialState,
        threads: { alice: [{
          msg_id: 'pm-1',
          from: 'me',
          text: 'hi',
          reactions: [
            { emoji: '👍', username: 'alice', user_id: 2 },
            { emoji: '❤️', username: 'bob', user_id: 3 },
          ],
        }]},
      };
      const next = pmReducer(state, {
        type: 'REMOVE_PM_REACTION',
        username: 'alice',
        msg_id: 'pm-1',
        emoji: '👍',
        reactor: 'alice',
      });
      expect(next.threads.alice[0].reactions).toHaveLength(1);
      expect(next.threads.alice[0].reactions[0].emoji).toBe('❤️');
    });
  });

  describe('CLEAR_PM_THREAD', () => {
    it('removes the thread for the given username', () => {
      const state = {
        ...initialState,
        threads: {
          alice: [{ msg_id: 'pm-1', text: 'hi' }],
          bob: [{ msg_id: 'pm-2', text: 'hey' }],
        },
      };
      const next = pmReducer(state, { type: 'REMOVE_PM_THREAD', username: 'alice' });
      expect(next.threads.alice).toBeUndefined();
      expect(next.threads.bob).toBeDefined();
    });
  });

  describe('DELETE_PM_CONVERSATION', () => {
    it('adds username to deletedPMs with a timestamp', () => {
      const next = pmReducer(initialState, {
        type: 'DELETE_PM_CONVERSATION',
        username: 'alice',
      });
      expect(next.deletedPMs.alice).toBeDefined();
      expect(typeof next.deletedPMs.alice).toBe('string');
    });
  });

  describe('RESTORE_PM_CONVERSATION', () => {
    it('removes username from deletedPMs', () => {
      const state = {
        ...initialState,
        deletedPMs: { alice: '2024-01-01T00:00:00.000Z' },
      };
      const next = pmReducer(state, {
        type: 'RESTORE_PM_CONVERSATION',
        username: 'alice',
      });
      expect(next.deletedPMs.alice).toBeUndefined();
    });
  });

  describe('default', () => {
    it('returns current state for unknown action', () => {
      const next = pmReducer(initialState, { type: 'UNKNOWN' });
      expect(next).toBe(initialState);
    });
  });
});

describe('pmReducer new actions', () => {
  const baseState = {
    threads: {}, pmUnread: {}, activePM: null, deletedPMs: {}, loadedThreads: {},
  };

  describe('SET_PM_THREAD', () => {
    it('replaces the thread for the given username', () => {
      const messages = [{ from: 'alice', text: 'hi', msg_id: '1' }];
      const state = pmReducer(baseState, { type: 'SET_PM_THREAD', username: 'alice', messages });
      expect(state.threads.alice).toEqual(messages);
    });

    it('overwrites existing thread', () => {
      const existing = { ...baseState, threads: { alice: [{ text: 'old' }] } };
      const state = pmReducer(existing, {
        type: 'SET_PM_THREAD', username: 'alice', messages: [{ text: 'new' }],
      });
      expect(state.threads.alice).toEqual([{ text: 'new' }]);
    });
  });

  describe('MARK_THREAD_LOADED', () => {
    it('sets loadedThreads[username] to true', () => {
      const state = pmReducer(baseState, { type: 'MARK_THREAD_LOADED', username: 'alice' });
      expect(state.loadedThreads.alice).toBe(true);
    });
  });

  describe('INIT_PM_THREAD', () => {
    it('creates an empty thread if none exists', () => {
      const state = pmReducer(baseState, { type: 'INIT_PM_THREAD', username: 'alice' });
      expect(state.threads.alice).toEqual([]);
    });

    it('does not overwrite an existing live thread', () => {
      const existing = { ...baseState, threads: { alice: [{ text: 'live msg' }] } };
      const state = pmReducer(existing, { type: 'INIT_PM_THREAD', username: 'alice' });
      expect(state.threads.alice).toEqual([{ text: 'live msg' }]);
    });
  });
});
