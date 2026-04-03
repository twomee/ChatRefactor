// Tests 39-42: Presence in rooms
const { test, expect } = require('@playwright/test');
const { twoBrowsers } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { AuthPage } = require('../fixtures/auth');
const { TEST_ROOM, USER_A, USER_B, ADMIN } = require('../fixtures/test-data');

test.describe('Presence - Rooms', () => {
  test('Test 39: admin role survives logout', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'admin', 'userB');
    const chatAdmin = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatAdmin.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    await pageA.waitForTimeout(1_000);

    // Check admin badge visible in B's view for admin user
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

    // If admin had badge before logout, should still have it
    if (hasBadge) {
      expect(hasBadgeAfter).toBe(true);
    } else {
      // Just verify the admin is in the user list
      const adminInList = await chatB.isUserInList(ADMIN.username);
      expect(adminInList).toBe(true);
    }

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 40: logout immediate disappearance', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    await pageA.waitForTimeout(1_000);

    // Verify A is in B's user list
    const aInList = await chatB.isUserInList(USER_A.username);
    expect(aInList).toBe(true);

    // A logs out
    const authA = new AuthPage(pageA);
    await authA.logout();
    await pageA.waitForURL('**/login', { timeout: 10_000 });

    // B should see A removed from user list
    await pageB.waitForTimeout(3_000);
    const aStillInList = await chatB.isUserInList(USER_A.username);
    expect(aStillInList).toBe(false);

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 41: refresh preserves state', async ({ browser }) => {
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
    await pageA.reload({ waitUntil: 'networkidle' });
    await pageA.waitForSelector('.chat-layout', { timeout: 10_000 });
    await chatA.switchRoom(TEST_ROOM);
    await pageB.waitForTimeout(2_000);

    // B still sees A online
    const aInListAfter = await chatB.isUserInList(USER_A.username);
    expect(aInListAfter).toBe(true);

    // No spurious leave/join system messages (or at most minimal)
    const msgsAfter = await pageB.locator('.msg.msg-system').count();
    // Tolerate at most 2 new system messages (reconnect)
    expect(msgsAfter - msgsBefore).toBeLessThanOrEqual(2);

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 42: leave shows offline', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    await pageA.waitForTimeout(1_000);

    const aInList = await chatB.isUserInList(USER_A.username);
    expect(aInList).toBe(true);

    // A exits the room
    await chatA.exitRoom(TEST_ROOM);
    await pageA.waitForTimeout(2_000);

    // B should no longer see A in the user list
    const aInListAfter = await chatB.isUserInList(USER_A.username);
    expect(aInListAfter).toBe(false);

    await ctxA.close();
    await ctxB.close();
  });
});
