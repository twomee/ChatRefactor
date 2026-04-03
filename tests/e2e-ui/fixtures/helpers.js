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
  const entry = tokens[userKey];
  if (!entry) throw new Error(`No token found for user key "${userKey}"`);
  const { token, user } = entry;
  await injectRuntimeConfig(context);
  await context.addInitScript(({ token, user }) => {
    if (window.location.hostname !== '') {
      window.sessionStorage.setItem('token', token);
      window.sessionStorage.setItem('user', JSON.stringify(user));
    }
  }, { token, user });

  // Navigate to chat page with retry for rate-limit errors
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.goto('/chat', { waitUntil: 'domcontentloaded', timeout: 15_000 });
    const loaded = await page.waitForSelector('.chat-layout', { timeout: 10_000 }).catch(() => null);
    if (loaded) break;

    // Check for rate-limit error page
    const bodyText = await page.locator('body').textContent().catch(() => '');
    const isRateLimited = bodyText.includes('rate limit') || bodyText.includes('429');
    await page.waitForTimeout(isRateLimited ? 30_000 : 2_000);
  }
  await page.waitForSelector('.chat-layout', { timeout: 15_000 });

  // Wait for rooms to load — one reload attempt if they don't appear
  const hasRooms = await page.locator('.room-item, .room-item-available').first()
    .waitFor({ timeout: 5_000 }).then(() => true).catch(() => false);
  if (!hasRooms) {
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.chat-layout', { timeout: 10_000 }).catch(() => {});
    await page.locator('.room-item, .room-item-available').first()
      .waitFor({ timeout: 5_000 }).catch(() => {});
  }
}

async function twoBrowsers(browser, userKeyA, userKeyB) {
  const tokens = loadTokens();
  const ctxA = await browser.newContext({ baseURL: BASE_URL });
  const ctxB = await browser.newContext({ baseURL: BASE_URL });
  const tokenA = tokens[userKeyA];
  const tokenB = tokens[userKeyB];
  if (!tokenA) throw new Error(`No token found for user key "${userKeyA}"`);
  if (!tokenB) throw new Error(`No token found for user key "${userKeyB}"`);

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

  // Navigate browsers to the chat page sequentially to avoid rate-limit storms
  await navigateWithRetry(pageA, '/chat');
  // Wait for room list to load — retry with longer backoff on rate-limit
  for (let i = 0; i < 2; i++) {
    const roomsA = await pageA.locator('.room-item, .room-item-available').first()
      .waitFor({ timeout: 8_000 }).then(() => true).catch(() => false);
    if (roomsA) break;
    const bodyA = await pageA.locator('body').textContent().catch(() => '');
    const delay = (bodyA.includes('rate limit') || bodyA.includes('429')) ? 15_000 : 3_000;
    await pageA.waitForTimeout(delay);
    await pageA.reload({ waitUntil: 'domcontentloaded' });
    await pageA.waitForSelector('.chat-layout', { timeout: 10_000 }).catch(() => {});
  }
  // Small delay between navigations to avoid rate limiting
  await pageA.waitForTimeout(1_500);
  await navigateWithRetry(pageB, '/chat');
  // Wait for room list to load on pageB
  for (let i = 0; i < 2; i++) {
    const roomsB = await pageB.locator('.room-item, .room-item-available').first()
      .waitFor({ timeout: 8_000 }).then(() => true).catch(() => false);
    if (roomsB) break;
    const bodyB = await pageB.locator('body').textContent().catch(() => '');
    const delay = (bodyB.includes('rate limit') || bodyB.includes('429')) ? 15_000 : 3_000;
    await pageB.waitForTimeout(delay);
    await pageB.reload({ waitUntil: 'domcontentloaded' });
    await pageB.waitForSelector('.chat-layout', { timeout: 10_000 }).catch(() => {});
  }

  return { pageA, pageB, ctxA, ctxB };
}

/**
 * Navigate to a page with retry logic for rate-limit resilience.
 */
async function navigateWithRetry(page, path) {
  await page.goto(path, { waitUntil: 'domcontentloaded', timeout: 15_000 });
  const loaded = await page.waitForSelector(
    '.chat-layout, .login-card, .settings-layout, .admin-page',
    { timeout: 10_000 }
  ).catch(() => null);
  if (loaded) return;

  // Check for rate-limit error and retry with longer backoff
  const bodyText = await page.locator('body').textContent().catch(() => '');
  const delay = (bodyText.includes('rate limit') || bodyText.includes('429')) ? 15_000 : 2_000;
  await page.waitForTimeout(delay);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.chat-layout, .admin-page', { timeout: 15_000 });
}

async function refreshAndWait(page) {
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 15_000 });
  const loaded = await page.waitForSelector(
    '.chat-layout, .login-card, .settings-layout, .admin-page',
    { timeout: 10_000 }
  ).catch(() => null);
  if (loaded) return;

  // One retry for rate limit
  const bodyText = await page.locator('body').textContent().catch(() => '');
  if (bodyText.includes('rate limit') || bodyText.includes('429') || bodyText.includes('404')) {
    await page.waitForTimeout(3_000);
    await page.reload({ waitUntil: 'domcontentloaded' });
  }
  await page.waitForSelector('.chat-layout, .login-card, .settings-layout, .admin-page', { timeout: 10_000 });
}

module.exports = { loadTokens, injectRuntimeConfig, fastLogin, twoBrowsers, refreshAndWait };
