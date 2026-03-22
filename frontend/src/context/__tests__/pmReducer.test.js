import { describe, it, expect } from 'vitest';
import { pmReducer } from '../PMContext';

const initialState = {
  threads: {},
  pmUnread: {},
  activePM: null,
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

  describe('default', () => {
    it('returns current state for unknown action', () => {
      const next = pmReducer(initialState, { type: 'UNKNOWN' });
      expect(next).toBe(initialState);
    });
  });
});
