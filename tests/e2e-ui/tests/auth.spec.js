// Tests 1-8: Authentication flows
const { test, expect } = require('@playwright/test');
const { spawnSync } = require('child_process');
const { fastLogin } = require('../fixtures/helpers');
const { AuthPage } = require('../fixtures/auth');
const { USER_D } = require('../fixtures/test-data');

const BASE_URL = process.env.BASE_URL || 'http://localhost:8090';

function generateTOTP(secret) {
  const result = spawnSync('python3', ['-c', `import pyotp; print(pyotp.TOTP('${secret}').now())`]);
  return result.stdout.toString().trim();
}

test.describe('Auth', () => {
  test('Test 1: register and land on chat', async ({ page }) => {
    const ts = Date.now();
    const username = `reguser_${ts}`;
    const email = `reguser_${ts}@test.com`;
    const password = 'Test1234!';

    const auth = new AuthPage(page);
    await auth.goto();
    await auth.register(username, email, password);
    await page.waitForURL('**/chat', { timeout: 15_000 });
    expect(page.url()).toContain('/chat');

    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForSelector('.chat-page, .room-list-panel', { timeout: 10_000 });
    expect(page.url()).toContain('/chat');
  });

  test('Test 2: duplicate email error', async ({ page }) => {
    const ts = Date.now();
    const email = `dupuser_${ts}@test.com`;
    const password = 'Test1234!';

    const auth = new AuthPage(page);
    await auth.goto();
    await auth.register(`dupuser_${ts}`, email, password);
    await page.waitForURL('**/chat', { timeout: 15_000 });

    await auth.goto();
    await auth.register(`dupuser2_${ts}`, email, password);

    const err = await auth.getErrorMessage();
    expect(err).toBeTruthy();
    expect(err.length).toBeGreaterThan(0);
  });

  test('Test 3: wrong password error with shake', async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.goto();
    await auth.login('alice_ui', 'wrongpassword!');

    const err = await auth.getErrorMessage();
    expect(err).toBeTruthy();
    expect(err.length).toBeGreaterThan(0);
  });

  test('Test 4: login with 2FA', async ({ page }) => {
    const loginRes = await fetch(`${BASE_URL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: USER_D.username, password: USER_D.password }),
    });
    const { token } = await loginRes.json();

    const setupRes = await fetch(`${BASE_URL}/2fa/setup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
    });
    const { secret } = await setupRes.json();

    const code = generateTOTP(secret);

    await fetch(`${BASE_URL}/2fa/verify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ code }),
    });

    const auth = new AuthPage(page);
    await auth.goto();
    await auth.login(USER_D.username, USER_D.password);

    await page.waitForSelector('input[name="totp"]', { timeout: 10_000 });
    expect(await auth.isOn2FAScreen()).toBe(true);

    const freshCode = generateTOTP(secret);
    await auth.enter2FACode(freshCode);

    await page.waitForURL('**/chat', { timeout: 15_000 });
    expect(page.url()).toContain('/chat');
  });

  test('Test 5: wrong 2FA code', async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.goto();
    await auth.login(USER_D.username, USER_D.password);

    await page.waitForSelector('input[name="totp"]', { timeout: 10_000 });
    expect(await auth.isOn2FAScreen()).toBe(true);

    await auth.enter2FACode('000000');

    const err = await auth.getErrorMessage();
    expect(err).toBeTruthy();
    expect(err.length).toBeGreaterThan(0);

    expect(await auth.isOn2FAScreen()).toBe(true);
  });

  test('Test 6: logout redirects to login', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    await page.waitForSelector('.chat-page, .room-list-panel', { timeout: 10_000 });

    const auth = new AuthPage(page);
    await auth.logout();

    await page.waitForURL('**/login', { timeout: 10_000 });
    expect(page.url()).toContain('/login');

    await page.goto('/chat');
    await page.waitForURL('**/login', { timeout: 10_000 });
    expect(page.url()).toContain('/login');
  });

  test('Test 7: forgot password flow', async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.goto();
    await auth.forgotPassword('alice_ui@test.com');

    const success = page.locator('.success-message, .forgot-success, [data-testid="forgot-success"]');
    await success.waitFor({ timeout: 10_000 });
    const txt = await success.textContent();
    expect(txt).toBeTruthy();
    expect(txt.length).toBeGreaterThan(0);

    const backBtn = page.locator('button:has-text("Back"), a:has-text("Back"), [data-testid="back-to-login"]').first();
    await backBtn.click();

    await page.waitForSelector('.login-card', { timeout: 5_000 });
    const loginForm = page.locator('input[name="username"], input[name="password"]').first();
    expect(await loginForm.isVisible()).toBe(true);
  });

  test('Test 8: password visibility toggle', async ({ page }) => {
    const auth = new AuthPage(page);
    await auth.goto();

    const passwordInput = page.locator('input[name="password"]');
    await passwordInput.fill('MySecret123!');

    expect(await passwordInput.getAttribute('type')).toBe('password');

    await auth.togglePasswordVisibility();
    expect(await passwordInput.getAttribute('type')).toBe('text');

    await auth.togglePasswordVisibility();
    expect(await passwordInput.getAttribute('type')).toBe('password');
  });
});
