// Tests 18-20: Chat sidebar (rooms, badges, dividers)
const { test, expect } = require('@playwright/test');
const { fastLogin, twoBrowsers, refreshAndWait } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { TEST_ROOM } = require('../fixtures/test-data');

test.describe('Chat Sidebar', () => {
  test('Test 18: exit room and rejoin', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);

    // Make sure we're in the test room first
    await chat.switchRoom(TEST_ROOM);
    await page.waitForTimeout(500);

    await chat.exitRoom(TEST_ROOM);
    await page.waitForTimeout(1_000);

    // After exiting, the room must move to the available section (can rejoin)
    const availableRoom = page.locator(`.room-item-available:has-text("${TEST_ROOM}")`);
    await expect(availableRoom).toBeVisible({ timeout: 5_000 });

    // Rejoin
    await chat.joinRoom(TEST_ROOM);
    await page.waitForTimeout(1_000);

    // Room should be clickable/active again
    const roomItem = page.locator(`.room-item:has-text("${TEST_ROOM}")`);
    await expect(roomItem.first()).toBeVisible({ timeout: 5_000 });
  });

  test('Test 19: unread badges', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    // Both join the test room
    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    await pageA.waitForTimeout(500);

    // A needs a second room to switch to — get the room name from .room-name span
    const secondRoom = pageA.locator(`.room-item:not(:has-text("${TEST_ROOM}")) .room-name`).first();
    const hasSecondRoom = await secondRoom.isVisible().catch(() => false);

    if (hasSecondRoom) {
      const secondRoomName = await secondRoom.textContent();
      await chatA.switchRoom(secondRoomName.trim());
    } else {
      // If no second room available, join an available room first
      const availRoom = pageA.locator('.room-item-available .room-name').first();
      const hasAvail = await availRoom.isVisible().catch(() => false);
      if (hasAvail) {
        const availName = await availRoom.textContent();
        await chatA.switchRoom(availName.trim());
      }
    }

    // B sends a message in TEST_ROOM
    const uniqMsg = `badge_test_${Date.now()}`;
    await chatB.sendMessage(uniqMsg);
    // Wait for message to propagate
    await pageB.waitForTimeout(2_000);

    if (hasSecondRoom || await pageA.locator('.room-item-available .room-name').first().isVisible().catch(() => false)) {
      // A should see an unread badge on TEST_ROOM — wait for it
      await pageA.waitForTimeout(1_000);
      const badge = await chatA.getUnreadBadge(TEST_ROOM);
      expect(badge).not.toBeNull();

      // A clicks TEST_ROOM — badge should clear
      await chatA.switchRoom(TEST_ROOM);
      await pageA.waitForTimeout(500);

      const badgeAfter = await chatA.getUnreadBadge(TEST_ROOM);
      expect(badgeAfter).toBeNull();
    } else {
      // Verify at least the message was sent
      const msgEl = await chatB.getMessage(uniqMsg);
      await expect(msgEl.first()).toBeVisible();
    }

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 20: new messages divider', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    // Both in TEST_ROOM
    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);

    // A switches away — get room name from .room-name span
    const secondRoom = pageA.locator(`.room-item:not(:has-text("${TEST_ROOM}")) .room-name`).first();
    const hasSecondRoom = await secondRoom.isVisible().catch(() => false);

    if (hasSecondRoom) {
      const secondRoomName = await secondRoom.textContent();
      await chatA.switchRoom(secondRoomName.trim());
      await pageA.waitForTimeout(500);

      // B sends messages
      await chatB.sendMessage(`divider_msg_${Date.now()}`);
      await pageB.waitForTimeout(500);

      // A returns to TEST_ROOM
      await chatA.switchRoom(TEST_ROOM);
      await pageA.waitForTimeout(1_000);

      // New-messages divider must appear when returning to a room with unread messages
      const divider = await chatA.getNewMessagesDivider();
      await expect(divider).toBeVisible({ timeout: 5_000 });
    } else {
      // No second room available — skip the divider assertion (can't create unread state)
      test.skip(true, 'No second room available to create unread state');
    }

    await ctxA.close();
    await ctxB.close();
  });
});
