// Tests 1-8: Authentication flows
const { test, expect } = require('@playwright/test');
const { spawnSync } = require('child_process');
const { fastLogin } = require('../fixtures/helpers');
const { AuthPage } = require('../fixtures/auth');

const BASE_URL = process.env.BASE_URL || 'http://localhost:8090';

function generateTOTP(secret) {
  const result = spawnSync('python3', ['-c', `import pyotp; print(pyotp.TOTP('${secret}').now())`]);
  return result.stdout.toString().trim();
}

/**
 * Register a user via API and return { username, password, token }.
 */
async function apiRegisterAndLogin(username, password, email) {
  await fetch(`${BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, email }),
  });
  const loginRes = await fetch(`${BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const data = await loginRes.json();
  return { username, password, token: data.access_token };
}

/**
 * Enable 2FA for a user via API. Returns the TOTP secret.
 */
async function apiEnable2FA(token) {
  const setupRes = await fetch(`${BASE_URL}/auth/2fa/setup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
  });
  const setupData = await setupRes.json();
  const secret = setupData.manual_entry_key;

  const code = generateTOTP(secret);
  await fetch(`${BASE_URL}/auth/2fa/verify-setup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ code }),
  });

  return secret;
}

// Shared state for 2FA tests — Test 4 sets up, Test 5 reuses.
let twoFAUser = null;
let twoFASecret = null;

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
    await page.waitForSelector('.chat-layout', { timeout: 10_000 });
    expect(page.url()).toContain('/chat');
  });

  test('Test 2: duplicate email error', async ({ page }) => {
    const ts = Date.now();
    const email = `dupuser_${ts}@test.com`;
    const password = 'Test1234!';

    // First registration + login
    const auth = new AuthPage(page);
    await auth.goto();
    await auth.register(`dupuser_${ts}`, email, password);
    await page.waitForURL('**/chat', { timeout: 15_000 });

    // Try to register a second user with the same email
    await auth.goto();
    await auth.switchToRegister();
    await page.fill('input[name="username"]', `dupuser2_${ts}`);
    await page.fill('input[name="email"]', email);
    await page.fill('input[name="password"]', password);
    await page.click('button[type="submit"]');

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
    // Create a fresh user and enable 2FA via API
    const ts = Date.now();
    const username = `twofa_${ts}`;
    const password = 'Test1234!';
    const email = `twofa_${ts}@test.com`;

    const user = await apiRegisterAndLogin(username, password, email);
    const secret = await apiEnable2FA(user.token);

    // Store for Test 5
    twoFAUser = { username, password };
    twoFASecret = secret;

    // Login via the UI — should prompt for 2FA
    const auth = new AuthPage(page);
    await auth.goto();
    await auth.login(username, password);

    await page.waitForSelector('[data-testid="totp-input"]', { timeout: 10_000 });
    expect(await auth.isOn2FAScreen()).toBe(true);

    const freshCode = generateTOTP(secret);
    await auth.enter2FACode(freshCode);

    await page.waitForURL('**/chat', { timeout: 15_000 });
    expect(page.url()).toContain('/chat');
  });

  test('Test 5: wrong 2FA code', async ({ page }) => {
    // If Test 4 didn't run, create a fresh 2FA user
    if (!twoFAUser) {
      const ts = Date.now();
      const username = `twofa5_${ts}`;
      const password = 'Test1234!';
      const email = `twofa5_${ts}@test.com`;
      const user = await apiRegisterAndLogin(username, password, email);
      await apiEnable2FA(user.token);
      twoFAUser = { username, password };
    }

    const auth = new AuthPage(page);
    await auth.goto();
    await auth.login(twoFAUser.username, twoFAUser.password);

    await page.waitForSelector('[data-testid="totp-input"]', { timeout: 10_000 });
    expect(await auth.isOn2FAScreen()).toBe(true);

    await auth.enter2FACode('000000');

    const err = await auth.getErrorMessage();
    expect(err).toBeTruthy();
    expect(err.length).toBeGreaterThan(0);

    expect(await auth.isOn2FAScreen()).toBe(true);
  });

  test('Test 6: logout redirects to login', async ({ page, context }) => {
    await fastLogin(context, page, 'userA');
    await page.waitForSelector('.chat-layout', { timeout: 10_000 });

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

    // The success message uses class .login-error.success
    const success = page.locator('.login-error.success');
    await success.waitFor({ timeout: 10_000 });
    const txt = await success.textContent();
    expect(txt).toBeTruthy();
    expect(txt.length).toBeGreaterThan(0);

    // Click "Back to Login"
    const backBtn = page.locator('button.btn-ghost:has-text("Back to Login")');
    await backBtn.click();

    // Verify we're back on the login form
    await page.waitForSelector('.login-card', { timeout: 5_000 });
    const loginForm = page.locator('input[name="username"]').first();
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
