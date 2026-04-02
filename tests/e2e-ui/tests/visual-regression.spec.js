// Test 47: Visual regression screenshots
const { test, expect } = require('@playwright/test');
const { fastLogin } = require('../fixtures/helpers');
const { AuthPage } = require('../fixtures/auth');
const { ChatPage } = require('../fixtures/chat');
const { SettingsPage } = require('../fixtures/settings');
const { AdminPage } = require('../fixtures/admin');
const { TEST_ROOM } = require('../fixtures/test-data');

test.describe('Visual Regression', () => {
  test('Test 47: full-page screenshots of all page states', async ({ page, context }) => {
    // 1. Login page — Sign In tab
    const auth = new AuthPage(page);
    await auth.goto();
    await expect(page).toHaveScreenshot('login-signin.png', { fullPage: true });

    // 2. Login page — Register tab
    await auth.switchToRegister();
    await page.waitForTimeout(300);
    await expect(page).toHaveScreenshot('login-register.png', { fullPage: true });

    // 3. Chat with a room selected
    await fastLogin(context, page, 'userA');
    await page.waitForSelector('.chat-page, .room-list-panel', { timeout: 10_000 });
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);
    await page.waitForTimeout(1_000);
    await expect(page).toHaveScreenshot('chat-room.png', { fullPage: true });

    // 4. Chat empty state (no room selected) — navigate to /chat fresh
    await page.goto('/chat');
    await page.waitForSelector('.chat-page, .room-list-panel', { timeout: 10_000 });
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot('chat-empty.png', { fullPage: true });

    // 5. Settings page
    const settings = new SettingsPage(page);
    await settings.goto();
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot('settings.png', { fullPage: true });

    // 6. Admin page
    const admin = new AdminPage(page);
    await admin.goto();
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot('admin.png', { fullPage: true });
  });
});
