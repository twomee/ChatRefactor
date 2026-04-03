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

    await pageA.goto('/chat');
    await pageA.waitForSelector('.chat-layout', { timeout: 10_000 });
    await pageB.goto('/chat');
    await pageB.waitForSelector('.chat-layout', { timeout: 10_000 });

    // A opens PM with B
    await chatA.startPM(USER_B.username);
    await pageA.waitForTimeout(1_000);

    // B opens PM with A
    await chatB.startPM(USER_A.username);
    await pageB.waitForTimeout(1_000);

    // Send an initial message to establish the PM
    await chatA.sendMessage(`pm_typing_init_${Date.now()}`);
    await pageA.waitForTimeout(500);

    // A starts typing
    await pageA.locator('.message-input').fill('I am typing...');

    // B should see typing indicator
    const typingIndicator = await chatB.getTypingIndicator();
    await expect(typingIndicator).toBeVisible({ timeout: 8_000 });

    const indicatorText = await typingIndicator.textContent();
    expect(indicatorText).toBeTruthy();
    expect(indicatorText.length).toBeGreaterThan(0);

    // A stops typing (clears input)
    await pageA.locator('.message-input').fill('');
    await pageA.waitForTimeout(3_000);

    // Typing indicator should disappear
    const isStillVisible = await typingIndicator.isVisible().catch(() => false);
    expect(isStillVisible).toBe(false);

    await ctxA.close();
    await ctxB.close();
  });
});
