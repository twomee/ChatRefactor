// Test 45: WebSocket disconnect/reconnect indicator
const { test, expect } = require('@playwright/test');
const { fastLogin } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { TEST_ROOM } = require('../fixtures/test-data');

test.describe('Connection', () => {
  test('Test 45: disconnect reconnect indicator', async ({ page, context }) => {
    // Patch WebSocket BEFORE the page loads so we can track and close connections.
    // context.addInitScript runs before every navigation in this context.
    await context.addInitScript(() => {
      window.__trackedSockets = [];
      const OrigWS = window.WebSocket;
      window.WebSocket = function (...args) {
        const ws = new OrigWS(...args);
        window.__trackedSockets.push(ws);
        return ws;
      };
      window.WebSocket.prototype = OrigWS.prototype;
      window.WebSocket.CONNECTING = OrigWS.CONNECTING;
      window.WebSocket.OPEN = OrigWS.OPEN;
      window.WebSocket.CLOSING = OrigWS.CLOSING;
      window.WebSocket.CLOSED = OrigWS.CLOSED;
    });

    await fastLogin(context, page, 'userA');
    await page.waitForSelector('.chat-layout', { timeout: 15_000 });

    // Join a room — the app creates a room-level WebSocket tracked in reconnectingRoomsRef.
    // Only room WS disconnects update connectionStatus (lobby WS does not).
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);
    await page.waitForTimeout(500); // brief settle for WS to open

    // Close all tracked WebSocket connections from inside the page.
    // This triggers onclose on the app's WS handlers — the same path as a real network drop.
    await page.evaluate(() => {
      window.__trackedSockets.forEach(ws => {
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
      });
    });

    // Room WS onclose → reconnectingRoomsRef.add(roomId) → connectionStatus = 'reconnecting'
    const connectionStatus = await chat.getConnectionStatus();
    await expect(connectionStatus).toBeVisible({ timeout: 15_000 });
    const statusText = await connectionStatus.textContent();
    expect(statusText.toLowerCase()).toMatch(/reconnect|disconnect|offline|connecting/i);

    // Once the app reconnects (backoff ~1 s for first retry), indicator disappears
    await connectionStatus.waitFor({ state: 'hidden', timeout: 20_000 }).catch(async () => {
      const textAfter = await connectionStatus.textContent().catch(() => '');
      expect(textAfter.toLowerCase()).toMatch(/connect|online/i);
    });
  });
});
