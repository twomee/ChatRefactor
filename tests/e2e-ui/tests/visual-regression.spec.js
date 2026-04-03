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
    test.setTimeout(180_000);
    // 1. Login page — Sign In tab
    const auth = new AuthPage(page);
    await auth.goto();
    await expect(page).toHaveScreenshot('login-signin.png', { fullPage: true, maxDiffPixelRatio: 0.05 });

    // 2. Login page — Register tab
    await auth.switchToRegister();
    await page.waitForTimeout(300);
    await expect(page).toHaveScreenshot('login-register.png', { fullPage: true, maxDiffPixelRatio: 0.05 });

    // 3. Chat with a room selected
    await fastLogin(context, page, 'userA');
    await page.waitForSelector('.chat-layout', { timeout: 15_000 });
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);
    await page.waitForTimeout(1_000);
    await expect(page).toHaveScreenshot('chat-room.png', { fullPage: true, maxDiffPixelRatio: 0.05 });

    // 4. Chat empty state (no room selected) — navigate to /chat fresh
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.chat-layout', { timeout: 15_000 });
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot('chat-empty.png', { fullPage: true, maxDiffPixelRatio: 0.05 });

    // 5. Settings page
    const settings = new SettingsPage(page);
    await settings.goto();
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot('settings.png', { fullPage: true, maxDiffPixelRatio: 0.05 });

    // 6. Admin page — requires admin credentials (userA is not admin)
    await fastLogin(context, page, 'admin');
    await page.waitForSelector('.chat-layout', { timeout: 15_000 });
    const admin = new AdminPage(page);
    await admin.goto();
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot('admin.png', { fullPage: true, maxDiffPixelRatio: 0.05 });
  });
});
