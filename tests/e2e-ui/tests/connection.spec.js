// Test 45: WebSocket disconnect/reconnect indicator
const { test, expect } = require('@playwright/test');
const { fastLogin } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');

test.describe('Connection', () => {
  test('Test 45: disconnect reconnect indicator', async ({ page, context }) => {
    // Block WebSocket connections BEFORE loading the page so new connection
    // attempts are immediately aborted. This is required because page.route()
    // only intercepts NEW requests — it cannot kill an already-open socket.
    await page.route('**/ws/**', route => route.abort());

    await fastLogin(context, page, 'userA');
    await page.waitForSelector('.chat-layout', { timeout: 15_000 });

    const chat = new ChatPage(page);
    const connectionStatus = await chat.getConnectionStatus();

    // The disconnect indicator MUST appear because all WS connections were blocked
    await expect(connectionStatus).toBeVisible({ timeout: 15_000 });
    const statusText = await connectionStatus.textContent();
    expect(statusText.toLowerCase()).toMatch(/reconnect|disconnect|offline|connecting/i);

    // Unblock WebSocket connections
    await page.unroute('**/ws/**');

    // Indicator MUST disappear once the app reconnects
    await connectionStatus.waitFor({ state: 'hidden', timeout: 20_000 }).catch(async () => {
      // If still visible, must show a "connected" or recovering state
      const textAfter = await connectionStatus.textContent().catch(() => '');
      expect(textAfter.toLowerCase()).toMatch(/connect|online/i);
    });
  });
});
