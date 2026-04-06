// Test 46: PM typing indicator
const { test, expect } = require('@playwright/test');
const { twoBrowsers } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');
const { USER_A, USER_B } = require('../fixtures/test-data');

test.describe('PM Typing', () => {
  test('Test 46: PM typing indicator', async ({ browser }) => {
    const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userB');
    const chatA = new ChatPage(pageA);
    const chatB = new ChatPage(pageB);

    // Both join room so they can see each other
    await chatA.switchRoom('ui-test-room');
    await chatB.switchRoom('ui-test-room');
    await pageA.waitForTimeout(1_000);

    // A opens PM with B
    await chatA.startPM(USER_B.username);
    await pageA.waitForTimeout(1_000);

    // B opens PM with A
    await chatB.startPM(USER_A.username);
    await pageB.waitForTimeout(1_000);

    // Send an initial message to establish the PM
    await chatA.sendMessage(`pm_typing_init_${Date.now()}`);
    await pageA.waitForTimeout(500);

    // A starts typing — use type() to trigger onChange events
    await pageA.locator('.message-input').click();
    await pageA.locator('.message-input').type('I am typing...', { delay: 50 });

    // B should see typing indicator (the div always exists but is empty when no one types)
    const typingIndicator = await chatB.getTypingIndicator();
    await expect(typingIndicator).toHaveText(/is typing/, { timeout: 8_000 });

    // A stops typing (clear input using triple-click + backspace to trigger onChange)
    await pageA.locator('.message-input').fill('');

    // Typing indicator should clear within the server's typing-expiry window (~3s).
    // Use toHaveText with a negation retry instead of a fixed sleep so slow CI
    // environments still pass and fast ones don't waste time.
    await expect(typingIndicator).not.toHaveText(/is typing/, { timeout: 8_000 });

    await ctxA.close();
    await ctxB.close();
  });
});
