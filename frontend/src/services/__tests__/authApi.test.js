import { describe, it, expect, vi, beforeEach } from 'vitest';
import { register, login, logout, ping } from '../authApi';
import http from '../http';

vi.mock('../http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

describe('authApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('register', () => {
    it('posts to /auth/register with username and password', async () => {
      http.post.mockResolvedValue({ data: { message: 'ok' } });
      await register('alice', 'pass123');
      expect(http.post).toHaveBeenCalledWith('/auth/register', { username: 'alice', password: 'pass123' });
    });
  });

  describe('login', () => {
    it('posts to /auth/login with credentials', async () => {
      http.post.mockResolvedValue({ data: { access_token: 'jwt' } });
      const res = await login('alice', 'pass123');
      expect(http.post).toHaveBeenCalledWith('/auth/login', { username: 'alice', password: 'pass123' });
      expect(res.data.access_token).toBe('jwt');
    });
  });

  describe('logout', () => {
    it('posts to /auth/logout', async () => {
      http.post.mockResolvedValue({ data: {} });
      await logout();
      expect(http.post).toHaveBeenCalledWith('/auth/logout');
    });
  });

  describe('ping', () => {
    it('posts to /auth/ping', async () => {
      http.post.mockResolvedValue({ data: {} });
      await ping();
      expect(http.post).toHaveBeenCalledWith('/auth/ping');
    });
  });
});
