import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import http from '../http';

describe('http client', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('creates an axios instance with the correct baseURL', () => {
    expect(http.defaults.baseURL).toBe('http://localhost:8000');
  });

  it('attaches Authorization header when token exists in sessionStorage', async () => {
    sessionStorage.setItem('token', 'test-jwt-token');

    // Access the interceptor and simulate a request config
    const interceptor = http.interceptors.request.handlers[0];
    const config = { headers: {} };
    const result = interceptor.fulfilled(config);

    expect(result.headers.Authorization).toBe('Bearer test-jwt-token');
  });

  it('does not attach Authorization header when no token', async () => {
    const interceptor = http.interceptors.request.handlers[0];
    const config = { headers: {} };
    const result = interceptor.fulfilled(config);

    expect(result.headers.Authorization).toBeUndefined();
  });

  describe('response interceptor — 401 auto-logout', () => {
    let responseInterceptor;
    const originalLocation = window.location;

    beforeEach(() => {
      // Access the response interceptor (index 0)
      responseInterceptor = http.interceptors.response.handlers[0];
      // Replace window.location with a writable mock
      delete window.location;
      window.location = { pathname: '/chat', href: '' };
    });

    afterEach(() => {
      window.location = originalLocation;
    });

    it('passes through successful responses unchanged', () => {
      const response = { status: 200, data: { ok: true } };
      expect(responseInterceptor.fulfilled(response)).toBe(response);
    });

    it('clears session and redirects to /login on 401 with a token', async () => {
      sessionStorage.setItem('token', 'stale-token');
      sessionStorage.setItem('user', 'alice');

      const error = {
        response: { status: 401 },
        config: { headers: { Authorization: 'Bearer stale-token' }, url: '/rooms' },
      };

      await expect(responseInterceptor.rejected(error)).rejects.toBe(error);

      expect(sessionStorage.getItem('token')).toBeNull();
      expect(sessionStorage.getItem('user')).toBeNull();
      expect(window.location.href).toBe('/login');
    });

    it('does NOT redirect if already on /login', async () => {
      window.location.pathname = '/login';
      const error = {
        response: { status: 401 },
        config: { headers: { Authorization: 'Bearer tok' }, url: '/rooms' },
      };

      await expect(responseInterceptor.rejected(error)).rejects.toBe(error);
      expect(window.location.href).toBe('');
    });

    it('does NOT clear session or redirect on 401 without a token', async () => {
      sessionStorage.setItem('token', 'should-stay');
      const error = {
        response: { status: 401 },
        config: { headers: {}, url: '/auth/login' },
      };

      await expect(responseInterceptor.rejected(error)).rejects.toBe(error);
      expect(sessionStorage.getItem('token')).toBe('should-stay');
      expect(window.location.href).toBe('');
    });

    it('does NOT auto-logout for /auth/profile/email (password verification endpoint)', async () => {
      sessionStorage.setItem('token', 'tok');
      const error = {
        response: { status: 401 },
        config: { headers: { Authorization: 'Bearer tok' }, url: '/auth/profile/email' },
      };

      await expect(responseInterceptor.rejected(error)).rejects.toBe(error);
      expect(sessionStorage.getItem('token')).toBe('tok');
      expect(window.location.href).toBe('');
    });

    it('does NOT auto-logout for /auth/profile/password', async () => {
      sessionStorage.setItem('token', 'tok');
      const error = {
        response: { status: 401 },
        config: { headers: { Authorization: 'Bearer tok' }, url: '/auth/profile/password' },
      };

      await expect(responseInterceptor.rejected(error)).rejects.toBe(error);
      expect(sessionStorage.getItem('token')).toBe('tok');
    });

    it('does NOT auto-logout for /auth/2fa/disable', async () => {
      sessionStorage.setItem('token', 'tok');
      const error = {
        response: { status: 401 },
        config: { headers: { Authorization: 'Bearer tok' }, url: '/auth/2fa/disable' },
      };

      await expect(responseInterceptor.rejected(error)).rejects.toBe(error);
      expect(sessionStorage.getItem('token')).toBe('tok');
    });

    it('passes through non-401 errors without side effects', async () => {
      sessionStorage.setItem('token', 'tok');
      const error = {
        response: { status: 500 },
        config: { headers: { Authorization: 'Bearer tok' }, url: '/rooms' },
      };

      await expect(responseInterceptor.rejected(error)).rejects.toBe(error);
      expect(sessionStorage.getItem('token')).toBe('tok');
      expect(window.location.href).toBe('');
    });
  });
});
