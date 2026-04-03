// Tests 43-44: Presence in PM
const { test, expect } = require('@playwright/test');
const { twoBrowsers } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { AuthPage } = require('../fixtures/auth');
const { USER_A, USER_B } = require('../fixtures/test-data');

test.describe('Presence - PM', () => {
  test('Test 43: PM refresh preserves state', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await pageA.goto('/chat');
    await pageA.waitForSelector('.chat-layout', { timeout: 10_000 });
    await pageB.goto('/chat');
    await pageB.waitForSelector('.chat-layout', { timeout: 10_000 });

    // A opens PM with B
    await chatA.startPM(USER_B.username);
    await pageA.waitForTimeout(1_000);

    // B opens PM with A
    await chatB.startPM(USER_A.username);
    await pageB.waitForTimeout(1_000);

    // Send a message to establish the PM channel
    const msg = `pm_presence_${Date.now()}`;
    await chatA.sendMessage(msg);
    await pageA.waitForTimeout(500);

    // Check B can see A's status (online)
    const offlineBannerBefore = await chatB.getPMOfflineBanner();
    const isOfflineBefore = await offlineBannerBefore.isVisible().catch(() => false);
    expect(isOfflineBefore).toBe(false);

    // A refreshes
    await pageA.reload({ waitUntil: 'networkidle' });
    await pageA.waitForSelector('.chat-layout', { timeout: 10_000 });
    await chatA.startPM(USER_B.username);
    await pageB.waitForTimeout(2_000);

    // B should still see A as online (no offline banner)
    const offlineBannerAfter = await chatB.getPMOfflineBanner();
    const isOfflineAfter = await offlineBannerAfter.isVisible().catch(() => false);
    expect(isOfflineAfter).toBe(false);

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 44: PM logout shows offline', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await pageA.goto('/chat');
    await pageA.waitForSelector('.chat-layout', { timeout: 10_000 });
    await pageB.goto('/chat');
    await pageB.waitForSelector('.chat-layout', { timeout: 10_000 });

    // A opens PM with B
    await chatA.startPM(USER_B.username);
    await pageA.waitForTimeout(1_000);

    // B opens PM with A
    await chatB.startPM(USER_A.username);
    await pageB.waitForTimeout(1_000);

    // Establish PM by sending a message
    const msg = `pm_logout_${Date.now()}`;
    await chatA.sendMessage(msg);
    await pageA.waitForTimeout(500);

    // Verify A is online from B's perspective
    const offlineBefore = await chatB.getPMOfflineBanner();
    const isOfflineBefore = await offlineBefore.isVisible().catch(() => false);
    expect(isOfflineBefore).toBe(false);

    // A logs out
    const authA = new AuthPage(pageA);
    await authA.logout();
    await pageA.waitForURL('**/login', { timeout: 10_000 });

    // B should see offline status
    await pageB.waitForTimeout(3_000);

    const offlineAfter = await chatB.getPMOfflineBanner();
    const isOfflineAfter = await offlineAfter.isVisible().catch(() => false);
    expect(isOfflineAfter).toBe(true);

    await ctxA.close();
    await ctxB.close();
  });
});
