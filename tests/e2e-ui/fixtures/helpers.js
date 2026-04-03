const fs = require('fs');
const path = require('path');

const TOKENS_PATH = path.join(__dirname, '..', 'playwright', '.auth', 'tokens.json');
const BASE_URL = process.env.BASE_URL || 'http://localhost:8090';
const WS_BASE = BASE_URL.replace(/^http/, 'ws');

function loadTokens() {
  return JSON.parse(fs.readFileSync(TOKENS_PATH, 'utf-8'));
}

/**
 * Override the frontend's runtime config so API calls go to BASE_URL
 * instead of whatever the container default provides.
 *
 * Strategy: intercept the /config.js request (loaded via <script> before the
 * app bundle) and replace its content with the correct API/WS base URLs.
 * This is more reliable than addInitScript because addInitScript runs before
 * ALL scripts — but the container's config.js runs after addInitScript and
 * would overwrite window.__RUNTIME_CONFIG__.
 */
async function injectRuntimeConfig(context) {
  await context.route('**/config.js', async (route) => {
    await route.fulfill({
      contentType: 'application/javascript',
      body: `window.__RUNTIME_CONFIG__ = { VITE_API_BASE: "${BASE_URL}", VITE_WS_BASE: "${WS_BASE}" };`,
    });
  });
}

async function fastLogin(context, page, userKey) {
  const tokens = loadTokens();
  const { token, user } = tokens[userKey];
  await injectRuntimeConfig(context);
  await context.addInitScript(({ token, user }) => {
    if (window.location.hostname !== '') {
      window.sessionStorage.setItem('token', token);
      window.sessionStorage.setItem('user', JSON.stringify(user));
    }
  }, { token, user });
  await page.goto('/chat');
  await page.waitForSelector('.chat-layout', { timeout: 10_000 });
}

async function twoBrowsers(browser, userKeyA, userKeyB) {
  const tokens = loadTokens();
  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();
  const tokenA = tokens[userKeyA];
  const tokenB = tokens[userKeyB];

  await injectRuntimeConfig(ctxA);
  await injectRuntimeConfig(ctxB);

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
  await page.waitForSelector('.chat-layout, .login-card, .settings-layout, .admin-page', { timeout: 10_000 });
}

module.exports = { loadTokens, injectRuntimeConfig, fastLogin, twoBrowsers, refreshAndWait };
