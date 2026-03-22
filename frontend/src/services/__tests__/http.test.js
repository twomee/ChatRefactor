import { describe, it, expect, beforeEach } from 'vitest';
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
});
