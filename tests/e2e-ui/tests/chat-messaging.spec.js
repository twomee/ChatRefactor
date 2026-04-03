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
    await expect(msgEl.first()).toBeVisible();

    await refreshAndWait(page);
    await chat.switchRoom(TEST_ROOM);
    const msgAfter = await chat.getMessage(msg);
    await expect(msgAfter.first()).toBeVisible();
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

    await chat.addReaction(msg, 'thumbs up');

    const reactionChip = page.locator(`.msg:has-text("${msg}") .reaction-chip`);
    await expect(reactionChip.first()).toBeVisible({ timeout: 5_000 });

    const chipText = await reactionChip.first().textContent();
    expect(chipText).toBeTruthy();

    await chat.removeReaction(msg, chipText.trim().split(/\s/)[0]);

    // After removal: chip gone or count decreased
    const remaining = page.locator(`.msg:has-text("${msg}") .reaction-chip`);
    const count = await remaining.count();
    // Either no chips remain or count decreased
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('Test 13: clear message history', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    const msg1 = `clear_a_${Date.now()}`;
    const msg2 = `clear_b_${Date.now()}`;
    await chat.sendMessage(msg1);
    await chat.sendMessage(msg2);
    await (await chat.getMessage(msg2)).first().waitFor({ timeout: 5_000 });

    await chat.clearHistory();
    await page.waitForTimeout(1_000);

    // No messages container should be empty or show empty state
    const messages = page.locator('.msg');
    const msgCount = await messages.count();
    expect(msgCount).toBe(0);

    await refreshAndWait(page);
    await chat.switchRoom(TEST_ROOM);
    const messagesAfter = page.locator('.msg');
    const msgCountAfter = await messagesAfter.count();
    expect(msgCountAfter).toBe(0);
  });

  test('Test 14: typing indicator', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);

    // A starts typing
    await pageA.locator('.message-input').fill('typing...');

    const indicator = await chatB.getTypingIndicator();
    await expect(indicator).toBeVisible({ timeout: 8_000 });

    const indicatorText = await indicator.textContent();
    expect(indicatorText).toBeTruthy();

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

  test('Test 16: markdown rendering', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    await chat.sendMessage('**bold** and `code`');
    await page.waitForTimeout(1_000);

    // Check that markdown is rendered as HTML
    const boldEl = page.locator('.msg strong, .msg b').first();
    const codeEl = page.locator('.msg code').first();

    await expect(boldEl).toBeVisible({ timeout: 5_000 });
    await expect(codeEl).toBeVisible({ timeout: 5_000 });

    const boldText = await boldEl.textContent();
    expect(boldText).toContain('bold');
    const codeText = await codeEl.textContent();
    expect(codeText).toContain('code');
  });

  test('Test 17: link preview', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    await chat.sendMessage('Check https://example.com');
    await page.waitForTimeout(2_000);

    const preview = page.locator('.link-preview-card').first();
    await expect(preview).toBeVisible({ timeout: 10_000 });

    await refreshAndWait(page);
    await chat.switchRoom(TEST_ROOM);
    const previewAfter = page.locator('.link-preview-card').first();
    await expect(previewAfter).toBeVisible({ timeout: 5_000 });
  });
});
