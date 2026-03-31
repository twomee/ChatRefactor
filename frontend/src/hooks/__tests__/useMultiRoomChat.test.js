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
import { createHandleMessage } from '../useMultiRoomChat';

describe('createHandleMessage', () => {
  let dispatch;
  let pmDispatch;
  let user;
  let activeRoomIdRef;
  let seenMsgIdsRef;
  let pmStateRef;
  let lastMsgTimeRef;
  let exitRoomRef;

  beforeEach(() => {
    dispatch = vi.fn();
    pmDispatch = vi.fn();
    user = { username: 'alice' };
    activeRoomIdRef = { current: null };
    seenMsgIdsRef = { current: new Set() };
    pmStateRef = { current: { threads: {}, activePM: null } };
    lastMsgTimeRef = { current: new Map() };
    exitRoomRef = { current: vi.fn() };
    vi.clearAllMocks();
  });

  function makeHandler() {
    return createHandleMessage({
      dispatch,
      pmDispatch,
      user,
      activeRoomIdRef,
      seenMsgIdsRef,
      pmStateRef,
      lastMsgTimeRef,
      exitRoomRef,
    });
  }

  describe('file_shared event routing', () => {
    it('dispatches ADD_PM_MESSAGE to pmDispatch for PM files (is_private: true) — sender is other user', () => {
      const handler = makeHandler();
      handler({
        type: 'file_shared',
        is_private: true,
        from: 'bob',
        to: 'alice',
        filename: 'photo.jpg',
        file_id: 42,
        size: 1024,
        timestamp: '2024-01-01T00:00:00Z',
      });

      expect(pmDispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'ADD_PM_MESSAGE',
          username: 'bob',
          message: expect.objectContaining({
            isFile: true,
            from: 'bob',
            text: 'photo.jpg',
            fileId: 42,
            fileSize: 1024,
          }),
        })
      );
      // Regular room dispatch should NOT receive ADD_MESSAGE
      const addMsgCalls = dispatch.mock.calls.filter(
        ([action]) => action.type === 'ADD_MESSAGE'
      );
      expect(addMsgCalls).toHaveLength(0);
    });

    it('dispatches ADD_PM_MESSAGE to pmDispatch for PM files (is_private: true) — sender is current user (self-send)', () => {
      const handler = makeHandler();
      handler({
        type: 'file_shared',
        is_private: true,
        from: 'alice',  // current user sent this
        to: 'bob',
        filename: 'doc.pdf',
        file_id: 99,
        size: 2048,
        timestamp: '2024-01-01T00:00:00Z',
      });

      // otherUser should be 'bob' because from === user.username
      expect(pmDispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'ADD_PM_MESSAGE',
          username: 'bob',
        })
      );
    });

    it('dispatches ADD_MESSAGE to room dispatch for room files (is_private: false)', () => {
      const handler = makeHandler();
      handler({
        type: 'file_shared',
        is_private: false,
        from: 'bob',
        room_id: 5,
        filename: 'image.png',
        file_id: 7,
        size: 512,
      });

      expect(dispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'ADD_MESSAGE',
          roomId: 5,
          message: expect.objectContaining({
            isFile: true,
            from: 'bob',
            text: 'image.png',
            fileId: 7,
            fileSize: 512,
          }),
        })
      );
      // pmDispatch should NOT be called for room files
      const addPMCalls = pmDispatch.mock.calls.filter(
        ([action]) => action.type === 'ADD_PM_MESSAGE'
      );
      expect(addPMCalls).toHaveLength(0);
    });

    it('dispatches ADD_MESSAGE for room files when is_private is absent/falsy', () => {
      const handler = makeHandler();
      handler({
        type: 'file_shared',
        from: 'carol',
        room_id: 3,
        filename: 'file.zip',
        file_id: 11,
        size: 4096,
      });

      expect(dispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'ADD_MESSAGE',
          roomId: 3,
        })
      );
    });
  });

  describe('private_message event', () => {
    it('calls addPMThread when a PM arrives from another user', () => {
      const handler = makeHandler();
      handler({
        type: 'private_message',
        from: 'bob',
        to: 'alice',
        text: 'hello',
        msg_id: 'pm-1',
        self: false,
      });

      expect(addPMThread).toHaveBeenCalledWith('alice', 'bob');
    });

    it('calls addPMThread when current user sends a PM (self: true)', () => {
      const handler = makeHandler();
      handler({
        type: 'private_message',
        from: 'alice',
        to: 'bob',
        text: 'hey',
        msg_id: 'pm-2',
        self: true,
      });

      // otherUser is msg.to when msg.self is true
      expect(addPMThread).toHaveBeenCalledWith('alice', 'bob');
    });

    it('still dispatches ADD_PM_MESSAGE in addition to calling addPMThread', () => {
      const handler = makeHandler();
      handler({
        type: 'private_message',
        from: 'bob',
        to: 'alice',
        text: 'hi',
        msg_id: 'pm-3',
        self: false,
      });

      expect(pmDispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'ADD_PM_MESSAGE',
          username: 'bob',
        })
      );
    });
  });
});
