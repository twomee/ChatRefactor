// Tests 29-34: Admin panel features
const { test, expect } = require('@playwright/test');
const { fastLogin, twoBrowsers, refreshAndWait } = require('../fixtures/helpers');
const { AdminPage } = require('../fixtures/admin');
const { ChatPage } = require('../fixtures/chat');
const { loadTokens } = require('../fixtures/helpers');
const { TEST_ROOM, USER_B } = require('../fixtures/test-data');

test.describe('Admin', () => {
  test('Test 29: close and open room', async ({ page, context }) => {
    await fastLogin(context, page, 'admin');
    const admin = new AdminPage(page);
    await admin.goto();

    // Wait for the rooms table to render
    await page.locator(`tr:has-text("${TEST_ROOM}")`).first().waitFor({ timeout: 10_000 });

    await admin.closeRoom(TEST_ROOM);
    await page.waitForTimeout(1_000);

    let status = await admin.getRoomStatus(TEST_ROOM);
    expect(status.toLowerCase()).toMatch(/closed/i);

    // Reload admin page (don't use refreshAndWait since /admin may 404 via Kong)
    await admin.goto();
    await page.locator(`tr:has-text("${TEST_ROOM}")`).first().waitFor({ timeout: 10_000 });
    status = await admin.getRoomStatus(TEST_ROOM);
    expect(status.toLowerCase()).toMatch(/closed/i);

    // Always reopen the room (critical for subsequent tests)
    await admin.openRoom(TEST_ROOM);
    await page.waitForTimeout(1_000);

    status = await admin.getRoomStatus(TEST_ROOM);
    expect(status.toLowerCase()).toMatch(/open/i);
  });

  test('Test 30: mute and kick user', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'admin', 'userB');
    const chatAdmin = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatAdmin.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    // Wait for both users to appear in each other's user lists
    await pageA.locator(`.user-item:has-text("${USER_B.username}")`).waitFor({ timeout: 10_000 });
    // Wait for admin status to propagate (the ⋮ button appears when admin)
    await pageA.locator(`.user-item:has-text("${USER_B.username}") .user-item-menu-btn`)
      .waitFor({ timeout: 15_000 });

    // Admin mutes B
    await chatAdmin.muteUser(USER_B.username);
    await pageB.waitForTimeout(3_000);

    // B sees muted banner
    const mutedBanner = await chatB.getMutedBanner();
    await expect(mutedBanner).toBeVisible({ timeout: 8_000 });

    // Admin kicks B
    await chatAdmin.kickUser(USER_B.username);
    await pageB.waitForTimeout(1_000);

    // B sees a toast about being kicked
    const toast = await chatB.getToast();
    await expect(toast).toBeVisible({ timeout: 8_000 });
    const toastText = await toast.textContent();
    expect(toastText.toLowerCase()).toMatch(/kicked|removed|kick/i);

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 31: promote user to room admin', async ({ browser }) => {
    // Use a fresh throwaway user so promotion doesn't pollute userB across runs.
    // There is no demote API endpoint, so we can't clean up after promoting a shared user.
    const tokens = loadTokens();
    const promoteUsername = tokens.promoteTarget.user.username;

    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'admin', 'promoteTarget');
    const chatAdmin = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatAdmin.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    // Wait for WebSocket to propagate user list and admin status
    await pageA.waitForTimeout(2_000);

    // Admin promotes the throwaway user
    await chatAdmin.promoteUser(promoteUsername);
    await pageB.waitForTimeout(1_000);

    // Promoted user should see Admin badge in user list
    const adminBadge = pageB.locator(`.user-item:has-text("${promoteUsername}") .user-item-role`).first();
    await expect(adminBadge).toBeVisible({ timeout: 8_000 });

    // Refresh and verify badge persists
    await pageB.reload({ waitUntil: 'networkidle' });
    await pageB.waitForSelector('.chat-layout', { timeout: 10_000 });
    await chatB.switchRoom(TEST_ROOM);
    await pageB.waitForTimeout(1_000);
    const adminBadgeAfter = pageB.locator(`.user-item:has-text("${promoteUsername}") .user-item-role`).first();
    await expect(adminBadgeAfter).toBeVisible({ timeout: 8_000 });

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 32: create room', async ({ page, context }) => {
    await fastLogin(context, page, 'admin');
    const admin = new AdminPage(page);
    await admin.goto();

    const newRoom = `new_room_${Date.now()}`;
    await admin.createRoom(newRoom);
    await page.waitForTimeout(1_000);

    // Room should appear in list
    const roomRow = page.locator(`tr:has-text("${newRoom}")`);
    await expect(roomRow.first()).toBeVisible({ timeout: 8_000 });
  });

  test('Test 33: reset database cancel', async ({ page, context }) => {
    await fastLogin(context, page, 'admin');
    const admin = new AdminPage(page);
    await admin.goto();

    // Dismiss the dialog — no data should be lost
    await admin.clickResetDatabase();
    await page.waitForTimeout(500);

    // Page should still be functional (admin page visible)
    await expect(page.locator('.admin-page')).toBeVisible();

    // TEST_ROOM should still exist
    const roomRow = page.locator(`tr:has-text("${TEST_ROOM}")`);
    await expect(roomRow.first()).toBeVisible({ timeout: 5_000 });
  });

  test('Test 34: files table', async ({ page, context }) => {
    await fastLogin(context, page, 'admin');
    const admin = new AdminPage(page);
    await admin.goto();

    // Wait for rooms table before expanding (admin page loads rooms async)
    await page.locator(`tr:has-text("${TEST_ROOM}")`).first().waitFor({ timeout: 10_000 });

    await admin.expandFiles(TEST_ROOM);

    // Files table or empty-state message must become visible after expanding
    const filesSection = page.locator('.admin-files-table, .admin-no-files').first();
    await expect(filesSection).toBeVisible({ timeout: 15_000 });
  });
});
