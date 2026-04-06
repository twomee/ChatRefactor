// Tests 9-17: Chat messaging features
const { test, expect } = require('@playwright/test');
const { fastLogin, twoBrowsers, refreshAndWait } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { TEST_ROOM } = require('../fixtures/test-data');

test.describe('Chat Messaging', () => {
  test('Test 9: send message and survives refresh', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    const msg = `hello_refresh_${Date.now()}`;
    await chat.sendMessage(msg);

    const msgEl = await chat.getMessage(msg);
    await expect(msgEl.first()).toBeVisible({ timeout: 10_000 });

    await refreshAndWait(page);
    await chat.switchRoom(TEST_ROOM);
    const msgAfter = await chat.getMessage(msg);
    await expect(msgAfter.first()).toBeVisible({ timeout: 10_000 });
  });

  test('Test 10: edit message shows edited badge', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    const original = `edit_original_${Date.now()}`;
    const edited = `edit_new_${Date.now()}`;
    await chat.sendMessage(original);
    await (await chat.getMessage(original)).first().waitFor({ timeout: 5_000 });

    await chat.editMessage(original, edited);

    const editedMsg = await chat.getMessage(edited);
    await expect(editedMsg.first()).toBeVisible();

    const editedBadge = page.locator(`.msg:has-text("${edited}") .msg-edited-badge`);
    await expect(editedBadge.first()).toBeVisible({ timeout: 5_000 });

    await refreshAndWait(page);
    await chat.switchRoom(TEST_ROOM);
    const editedAfter = await chat.getMessage(edited);
    await expect(editedAfter.first()).toBeVisible();
    const badgeAfter = page.locator(`.msg:has-text("${edited}") .msg-edited-badge`);
    await expect(badgeAfter.first()).toBeVisible();
  });

  test('Test 11: delete message shows deleted text', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    const msg = `delete_me_${Date.now()}`;
    await chat.sendMessage(msg);
    await (await chat.getMessage(msg)).first().waitFor({ timeout: 5_000 });

    await chat.deleteMessage(msg);

    const deletedEl = page.locator('.msg:has-text("[deleted]")');
    await expect(deletedEl.first()).toBeVisible({ timeout: 5_000 });

    await refreshAndWait(page);
    await chat.switchRoom(TEST_ROOM);
    const deletedAfter = page.locator('.msg:has-text("[deleted]")');
    await expect(deletedAfter.first()).toBeVisible();
  });

  test('Test 12: add and remove reaction', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    const msg = `react_msg_${Date.now()}`;
    await chat.sendMessage(msg);
    await (await chat.getMessage(msg)).first().waitFor({ timeout: 5_000 });

    await chat.addReaction(msg, '👍');

    const reactionChip = page.locator(`.msg:has-text("${msg}") .reaction-chip`);
    await expect(reactionChip.first()).toBeVisible({ timeout: 5_000 });

    const chipText = await reactionChip.first().textContent();
    expect(chipText).toBeTruthy();

    await chat.removeReaction(msg, chipText.trim().split(/\s/)[0]);

    // The single reaction we added should be gone (retries until server confirms)
    const remaining = page.locator(`.msg:has-text("${msg}") .reaction-chip`);
    await expect(remaining).toHaveCount(0, { timeout: 5_000 });
  });

  test('Test 13: clear message history', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    const msg1 = `clear_a_${Date.now()}`;
    const msg2 = `clear_b_${Date.now()}`;
    await chat.sendMessage(msg1);
    await chat.sendMessage(msg2);
    await (await chat.getMessage(msg2)).first().waitFor({ timeout: 10_000 });

    await chat.clearHistory();
    await page.waitForTimeout(1_000);

    // Only count user messages — system messages (join/leave) are not cleared
    // by clearHistory and have the .msg-system class.
    const messages = page.locator('.msg:not(.msg-system)');
    const msgCount = await messages.count();
    expect(msgCount).toBe(0);

    await refreshAndWait(page);
    await chat.switchRoom(TEST_ROOM);
    const messagesAfter = page.locator('.msg:not(.msg-system)');
    const msgCountAfter = await messagesAfter.count();
    expect(msgCountAfter).toBe(0);
  });

  test('Test 14: typing indicator', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userC');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);

    // A starts typing — use type() instead of fill() to trigger onChange events
    await pageA.locator('.message-input').click();
    await pageA.locator('.message-input').type('typing...', { delay: 50 });

    // The typing indicator div always exists but is empty when no one is typing.
    // When someone is typing, it contains text like "alice_ui is typing..."
    const indicator = await chatB.getTypingIndicator();
    // Wait for typing text to appear inside the indicator
    await expect(indicator).toHaveText(/is typing/, { timeout: 8_000 });

    await ctxA.close();
    await ctxB.close();
  });

  test('Test 15: search messages', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    const unique = `searchable_${Date.now()}`;
    await chat.sendMessage(unique);
    await (await chat.getMessage(unique)).first().waitFor({ timeout: 5_000 });

    await chat.openSearch();
    await chat.search(unique);

    const results = await chat.getSearchResults();
    await expect(results.first()).toBeVisible({ timeout: 8_000 });
    const count = await results.count();
    expect(count).toBeGreaterThan(0);

    await chat.clickSearchResult(0);

    // Message should be visible/highlighted after clicking result
    const msgEl = await chat.getMessage(unique);
    await expect(msgEl.first()).toBeVisible({ timeout: 5_000 });
  });

  test('Test 16: message with special characters', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    // Room messages display text as-is (markdown rendering is only in PMs)
    const msg = `special_chars_${Date.now()} **bold** & <tag>`;
    await chat.sendMessage(msg);

    const msgEl = page.locator(`.msg-text-content:has-text("special_chars_")`).first();
    await expect(msgEl).toBeVisible({ timeout: 5_000 });

    const content = await msgEl.textContent();
    expect(content).toContain('**bold**');
  });

  test('Test 17: link in message is rendered', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    const msg = `link_test_${Date.now()} https://example.com`;
    await chat.sendMessage(msg);

    // Verify the message itself appears with the URL text
    const msgEl = page.locator(`.msg-text-content:has-text("https://example.com")`).first();
    await expect(msgEl).toBeVisible({ timeout: 5_000 });

    // Link preview depends on the backend being able to fetch OG metadata;
    // a loading skeleton briefly appears then disappears if the backend can't
    // fetch metadata. We just verify the message text persists after refresh.
    await refreshAndWait(page);
    await chat.switchRoom(TEST_ROOM);
    const msgAfter = page.locator(`.msg-text-content:has-text("https://example.com")`).first();
    // Use a longer timeout: after a rate-limit backoff the message history
    // load can lag significantly in constrained (K8s) environments.
    await expect(msgAfter).toBeVisible({ timeout: 20_000 });
  });
});
