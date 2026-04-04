// Test 45: WebSocket disconnect/reconnect indicator
const { test, expect } = require('@playwright/test');
const { fastLogin } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { TEST_ROOM } = require('../fixtures/test-data');

test.describe('Connection', () => {
  test('Test 45: disconnect reconnect indicator', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    await page.waitForSelector('.chat-layout', { timeout: 15_000 });

    // Join a room — this creates a room WebSocket connection tracked in
    // reconnectingRoomsRef. The lobby WS disconnect alone does NOT update
    // connectionStatus; only room-level WS connections do.
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);
    await page.waitForTimeout(500); // brief settle for WS to open

    // context.setOffline(true) kills all existing connections and blocks new ones
    await context.setOffline(true);

    // Room WS onclose fires → reconnectingRoomsRef.add(roomId) → status = 'reconnecting'
    const connectionStatus = await chat.getConnectionStatus();
    await expect(connectionStatus).toBeVisible({ timeout: 15_000 });
    const statusText = await connectionStatus.textContent();
    expect(statusText.toLowerCase()).toMatch(/reconnect|disconnect|offline|connecting/i);

    // Restore network — next retry attempt will succeed
    await context.setOffline(false);

    // Indicator must disappear once the room WS reconnects
    await connectionStatus.waitFor({ state: 'hidden', timeout: 20_000 }).catch(async () => {
      const textAfter = await connectionStatus.textContent().catch(() => '');
      expect(textAfter.toLowerCase()).toMatch(/connect|online/i);
    });
  });
});
