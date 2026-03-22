import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { AuthProvider, useAuth } from '../AuthContext';

// Mock the ping function to prevent real HTTP calls
vi.mock('../../services/authApi', () => ({
  ping: vi.fn().mockResolvedValue({}),
}));

describe('AuthContext', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  function renderAuthHook() {
    return renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });
  }

  it('starts with null user and token when sessionStorage is empty', () => {
    const { result } = renderAuthHook();
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
  });

  it('restores user and token from sessionStorage on mount', () => {
    sessionStorage.setItem('token', 'saved-jwt');
    sessionStorage.setItem('user', JSON.stringify({ username: 'alice', is_global_admin: false }));

    const { result } = renderAuthHook();
    expect(result.current.token).toBe('saved-jwt');
    expect(result.current.user.username).toBe('alice');
  });

  it('login sets user, token, and persists to sessionStorage', () => {
    const { result } = renderAuthHook();

    act(() => {
      result.current.login('new-jwt', { username: 'bob', is_global_admin: true });
    });

    expect(result.current.token).toBe('new-jwt');
    expect(result.current.user.username).toBe('bob');
    expect(sessionStorage.getItem('token')).toBe('new-jwt');
    expect(JSON.parse(sessionStorage.getItem('user')).username).toBe('bob');
  });

  it('logout clears user, token, and sessionStorage', () => {
    sessionStorage.setItem('token', 'old-jwt');
    sessionStorage.setItem('user', JSON.stringify({ username: 'alice' }));
    const { result } = renderAuthHook();

    act(() => {
      result.current.logout();
    });

    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
    expect(sessionStorage.getItem('token')).toBeNull();
    expect(sessionStorage.getItem('user')).toBeNull();
  });
});
