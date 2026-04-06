// Tests 43-44: Presence in PM
const { test, expect } = require('@playwright/test');
const { twoBrowsers, refreshAndWait } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { AuthPage } = require('../fixtures/auth');
const { USER_A, USER_B } = require('../fixtures/test-data');

test.describe('Presence - PM', () => {
  test('Test 43: PM refresh preserves state', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    // Both join room so they can see each other in user list
    await chatA.switchRoom('ui-test-room');
    await chatB.switchRoom('ui-test-room');
    // 3s: presence WebSocket events can lag in rate-limited (K8s) environments
    await pageA.waitForTimeout(3_000);

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

    // A refreshes — use refreshAndWait so a rate-limit response triggers a backoff + retry
    await refreshAndWait(pageA);
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
    // Use logoutPM — a throwaway user whose token can be blacklisted safely
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'logoutPM', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    // Both join room so they can see each other in user list
    await chatA.switchRoom('ui-test-room');
    await chatB.switchRoom('ui-test-room');
    // 3s: presence WebSocket events can lag in rate-limited (K8s) environments
    await pageA.waitForTimeout(3_000);

    // A opens PM with B
    await chatA.startPM(USER_B.username);
    await pageA.waitForTimeout(1_000);

    // B opens PM with A (logoutPM user)
    const { loadTokens } = require('../fixtures/helpers');
    const tokens = loadTokens();
    const logoutPMUsername = tokens.logoutPM.user.username;
    await chatB.startPM(logoutPMUsername);
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

    // B should see offline banner — wait for it to appear via WebSocket rather than
    // sleeping a fixed amount, which is fragile in slow (K8s) environments.
    const offlineAfter = await chatB.getPMOfflineBanner();
    await expect(offlineAfter).toBeVisible({ timeout: 8_000 });

    await ctxA.close();
    await ctxB.close();
  });
});
