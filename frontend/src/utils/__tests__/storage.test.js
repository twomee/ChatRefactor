import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getJoinedRooms, addJoinedRoom, removeJoinedRoom, getPMThreadList, savePMThreadList, addPMThread, removePMThread } from '../storage';

describe('storage helpers', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe('getJoinedRooms', () => {
    it('returns empty array when no data stored', () => {
      expect(getJoinedRooms('alice')).toEqual([]);
    });

    it('returns stored rooms for a user', () => {
      localStorage.setItem('chatbox_joined_rooms_alice', JSON.stringify(['room1', 'room2']));
      expect(getJoinedRooms('alice')).toEqual(['room1', 'room2']);
    });

    it('uses "anonymous" key when username is null/undefined', () => {
      localStorage.setItem('chatbox_joined_rooms_anonymous', JSON.stringify(['lobby']));
      expect(getJoinedRooms(null)).toEqual(['lobby']);
      expect(getJoinedRooms(undefined)).toEqual(['lobby']);
    });

    it('isolates data between users', () => {
      localStorage.setItem('chatbox_joined_rooms_alice', JSON.stringify(['room1']));
      localStorage.setItem('chatbox_joined_rooms_bob', JSON.stringify(['room2']));
      expect(getJoinedRooms('alice')).toEqual(['room1']);
      expect(getJoinedRooms('bob')).toEqual(['room2']);
    });

    it('returns empty array and removes key when stored value is corrupted JSON', () => {
      localStorage.setItem('chatbox_joined_rooms_alice', 'not-valid-json{{{');
      const result = getJoinedRooms('alice');
      expect(result).toEqual([]);
      expect(localStorage.getItem('chatbox_joined_rooms_alice')).toBeNull();
    });
  });

  describe('addJoinedRoom', () => {
    it('adds a room to an empty list', () => {
      addJoinedRoom('alice', 'room1');
      expect(getJoinedRooms('alice')).toEqual(['room1']);
    });

    it('appends a room to an existing list', () => {
      addJoinedRoom('alice', 'room1');
      addJoinedRoom('alice', 'room2');
      expect(getJoinedRooms('alice')).toEqual(['room1', 'room2']);
    });

    it('does not add duplicate rooms', () => {
      addJoinedRoom('alice', 'room1');
      addJoinedRoom('alice', 'room1');
      expect(getJoinedRooms('alice')).toEqual(['room1']);
    });
  });

  describe('removeJoinedRoom', () => {
    it('removes a room from the list', () => {
      addJoinedRoom('alice', 'room1');
      addJoinedRoom('alice', 'room2');
      removeJoinedRoom('alice', 'room1');
      expect(getJoinedRooms('alice')).toEqual(['room2']);
    });

    it('does nothing when removing a non-existent room', () => {
      addJoinedRoom('alice', 'room1');
      removeJoinedRoom('alice', 'nonexistent');
      expect(getJoinedRooms('alice')).toEqual(['room1']);
    });

    it('handles removing from empty list', () => {
      removeJoinedRoom('alice', 'room1');
      expect(getJoinedRooms('alice')).toEqual([]);
    });
  });
});

describe('PM thread list helpers', () => {
  beforeEach(() => localStorage.clear());

  it('getPMThreadList returns empty array when nothing saved', () => {
    expect(getPMThreadList('alice')).toEqual([]);
  });

  it('savePMThreadList persists list under per-user key', () => {
    savePMThreadList('alice', ['bob', 'charlie']);
    expect(getPMThreadList('alice')).toEqual(['bob', 'charlie']);
  });

  it('getPMThreadList is isolated per user', () => {
    savePMThreadList('alice', ['bob']);
    expect(getPMThreadList('carol')).toEqual([]);
  });

  it('addPMThread appends a new username', () => {
    addPMThread('alice', 'bob');
    expect(getPMThreadList('alice')).toContain('bob');
  });

  it('addPMThread is idempotent — does not duplicate', () => {
    addPMThread('alice', 'bob');
    addPMThread('alice', 'bob');
    const list = getPMThreadList('alice');
    expect(list.filter(u => u === 'bob').length).toBe(1);
  });

  it('addPMThread preserves existing entries', () => {
    addPMThread('alice', 'bob');
    addPMThread('alice', 'charlie');
    expect(getPMThreadList('alice')).toEqual(['bob', 'charlie']);
  });

  it('getPMThreadList returns empty array when stored value is corrupted JSON', () => {
    localStorage.setItem('chatbox_pm_threads_alice', 'BAD_JSON{{');
    expect(getPMThreadList('alice')).toEqual([]);
  });

  it('removePMThread removes the given username from the list', () => {
    savePMThreadList('alice', ['bob', 'charlie', 'dave']);
    removePMThread('alice', 'charlie');
    expect(getPMThreadList('alice')).toEqual(['bob', 'dave']);
  });

  it('removePMThread is a no-op when username is not in the list', () => {
    savePMThreadList('alice', ['bob']);
    removePMThread('alice', 'nonexistent');
    expect(getPMThreadList('alice')).toEqual(['bob']);
  });
});
