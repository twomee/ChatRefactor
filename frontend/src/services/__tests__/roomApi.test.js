import { describe, it, expect, vi, beforeEach } from 'vitest';
import { listRooms, createRoom } from '../roomApi';
import http from '../http';

vi.mock('../http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

describe('roomApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listRooms', () => {
    it('calls GET /rooms/ with custom validateStatus', async () => {
      http.get.mockResolvedValue({ data: [], status: 200 });
      await listRooms();
      expect(http.get).toHaveBeenCalledWith('/rooms/', { validateStatus: expect.any(Function) });
    });

    it('validateStatus accepts status codes below 500', () => {
      // Manually test the validateStatus function
      http.get.mockResolvedValue({ data: [] });
      listRooms();
      const options = http.get.mock.calls[0][1];
      expect(options.validateStatus(200)).toBe(true);
      expect(options.validateStatus(403)).toBe(true);
      expect(options.validateStatus(499)).toBe(true);
      expect(options.validateStatus(500)).toBe(false);
      expect(options.validateStatus(503)).toBe(false);
    });
  });

  describe('createRoom', () => {
    it('posts to /rooms/ with room name', async () => {
      http.post.mockResolvedValue({ data: { id: '1', name: 'general' } });
      const res = await createRoom('general');
      expect(http.post).toHaveBeenCalledWith('/rooms/', { name: 'general' });
      expect(res.data.name).toBe('general');
    });
  });
});
