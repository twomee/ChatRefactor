// Tests 21-23: File uploads
const { test, expect } = require('@playwright/test');
const path = require('path');
const { fastLogin, twoBrowsers, refreshAndWait } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { TEST_ROOM, USER_A, USER_B } = require('../fixtures/test-data');

const TEST_FILE_PATH = path.join(__dirname, '..', 'fixtures', 'test-file.txt');
const TEST_IMAGE_PATH = path.join(__dirname, '..', 'fixtures', 'test-image.png');

test.describe('Files', () => {
  test('Test 21: upload file and download', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    await chat.uploadFile(TEST_FILE_PATH);

    // Wait for the file message to appear (no fixed sleep)
    const fileMsg = await chat.getFileMessage('test-file.txt');
    await expect(fileMsg.first()).toBeVisible({ timeout: 10_000 });

    // Download link must be present in the file message
    const downloadLink = fileMsg.first().locator('.msg-file-link');
    await expect(downloadLink).toBeVisible({ timeout: 5_000 });

    // Trigger download and assert the file is delivered
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 10_000 }),
      downloadLink.click(),
    ]);
    expect(download.suggestedFilename()).toContain('test-file');

    // Verify persistence across refresh
    await refreshAndWait(page);
    await chat.switchRoom(TEST_ROOM);
    const fileMsgAfter = await chat.getFileMessage('test-file.txt');
    await expect(fileMsgAfter.first()).toBeVisible();
  });

  test('Test 22: upload image inline preview', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    const chat = new ChatPage(page);
    await chat.switchRoom(TEST_ROOM);

    await chat.uploadFile(TEST_IMAGE_PATH);

    // Image should render with an <img> tag inside a message
    const imgEl = page.locator('.msg img').last();
    // Scroll into view to trigger lazy-loading, then check visibility
    await imgEl.scrollIntoViewIfNeeded().catch(() => {});
    await expect(imgEl).toBeVisible({ timeout: 10_000 });

    await refreshAndWait(page);
    await chat.switchRoom(TEST_ROOM);
    const imgAfter = page.locator('.msg img').last();
    await imgAfter.scrollIntoViewIfNeeded().catch(() => {});
    await expect(imgAfter).toBeVisible();
  });

  test('Test 23: upload file in PM', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    // Both join room so they can see each other in user list
    await chatA.switchRoom(TEST_ROOM);
    await chatB.switchRoom(TEST_ROOM);
    // 3s: presence WebSocket events can lag in rate-limited (K8s) environments
    await pageA.waitForTimeout(3_000);

    // A opens PM with B
    await chatA.startPM(USER_B.username);
    await pageA.waitForTimeout(1_000);

    // A uploads file in PM
    await chatA.uploadFile(TEST_FILE_PATH);
    // Wait for the upload to appear in A's PM before checking B's view
    const fileMsgA = await chatA.getFileMessage('test-file.txt');
    await expect(fileMsgA.first()).toBeVisible({ timeout: 10_000 });

    // B opens PM with A via user-list click (avoids history fetch that could miss the file)
    await pageB.locator(`.pm-item:has-text("${USER_A.username}")`).waitFor({ timeout: 10_000 });
    await chatB.startPM(USER_A.username, { viaUserList: true });
    await pageB.waitForTimeout(1_000);

    // B should see the file message
    const fileMsgB = await chatB.getFileMessage('test-file.txt');
    await expect(fileMsgB.first()).toBeVisible({ timeout: 10_000 });

    await ctxA.close();
    await ctxB.close();
  });
});
