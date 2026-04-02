const fs = require('fs');
const path = require('path');

const TOKENS_PATH = path.join(__dirname, '..', 'playwright', '.auth', 'tokens.json');

function loadTokens() {
  return JSON.parse(fs.readFileSync(TOKENS_PATH, 'utf-8'));
}

async function fastLogin(context, page, userKey) {
  const tokens = loadTokens();
  const { token, user } = tokens[userKey];
  await context.addInitScript(({ token, user }) => {
    if (window.location.hostname !== '') {
      window.sessionStorage.setItem('token', token);
      window.sessionStorage.setItem('user', JSON.stringify(user));
    }
  }, { token, user });
  await page.goto('/chat');
  await page.waitForSelector('.chat-page, .room-list-panel', { timeout: 10_000 });
}

async function twoBrowsers(browser, userKeyA, userKeyB) {
  const tokens = loadTokens();
  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();
  const tokenA = tokens[userKeyA];
  const tokenB = tokens[userKeyB];

  await ctxA.addInitScript(({ token, user }) => {
    if (window.location.hostname !== '') {
      window.sessionStorage.setItem('token', token);
      window.sessionStorage.setItem('user', JSON.stringify(user));
    }
  }, { token: tokenA.token, user: tokenA.user });

  await ctxB.addInitScript(({ token, user }) => {
    if (window.location.hostname !== '') {
      window.sessionStorage.setItem('token', token);
      window.sessionStorage.setItem('user', JSON.stringify(user));
    }
  }, { token: tokenB.token, user: tokenB.user });

  const pageA = await ctxA.newPage();
  const pageB = await ctxB.newPage();
  return { pageA, pageB, ctxA, ctxB };
}

async function refreshAndWait(page) {
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('.chat-page, .room-list-panel, .login-page, .settings-page, .admin-page', { timeout: 10_000 });
}

module.exports = { loadTokens, fastLogin, twoBrowsers, refreshAndWait };
