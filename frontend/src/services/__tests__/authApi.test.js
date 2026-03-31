import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  register, login, logout, ping,
  setup2FA, verifySetup2FA, disable2FA, verifyLogin2FA, get2FAStatus,
  getProfile, updateEmail, updatePassword, forgotPassword, resetPassword,
} from '../authApi';
import http from '../http';

vi.mock('../http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
}));

describe('authApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('register', () => {
    it('posts to /auth/register with username, password, and email', async () => {
      http.post.mockResolvedValue({ data: { message: 'ok' } });
      await register('alice', '', 'alice@example.com');
      expect(http.post).toHaveBeenCalledWith('/auth/register', { username: 'alice', password: '', email: 'alice@example.com' });
    });

    it('posts to /auth/register with undefined email when omitted', async () => {
      http.post.mockResolvedValue({ data: { message: 'ok' } });
      await register('alice', '');
      expect(http.post).toHaveBeenCalledWith('/auth/register', { username: 'alice', password: '', email: undefined });
    });
  });

  describe('login', () => {
    it('posts to /auth/login with credentials', async () => {
      http.post.mockResolvedValue({ data: { access_token: 'jwt' } });
      const res = await login('alice', '');
      expect(http.post).toHaveBeenCalledWith('/auth/login', { username: 'alice', password: '' });
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

  // ── Profile Management ────────────────────────────────────────────────

  describe('getProfile', () => {
    it('gets /auth/profile and returns data', async () => {
      http.get.mockResolvedValue({ data: { username: 'alice', email: 'alice@example.com' } });
      const profile = await getProfile();
      expect(http.get).toHaveBeenCalledWith('/auth/profile');
      expect(profile.username).toBe('alice');
      expect(profile.email).toBe('alice@example.com');
    });
  });

  describe('updateEmail', () => {
    it('patches /auth/profile/email with new_email and current_password', async () => {
      http.patch.mockResolvedValue({ data: { message: 'email updated' } });
      const res = await updateEmail('new@example.com', '');
      expect(http.patch).toHaveBeenCalledWith('/auth/profile/email', {
        new_email: 'new@example.com',
        current_password: '',
      });
      expect(res.message).toBe('email updated');
    });
  });

  describe('updatePassword', () => {
    it('patches /auth/profile/password with current and new password', async () => {
      http.patch.mockResolvedValue({ data: { message: 'password updated' } });
      const res = await updatePassword('', '');
      expect(http.patch).toHaveBeenCalledWith('/auth/profile/password', {
        current_password: '',
        new_password: '',
      });
      expect(res.message).toBe('password updated');
    });
  });

  // ── Password Reset ────────────────────────────────────────────────────

  describe('forgotPassword', () => {
    it('posts to /auth/forgot-password with email', async () => {
      http.post.mockResolvedValue({ data: { message: 'email sent' } });
      const res = await forgotPassword('alice@example.com');
      expect(http.post).toHaveBeenCalledWith('/auth/forgot-password', { email: 'alice@example.com' });
      expect(res.message).toBe('email sent');
    });
  });

  describe('resetPassword', () => {
    it('posts to /auth/reset-password with token and new_password', async () => {
      http.post.mockResolvedValue({ data: { message: 'password reset' } });
      const res = await resetPassword('test-reset-token', '');
      expect(http.post).toHaveBeenCalledWith('/auth/reset-password', {
        token: 'test-reset-token',
        new_password: '',
      });
      expect(res.message).toBe('password reset');
    });
  });
});
