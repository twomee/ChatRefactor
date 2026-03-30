// src/services/__tests__/searchApi.test.js
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { searchMessages } from '../searchApi';
import http from '../http';

vi.mock('../http', () => ({
  default: {
    get: vi.fn(),
  },
}));

describe('searchApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('searchMessages', () => {
    it('calls GET /messages/search with query and default limit', async () => {
      http.get.mockResolvedValue({ data: [] });
      await searchMessages('hello');
      expect(http.get).toHaveBeenCalledWith('/messages/search', {
        params: { q: 'hello', limit: 20 },
        signal: null,
      });
    });

    it('includes room_id when provided', async () => {
      http.get.mockResolvedValue({ data: [] });
      await searchMessages('hello', 5);
      expect(http.get).toHaveBeenCalledWith('/messages/search', {
        params: { q: 'hello', limit: 20, room_id: 5 },
        signal: null,
      });
    });

    it('respects custom limit', async () => {
      http.get.mockResolvedValue({ data: [] });
      await searchMessages('test', null, 50);
      expect(http.get).toHaveBeenCalledWith('/messages/search', {
        params: { q: 'test', limit: 50 },
        signal: null,
      });
    });

    it('passes abort signal when provided', async () => {
      http.get.mockResolvedValue({ data: [] });
      const controller = new AbortController();
      await searchMessages('test', null, 20, controller.signal);
      expect(http.get).toHaveBeenCalledWith('/messages/search', {
        params: { q: 'test', limit: 20 },
        signal: controller.signal,
      });
    });
  });
});
