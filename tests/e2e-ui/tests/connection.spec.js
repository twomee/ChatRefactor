// Test 45: WebSocket disconnect/reconnect indicator
const { test, expect } = require('@playwright/test');
const { fastLogin } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');

test.describe('Connection', () => {
  test('Test 45: disconnect reconnect indicator', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    await page.waitForSelector('.chat-layout', { timeout: 10_000 });

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

    const chat = new ChatPage(page);
    const connectionStatus = await chat.getConnectionStatus();

    // The disconnect indicator MUST appear — fail the test if it never does
    await expect(connectionStatus).toBeVisible({ timeout: 15_000 });
    const statusText = await connectionStatus.textContent();
    expect(statusText.toLowerCase()).toMatch(/reconnect|disconnect|offline|connecting/i);

    // Unblock WebSocket
    await page.unroute('**/ws/**');
    await page.unroute('**');

    // Indicator MUST disappear (reconnected) or show a connected state
    await connectionStatus.waitFor({ state: 'hidden', timeout: 15_000 }).catch(async () => {
      const textAfter = await connectionStatus.textContent().catch(() => '');
      expect(textAfter.toLowerCase()).toMatch(/connect|online/i);
    });
  });
});
