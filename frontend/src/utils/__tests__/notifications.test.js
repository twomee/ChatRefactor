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

  it('sendBrowserNotification creates a Notification when unfocused and permission granted', async () => {
    const mockClose = vi.fn();
    let createdInstance;
    // vi.fn() must be used with mockImplementation (not mockReturnValue) for `new` calls
    const MockNotificationClass = vi.fn().mockImplementation(function(title, opts) {
      this.title = title;
      this.opts = opts;
      this.close = mockClose;
      createdInstance = this;
    });
    globalThis.Notification = Object.assign(MockNotificationClass, { permission: 'granted' });

    const { requestNotificationPermission, sendBrowserNotification } = await import('../notifications.js');
    await requestNotificationPermission();

    const originalHasFocus = document.hasFocus;
    document.hasFocus = () => false;
    try {
      sendBrowserNotification('Test Title', 'Test body');
      expect(MockNotificationClass).toHaveBeenCalledWith('Test Title', expect.objectContaining({
        body: 'Test body',
        icon: '/favicon.ico',
      }));
      // Auto-close fires after 5 seconds
      vi.advanceTimersByTime(5001);
      expect(mockClose).toHaveBeenCalled();
    } finally {
      document.hasFocus = originalHasFocus;
    }
  });

  it('sendBrowserNotification wires up onClick handler when provided', async () => {
    const mockClose = vi.fn();
    let createdInstance;
    const MockNotificationClass = vi.fn().mockImplementation(function(title, opts) {
      this.title = title;
      this.opts = opts;
      this.close = mockClose;
      createdInstance = this;
    });
    globalThis.Notification = Object.assign(MockNotificationClass, { permission: 'granted' });

    const { requestNotificationPermission, sendBrowserNotification } = await import('../notifications.js');
    await requestNotificationPermission();

    const originalHasFocus = document.hasFocus;
    const originalFocus = window.focus;
    const mockFocus = vi.fn();
    window.focus = mockFocus;
    document.hasFocus = () => false;
    try {
      const onClickFn = vi.fn();
      sendBrowserNotification('Title', 'Body', onClickFn);
      expect(typeof createdInstance.onclick).toBe('function');
      // Simulate click on the notification
      createdInstance.onclick();
      expect(mockFocus).toHaveBeenCalled();
      expect(onClickFn).toHaveBeenCalled();
      expect(mockClose).toHaveBeenCalled();
    } finally {
      document.hasFocus = originalHasFocus;
      window.focus = originalFocus;
    }
  });

  it('sendBrowserNotification does nothing when permissionGranted is false', async () => {
    const mockConstructor = vi.fn();
    globalThis.Notification = Object.assign(mockConstructor, { permission: 'default' });
    const { sendBrowserNotification } = await import('../notifications.js');

    const originalHasFocus = document.hasFocus;
    document.hasFocus = () => false;
    try {
      sendBrowserNotification('Title', 'Body');
      expect(mockConstructor).not.toHaveBeenCalled();
    } finally {
      document.hasFocus = originalHasFocus;
    }
  });
});
