import { describe, it, expect, beforeEach } from 'vitest';
import { getJoinedRooms, addJoinedRoom, removeJoinedRoom } from '../storage';

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
