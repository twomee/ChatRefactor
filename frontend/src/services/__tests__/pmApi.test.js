import { describe, it, expect, vi, beforeEach } from 'vitest';
import { sendPM, editPM, deletePM, addPMReaction, removePMReaction } from '../pmApi';
import http from '../http';

vi.mock('../http', () => ({
  default: {
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('pmApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('sendPM', () => {
    it('sends PM to the correct endpoint with payload', async () => {
      http.post.mockResolvedValue({ data: { status: 'sent' } });
      await sendPM('bob', 'Hello!');
      expect(http.post).toHaveBeenCalledWith('/pm/send', { to: 'bob', text: 'Hello!' });
    });
  });

  describe('editPM', () => {
    it('patches /pm/edit/:msgId with text', async () => {
      http.patch.mockResolvedValue({ data: { status: 'edited' } });
      await editPM('msg-123', 'Updated text');
      expect(http.patch).toHaveBeenCalledWith('/pm/edit/msg-123', { text: 'Updated text' });
    });
  });

  describe('deletePM', () => {
    it('deletes /pm/delete/:msgId', async () => {
      http.delete.mockResolvedValue({ data: { status: 'deleted' } });
      await deletePM('msg-456');
      expect(http.delete).toHaveBeenCalledWith('/pm/delete/msg-456');
    });
  });

  describe('addPMReaction', () => {
    it('posts to /pm/reaction/:msgId with emoji', async () => {
      http.post.mockResolvedValue({ data: { status: 'added' } });
      await addPMReaction('msg-789', '👍');
      expect(http.post).toHaveBeenCalledWith('/pm/reaction/msg-789', { emoji: '👍' });
    });
  });

  describe('removePMReaction', () => {
    it('deletes /pm/reaction/:msgId/:emoji (URL encoded)', async () => {
      http.delete.mockResolvedValue({ data: { status: 'removed' } });
      await removePMReaction('msg-789', '👍');
      expect(http.delete).toHaveBeenCalledWith(
        `/pm/reaction/msg-789/${encodeURIComponent('👍')}`,
      );
    });
  });
});
