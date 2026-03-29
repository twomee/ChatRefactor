import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  register, login, logout, ping,
  setup2FA, verifySetup2FA, disable2FA, verifyLogin2FA, get2FAStatus,
} from '../authApi';
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

  // ── 2FA API functions ────────────────────────────────────────────────

  describe('setup2FA', () => {
    it('posts to /auth/2fa/setup', async () => {
      http.post.mockResolvedValue({ data: { secret: 'ABC', otpauth_uri: 'otpauth://...' } });
      const res = await setup2FA();
      expect(http.post).toHaveBeenCalledWith('/auth/2fa/setup');
      expect(res.data.secret).toBe('ABC');
    });
  });

  describe('verifySetup2FA', () => {
    it('posts to /auth/2fa/verify-setup with code', async () => {
      http.post.mockResolvedValue({ data: { message: 'ok' } });
      await verifySetup2FA('123456');
      expect(http.post).toHaveBeenCalledWith('/auth/2fa/verify-setup', { code: '123456' });
    });
  });

  describe('disable2FA', () => {
    it('posts to /auth/2fa/disable with code', async () => {
      http.post.mockResolvedValue({ data: { message: 'ok' } });
      await disable2FA('654321');
      expect(http.post).toHaveBeenCalledWith('/auth/2fa/disable', { code: '654321' });
    });
  });

  describe('verifyLogin2FA', () => {
    it('posts to /auth/2fa/verify-login with temp_token and code', async () => {
      http.post.mockResolvedValue({ data: { access_token: 'jwt2fa' } });
      const res = await verifyLogin2FA('temp123', '123456');
      expect(http.post).toHaveBeenCalledWith('/auth/2fa/verify-login', { temp_token: 'temp123', code: '123456' });
      expect(res.data.access_token).toBe('jwt2fa');
    });
  });

  describe('get2FAStatus', () => {
    it('gets /auth/2fa/status', async () => {
      http.get.mockResolvedValue({ data: { is_2fa_enabled: false } });
      const res = await get2FAStatus();
      expect(http.get).toHaveBeenCalledWith('/auth/2fa/status');
      expect(res.data.is_2fa_enabled).toBe(false);
    });
  });
});
