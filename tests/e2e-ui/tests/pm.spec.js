// Tests 24-28: Private messaging
const { test, expect } = require('@playwright/test');
const { twoBrowsers, fastLogin, refreshAndWait, loadTokens } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { TEST_ROOM, USER_A, USER_B } = require('../fixtures/test-data');

test.describe('PM', () => {
  test('Test 24: PM send and receive', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    // Both join the test room so they appear in each other's user list
    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);

    // Wait for user B to appear in A's user list before starting PM
    await pageA.locator(`.user-item:has-text("${USER_B.username}")`).waitFor({ timeout: 10_000 });

    // A starts PM with B (via user-item click)
    await chatA.startPM(USER_B.username, { viaUserList: true });
    await pageA.waitForTimeout(500);

    const msgA = `pm_hello_${Date.now()}`;
    await chatA.sendMessage(msgA);

    // Verify A sees their own sent message
    const sentEl = await chatA.getMessage(msgA);
    await expect(sentEl.first()).toBeVisible({ timeout: 8_000 });

    // B waits for PM notification from A (pm-item appears in sidebar when message arrives via WS)
    await pageB.locator(`.pm-item:has-text("${USER_A.username}")`).waitFor({ timeout: 15_000 });
    // Open PM via user-list click to avoid history-fetch overwriting the WS-delivered message.
    // The backend history endpoint applies clear/limit AFTER fetching, so with many old
    // messages the newest can be outside the 50-message window.
    await chatB.startPM(USER_A.username, { viaUserList: true });

    // B should see A's message (delivered via WebSocket, already in thread state)
    const msgElB = await chatB.getMessage(msgA);
    await expect(msgElB.first()).toBeVisible({ timeout: 10_000 });

    // B replies
    const msgB = `pm_reply_${Date.now()}`;
    await chatB.sendMessage(msgB);

    // A should see B's reply
    const replyElA = await chatA.getMessage(msgB);
    await expect(replyElA.first()).toBeVisible({ timeout: 10_000 });

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 25: PM edit and delete', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);

    // Both join the test room so they appear in each other's user list
    await chatA.switchRoom(TEST_ROOM);
    await new ChatPage(pageB).switchRoom(TEST_ROOM);

    // Wait for user B to appear in A's user list
    await pageA.locator(`.user-item:has-text("${USER_B.username}")`).waitFor({ timeout: 10_000 });

    // A starts PM with B
    await chatA.startPM(USER_B.username, { viaUserList: true });
    await pageA.waitForTimeout(500);

    // Send and edit
    const editOriginal = `pm_edit_orig_${Date.now()}`;
    const editNew = `pm_edit_new_${Date.now()}`;
    await chatA.sendMessage(editOriginal);
    await (await chatA.getMessage(editOriginal)).first().waitFor({ timeout: 5_000 });

    await chatA.editMessage(editOriginal, editNew);
    await pageA.waitForTimeout(500);
    const editedEl = await chatA.getMessage(editNew);
    await expect(editedEl.first()).toBeVisible({ timeout: 10_000 });

    const editedBadge = pageA.locator(`.msg:has-text("${editNew}") .msg-edited-badge`);
    await expect(editedBadge.first()).toBeVisible({ timeout: 5_000 });

    // Send and delete
    const deleteMsg = `pm_delete_${Date.now()}`;
    await chatA.sendMessage(deleteMsg);
    await (await chatA.getMessage(deleteMsg)).first().waitFor({ timeout: 5_000 });

    await chatA.deleteMessage(deleteMsg);
    const deletedEl = pageA.locator('.msg:has-text("[deleted]")');
    await expect(deletedEl.first()).toBeVisible({ timeout: 5_000 });

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 26: PM reaction', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);

    // Both join the test room so they appear in each other's user list
    await chatA.switchRoom(TEST_ROOM);
    await new ChatPage(pageB).switchRoom(TEST_ROOM);

    // Wait for user B to appear in A's user list
    await pageA.locator(`.user-item:has-text("${USER_B.username}")`).waitFor({ timeout: 10_000 });

    await chatA.startPM(USER_B.username, { viaUserList: true });
    await pageA.waitForTimeout(500);

    const msg = `pm_react_${Date.now()}`;
    await chatA.sendMessage(msg);
    await (await chatA.getMessage(msg)).first().waitFor({ timeout: 5_000 });

    // Scroll message into view before adding reaction (prevents emoji picker from being off-screen)
    const msgEl = pageA.locator(`.msg:has-text("${msg}")`).first();
    await msgEl.scrollIntoViewIfNeeded();
    await chatA.addReaction(msg, '👍');

    const reactionChip = pageA.locator(`.msg:has-text("${msg}") .reaction-chip`);
    await expect(reactionChip.first()).toBeVisible({ timeout: 5_000 });

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 27: delete DM conversation', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);

    // Both join the test room so they appear in each other's user list
    await chatA.switchRoom(TEST_ROOM);
    await new ChatPage(pageB).switchRoom(TEST_ROOM);
    await pageA.waitForTimeout(1_000);

    await chatA.startPM(USER_B.username);
    await pageA.waitForTimeout(1_000);

    const msg = `pm_del_conv_${Date.now()}`;
    await chatA.sendMessage(msg);
    await pageA.waitForTimeout(1_000);

    // Delete the PM conversation
    await chatA.deletePMConversation(USER_B.username);
    await pageA.waitForTimeout(1_000);

    // PM item should be removed from sidebar
    const pmItem = pageA.locator(`.pm-item:has-text("${USER_B.username}")`);
    const isVisible = await pmItem.isVisible().catch(() => false);
    expect(isVisible).toBe(false);

    // Refresh — still removed
    await pageA.reload({ waitUntil: 'networkidle' });
    await pageA.waitForSelector('.chat-layout', { timeout: 10_000 });
    const pmItemAfter = pageA.locator(`.pm-item:has-text("${USER_B.username}")`);
    const isVisibleAfter = await pmItemAfter.isVisible().catch(() => false);
    expect(isVisibleAfter).toBe(false);

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 28: room closed toast', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'admin', 'userB');
    const chatB = new ChatPage(pageB);

    // B joins test room
    await chatB.switchRoom(TEST_ROOM);
    await pageB.waitForTimeout(500);

    // Admin navigates to admin panel via UI dropdown
    await pageA.locator('[data-testid="user-dropdown-trigger"]').click();
    await pageA.locator('[data-testid="dropdown-admin"]').click();
    await pageA.waitForSelector('.admin-page', { timeout: 15_000 });

    const { AdminPage } = require('../fixtures/admin');
    const admin = new AdminPage(pageA);
    await admin.closeRoom(TEST_ROOM);
    await pageA.waitForTimeout(1_000);

    // B should see a toast about room being closed
    const toast = await chatB.getToast();
    await expect(toast).toBeVisible({ timeout: 10_000 });
    const toastText = await toast.textContent();
    expect(toastText.toLowerCase()).toMatch(/closed|room/i);

    // Reopen room for other tests
    await admin.openRoom(TEST_ROOM);

    await ctxA.close();
    await ctxB.close();
  });
});
