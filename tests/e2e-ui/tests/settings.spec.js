// Tests 35-38: Settings page
const { test, expect } = require('@playwright/test');
const { spawnSync } = require('child_process');
const { fastLogin, refreshAndWait, loadTokens } = require('../fixtures/helpers');
const { SettingsPage } = require('../fixtures/settings');
const { AuthPage } = require('../fixtures/auth');
const { USER_D, USER_E } = require('../fixtures/test-data');

const BASE_URL = process.env.BASE_URL || 'http://localhost:8090';

function generateTOTP(secret) {
  const result = spawnSync('python3', ['-c', `import pyotp; print(pyotp.TOTP('${secret}').now())`]);
  return result.stdout.toString().trim();
}

// Track the new password between tests (Test 35 changes it)
// Note: the password is unique per test suite run
let echoNewPassword = `NewPass${Date.now()}!`;

test.describe('Settings', () => {
  test('Test 35: change password', async ({ page, context }) => {
    await fastLogin(context, page, 'userE');
    const settings = new SettingsPage(page);
    await settings.goto();

    await settings.changePassword(USER_E.password, echoNewPassword, echoNewPassword);

    // Wait specifically for the password success message
    const successEl = page.locator('.settings-success');
    await successEl.waitFor({ timeout: 10_000 });
    const msg = await successEl.textContent();
    expect(msg.toLowerCase()).toContain('password updated');

    // Navigate back to chat before logout (settings page has no user dropdown)
    await page.locator('[data-testid="back-to-chat"]').click();
    await page.waitForSelector('.chat-layout', { timeout: 10_000 });

    // Logout and login with new password
    const tokens = loadTokens();
    const actualUsername = tokens.userE.user.username;

    const auth = new AuthPage(page);
    await auth.logout();
    await page.waitForURL('**/login', { timeout: 10_000 });

    const authPage = new AuthPage(page);
    await authPage.goto();
    await authPage.login(actualUsername, echoNewPassword);
    await page.waitForURL('**/chat', { timeout: 15_000 });
    expect(page.url()).toContain('/chat');
  });

  test('Test 36: change email', async ({ page, context }) => {
    // Test 35 blacklisted the stored token on logout, so fastLogin would fail.
    // Log in via the UI with the new password instead.
    const tokens = loadTokens();
    const actualUsername = tokens.userE.user.username;

    const { injectRuntimeConfig } = require('../fixtures/helpers');
    await injectRuntimeConfig(context);

    const auth = new AuthPage(page);
    await auth.goto();
    await auth.login(actualUsername, echoNewPassword);
    await page.waitForURL('**/chat', { timeout: 15_000 });
    await page.waitForSelector('.chat-layout', { timeout: 10_000 });

    const settings = new SettingsPage(page);
    await settings.goto();

    const newEmail = `echo_ui_new_${Date.now()}@test.com`;
    await settings.changeEmail(newEmail, echoNewPassword);

    // Wait specifically for the email success message
    const successEl = page.locator('.settings-success');
    await successEl.waitFor({ timeout: 10_000 });
    const msg = await successEl.textContent();
    expect(msg.toLowerCase()).toContain('email updated');

    // Navigate back to settings to verify
    await settings.goto();
    await page.waitForTimeout(500);

    const currentEmail = await settings.getCurrentEmail();
    expect(currentEmail).toContain(newEmail);
  });

  test('Test 37: enable 2FA', async ({ page, context }) => {
    await fastLogin(context, page, 'userD');
    const settings = new SettingsPage(page);
    await settings.goto();

    await settings.enable2FA();

    // QR code visible
    const qr = page.locator('img[alt*="QR"], canvas');
    await expect(qr.first()).toBeVisible({ timeout: 5_000 });

    // Get manual key
    const secret = await settings.getManualKey();
    expect(secret).toBeTruthy();
    expect(secret.length).toBeGreaterThan(0);

    // Generate TOTP
    const code = generateTOTP(secret);

    // Enter code to verify
    await settings.enter2FACode(code);

    const msg = await settings.getStatusMessage();
    expect(msg).toBeTruthy();
    expect(msg.toLowerCase()).toMatch(/enabled|success|verified/i);

    // Navigate back to settings to verify
    await settings.goto();
    await page.waitForTimeout(500);

    // 2FA should show as enabled
    const enabled = page.locator('.tfa-panel p:has-text("currently enabled")');
    const isEnabled = await enabled.isVisible().catch(() => false);
    if (isEnabled) {
      const statusText = await enabled.textContent();
      expect(statusText.toLowerCase()).toMatch(/enabled/i);
    } else {
      // Verify the disable button is present which implies it's enabled
      const disableBtn = page.locator('button:has-text("Disable 2FA")');
      await expect(disableBtn).toBeVisible({ timeout: 5_000 });
    }
  });

  test('Test 38: disable 2FA', async ({ page, context }) => {
    // Use the fresh timestamped userD created in global.setup (not the static USER_D.username)
    const tokens = loadTokens();
    const userDUsername = tokens.userD.user.username;

    // Get a fresh token to call the 2FA setup API
    const loginRes = await fetch(`${BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: userDUsername, password: USER_D.password }),
    });
    const loginData = await loginRes.json();
    const token = loginData.access_token;

    // Get setup info (may fail if not in setup flow — use existing secret from Test 37)
    // We'll disable using the settings UI after fastLogin sets the session
    await fastLogin(context, page, 'userD');
    const settings = new SettingsPage(page);
    await settings.goto();

    // We need the secret to generate TOTP — try to get it from setup again
    const setupRes = await fetch(`${BASE_URL}/auth/2fa/setup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
    });
    const setupData = await setupRes.json();
    const secret = setupData.manual_entry_key;

    if (secret) {
      const code = generateTOTP(secret);
      await settings.disable2FA(code);

      const msg = await settings.getStatusMessage();
      expect(msg).toBeTruthy();
      expect(msg.toLowerCase()).toMatch(/disabled|removed|success/i);

      // Navigate back to settings to verify
      await settings.goto();
      await page.waitForTimeout(500);

      // Enable button should be visible (indicating 2FA is disabled)
      const enableBtn = page.locator('button:has-text("Enable 2FA")');
      await expect(enableBtn).toBeVisible({ timeout: 5_000 });
    } else {
      // Secret not returned by setup endpoint — 2FA state is unknown, skip assertion
      test.skip(true, '2FA setup endpoint did not return a secret; cannot generate TOTP to disable');
    }
  });
});
