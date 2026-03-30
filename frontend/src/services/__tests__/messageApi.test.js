import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchLinkPreview, getMessageContext, clearHistory } from '../messageApi';
import http from '../http';

vi.mock('../http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('messageApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('fetchLinkPreview', () => {
    it('gets /messages/preview with url param', async () => {
      http.get.mockResolvedValue({ data: { title: 'Example', url: 'https://example.com' } });
      await fetchLinkPreview('https://example.com');
      expect(http.get).toHaveBeenCalledWith('/messages/preview', { params: { url: 'https://example.com' } });
    });
  });

  describe('getMessageContext', () => {
    it('gets context endpoint with default before/after values', async () => {
      http.get.mockResolvedValue({ data: { messages: [] } });
      await getMessageContext(5, 'abc123');
      expect(http.get).toHaveBeenCalledWith('/messages/rooms/5/context', {
        params: { message_id: 'abc123', before: 25, after: 25 },
      });
    });

    it('gets context endpoint with custom before/after values', async () => {
      http.get.mockResolvedValue({ data: { messages: [] } });
      await getMessageContext(3, 'xyz', 10, 10);
      expect(http.get).toHaveBeenCalledWith('/messages/rooms/3/context', {
        params: { message_id: 'xyz', before: 10, after: 10 },
      });
    });
  });

  describe('clearHistory', () => {
    it('posts to /messages/clear with room context_type and context_id', async () => {
      http.post.mockResolvedValue({ data: { message: 'cleared' } });
      await clearHistory('room', 42);
      expect(http.post).toHaveBeenCalledWith('/messages/clear', {
        context_type: 'room',
        context_id: 42,
      });
    });

    it('posts to /messages/clear with pm context_type and context_id', async () => {
      http.post.mockResolvedValue({ data: { message: 'cleared' } });
      await clearHistory('pm', 7);
      expect(http.post).toHaveBeenCalledWith('/messages/clear', {
        context_type: 'pm',
        context_id: 7,
      });
    });
  });
});
