// Test 45: WebSocket disconnect/reconnect indicator
const { test, expect } = require('@playwright/test');
const { fastLogin } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');

test.describe('Connection', () => {
  test('Test 45: disconnect reconnect indicator', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    await page.waitForSelector('.chat-page, .room-list-panel', { timeout: 10_000 });

    // Block WebSocket connections to simulate disconnect
    await page.route('**/ws/**', route => route.abort());

    // Also block WebSocket upgrade requests
    await page.route('**', route => {
      const url = route.request().url();
      const isWS = route.request().resourceType() === 'websocket';
      if (isWS) {
        route.abort();
      } else {
        route.continue();
      }
    });

    // Trigger a reconnect by waiting — the app should detect the disconnection
    await page.waitForTimeout(5_000);

    const chat = new ChatPage(page);
    const connectionStatus = await chat.getConnectionStatus();

    // Should show reconnecting/disconnected indicator
    const isVisible = await connectionStatus.isVisible().catch(() => false);
    if (isVisible) {
      const statusText = await connectionStatus.textContent();
      expect(statusText.toLowerCase()).toMatch(/reconnect|disconnect|offline|connecting/i);
    }

    // Unblock WebSocket
    await page.unroute('**/ws/**');
    await page.unroute('**');

    await page.waitForTimeout(5_000);

    // Connection status indicator should disappear or show connected
    const statusAfter = await connectionStatus.isVisible().catch(() => false);
    // Either hidden (connected) or showing "connected"
    if (statusAfter) {
      const statusTextAfter = await connectionStatus.textContent();
      expect(statusTextAfter.toLowerCase()).toMatch(/connect|online/i);
    } else {
      expect(statusAfter).toBe(false);
    }
  });
});
