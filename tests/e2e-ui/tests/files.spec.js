// Tests 21-23: File uploads
const { test, expect } = require('@playwright/test');
const path = require('path');
const { fastLogin, twoBrowsers, refreshAndWait } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { TEST_ROOM, USER_B } = require('../fixtures/test-data');

const TEST_FILE_PATH = path.join(__dirname, '..', 'fixtures', 'test-file.txt');
const TEST_IMAGE_PATH = path.join(__dirname, '..', 'fixtures', 'test-image.png');

test.describe('Files', () => {
  test('Test 21: upload file and download', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    await chat.uploadFile(TEST_FILE_PATH);
    await page.waitForTimeout(2_000);

    const fileMsg = await chat.getFileMessage('test-file.txt');
    await expect(fileMsg.first()).toBeVisible({ timeout: 10_000 });

    await refreshAndWait(page);
    const fileMsgAfter = await chat.getFileMessage('test-file.txt');
    await expect(fileMsgAfter.first()).toBeVisible();
  });

  test('Test 22: upload image inline preview', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    await chat.uploadFile(TEST_IMAGE_PATH);
    await page.waitForTimeout(2_000);

    // Image should render with an <img> tag inside a message
    const imgEl = page.locator('.msg img').last();
    await expect(imgEl).toBeVisible({ timeout: 10_000 });

    await refreshAndWait(page);
    const imgAfter = page.locator('.msg img').last();
    await expect(imgAfter).toBeVisible();
  });

  test('Test 23: upload file in PM', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    // A opens PM with B
    await pageA.goto('/chat');
    await pageA.waitForSelector('.chat-page, .room-list-panel', { timeout: 10_000 });
    await pageB.goto('/chat');
    await pageB.waitForSelector('.chat-page, .room-list-panel', { timeout: 10_000 });

    await chatA.startPM(USER_B.username);
    await pageA.waitForTimeout(1_000);

    // A uploads file in PM
    await chatA.uploadFile(TEST_FILE_PATH);
    await pageA.waitForTimeout(2_000);

    // B opens PM with A — navigate to the PM
    await chatB.startPM('alice_ui');
    await pageB.waitForTimeout(1_000);

    // B should see the file message
    const fileMsgB = await chatB.getFileMessage('test-file.txt');
    await expect(fileMsgB.first()).toBeVisible({ timeout: 10_000 });

    await ctxA.close();
    await ctxB.close();
  });
});
