const { test, expect } = require('@playwright/test');
const { fastLogin, twoBrowsers } = require('../fixtures/helpers');
const { ChatPage } = require('../fixtures/chat');

test('twoBrowsers then fastLogin', async ({ browser, page, context }) => {
  const { pageA, pageB, ctxA, ctxB } = await twoBrowsers(browser, 'userA', 'userC');
  const chatA = new ChatPage(pageA);
  await chatA.switchRoom('ui-test-room');
  await pageA.locator('.message-input').fill('typing...');
  await ctxA.close();
  await ctxB.close();

  page.on('response', response => {
    const url = response.url();
    if (url.includes('/rooms') || url.includes('config.js')) {
      console.log(`RESPONSE: ${response.status()} ${url}`);
    }
  });
  page.on('requestfailed', request => {
    console.log(`FAILED: ${request.url()} ${request.failure().errorText}`);
  });

  await fastLogin(context, page, 'userA');
  const roomItems = page.locator('.room-item, .room-item-available');
  const count = await roomItems.count();
  console.log('Room items found:', count);
});
