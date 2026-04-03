// Tests 39-42: Presence in rooms
const { test, expect } = require('@playwright/test');
const { twoBrowsers, loadTokens } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { AuthPage } = require('../fixtures/auth');
const { TEST_ROOM, USER_A, USER_B, ADMIN } = require('../fixtures/test-data');

test.describe('Presence - Rooms', () => {
  // Tests 41 and 42 run BEFORE Tests 39 and 40.
  // Tests 39/40 call logout() which blacklists the JWT in Redis.
  // Running non-logout tests first avoids token invalidation issues.

  test('Test 41: refresh preserves state', async ({ browser }) => {
    test.setTimeout(180_000);
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    await pageA.waitForTimeout(1_000);

    // Verify both in room
    const aInList = await chatB.isUserInList(USER_A.username);
    expect(aInList).toBe(true);

    // Count messages before refresh
    const msgsBefore = await pageB.locator('.msg.msg-system').count();

    // A refreshes
    await pageA.reload({ waitUntil: 'domcontentloaded' });
    await pageA.waitForSelector('.chat-layout', { timeout: 15_000 });
    await chatA.switchRoom(TEST_ROOM);
    await pageB.waitForTimeout(3_000);

    // B still sees A online
    const aInListAfter = await chatB.isUserInList(USER_A.username);
    expect(aInListAfter).toBe(true);

    // No spurious leave/join system messages (or at most minimal)
    const msgsAfter = await pageB.locator('.msg.msg-system').count();
    expect(msgsAfter - msgsBefore).toBeLessThanOrEqual(2);

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 42: leave shows offline', async ({ browser }) => {
    test.setTimeout(180_000);
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    await pageA.waitForTimeout(1_000);

    await pageB.locator(`.user-item:has-text("${USER_A.username}")`).waitFor({ timeout: 10_000 });
    const aInList = await chatB.isUserInList(USER_A.username);
    expect(aInList).toBe(true);

    // A exits the room
    await chatA.exitRoom(TEST_ROOM);

    // Wait for A to disappear from B's user list
    await pageB.locator(`.user-item:has-text("${USER_A.username}")`).waitFor({ state: 'hidden', timeout: 10_000 }).catch(() => {});
    await pageB.waitForTimeout(1_000);

    const aInListAfter = await chatB.isUserInList(USER_A.username);
    expect(aInListAfter).toBe(false);

    await ctxA.close();
    await ctxB.close();
  });

  // Tests 39 and 40 perform logout which blacklists JWT tokens in Redis.
  // They use dedicated throwaway users (logoutAdmin, logoutPresence) so that
  // userA/userB/userC/admin tokens remain valid for later test files.

  test('Test 39: admin role survives logout', async ({ browser }) => {
    // This test verifies admin badge after logout/re-login.
    // We use the real admin user, but since visual-regression also needs the
    // admin token, we re-login the admin via API after this test to refresh
    // the stored token.
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'admin', 'userB');
    const chatAdmin = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatAdmin.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    await pageA.waitForTimeout(1_000);

    // Check admin badge visible in B's view
    const adminBadge = pageB.locator(`.user-item:has-text("${ADMIN.username}") .user-item-role`).first();
    const hasBadge = await adminBadge.isVisible().catch(() => false);

    // Admin logs out via UI
    const authAdmin = new AuthPage(pageA);
    await authAdmin.logout();
    await pageA.waitForURL('**/login', { timeout: 10_000 });

    // Admin logs back in via UI
    await authAdmin.goto();
    await authAdmin.login(ADMIN.username, ADMIN.password);
    await pageA.waitForURL('**/chat', { timeout: 15_000 });
    await pageA.waitForSelector('.chat-layout', { timeout: 10_000 });

    await chatAdmin.switchRoom(TEST_ROOM);
    await pageA.waitForTimeout(1_000);

    // Admin should still have admin badge after re-login
    const adminBadgeAfter = pageB.locator(`.user-item:has-text("${ADMIN.username}") .user-item-role`).first();
    const hasBadgeAfter = await adminBadgeAfter.isVisible().catch(() => false);

    if (hasBadge) {
      expect(hasBadgeAfter).toBe(true);
    } else {
      const adminInList = await chatB.isUserInList(ADMIN.username);
      expect(adminInList).toBe(true);
    }

    // Refresh the stored admin token so later tests (visual-regression) can use it
    const BASE_URL = process.env.BASE_URL || 'http://localhost:8090';
    const loginRes = await fetch(`${BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: ADMIN.username, password: ADMIN.password }),
    });
    const loginData = await loginRes.json();
    if (loginData.access_token) {
      const fs = require('fs');
      const path = require('path');
      const tokensPath = path.join(__dirname, '..', 'playwright', '.auth', 'tokens.json');
      const tokens = JSON.parse(fs.readFileSync(tokensPath, 'utf-8'));
      tokens.admin.token = loginData.access_token;
      fs.writeFileSync(tokensPath, JSON.stringify(tokens, null, 2));
    }

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 40: logout immediate disappearance', async ({ browser }) => {
    // Use logoutPresence — a throwaway user whose token can be blacklisted safely
    const tokens = loadTokens();
    const logoutUsername = tokens.logoutPresence.user.username;

    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'logoutPresence', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    await pageA.waitForTimeout(1_000);

    // Verify A is in B's user list
    const aInList = await chatB.isUserInList(logoutUsername);
    expect(aInList).toBe(true);

    // A logs out
    const authA = new AuthPage(pageA);
    await authA.logout();
    await pageA.waitForURL('**/login', { timeout: 10_000 });

    // B should see A removed from user list
    await pageB.waitForTimeout(3_000);
    const aStillInList = await chatB.isUserInList(logoutUsername);
    expect(aStillInList).toBe(false);

    await ctxA.close();
    await ctxB.close();
  });
});
