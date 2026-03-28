import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// We need to re-import after each test because the module has internal state
// (permissionGranted). Use dynamic imports for isolation.

describe('notifications', () => {
  let originalNotification;

  beforeEach(() => {
    originalNotification = globalThis.Notification;
    vi.useFakeTimers();
  });

  afterEach(() => {
    globalThis.Notification = originalNotification;
    vi.useRealTimers();
    vi.resetModules();
  });

  it('requestNotificationPermission returns false when Notification API is not available', async () => {
    delete globalThis.Notification;
    const { requestNotificationPermission } = await import('../notifications.js');
    const result = await requestNotificationPermission();
    expect(result).toBe(false);
  });

  it('requestNotificationPermission returns true when permission is already granted', async () => {
    globalThis.Notification = { permission: 'granted', requestPermission: vi.fn() };
    const { requestNotificationPermission } = await import('../notifications.js');
    const result = await requestNotificationPermission();
    expect(result).toBe(true);
  });

  it('requestNotificationPermission returns false when permission is denied', async () => {
    globalThis.Notification = { permission: 'denied', requestPermission: vi.fn() };
    const { requestNotificationPermission } = await import('../notifications.js');
    const result = await requestNotificationPermission();
    expect(result).toBe(false);
  });

  it('requestNotificationPermission requests permission when default', async () => {
    globalThis.Notification = {
      permission: 'default',
      requestPermission: vi.fn().mockResolvedValue('granted'),
    };
    const { requestNotificationPermission } = await import('../notifications.js');
    const result = await requestNotificationPermission();
    expect(result).toBe(true);
    expect(globalThis.Notification.requestPermission).toHaveBeenCalled();
  });

  it('sendBrowserNotification does not fire when document has focus', async () => {
    const mockConstructor = vi.fn();
    globalThis.Notification = Object.assign(mockConstructor, { permission: 'granted' });
    const { requestNotificationPermission, sendBrowserNotification } = await import('../notifications.js');
    await requestNotificationPermission();

    // Force document.hasFocus() to return true
    const originalHasFocus = document.hasFocus;
    document.hasFocus = () => true;
    try {
      sendBrowserNotification('Title', 'Body');
      expect(mockConstructor).not.toHaveBeenCalled();
    } finally {
      document.hasFocus = originalHasFocus;
    }
  });
});
