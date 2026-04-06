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

// Track the 2FA secret between tests — Test 37 enables 2FA and saves the secret,
// Test 38 reuses it to generate a TOTP code for disable. Without this, Test 38
// would try to call /auth/login as a 2FA-enabled user, get requires_2fa:true
// instead of an access_token, and never be able to obtain the TOTP secret.
let userDTOTPSecret = null;

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

    // Get manual key and save it for Test 38 (which needs it to disable 2FA)
    const secret = await settings.getManualKey();
    expect(secret).toBeTruthy();
    expect(secret.length).toBeGreaterThan(0);
    userDTOTPSecret = secret;

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
    // Test 37 saved the TOTP secret in userDTOTPSecret so we can generate a valid code.
    // Without it, Test 38 cannot disable 2FA: calling /auth/login for a 2FA-enabled
    // user returns requires_2fa:true (no access_token), and /auth/2fa/setup with
    // an invalid token returns 401, so manual_entry_key is never obtained.
    if (!userDTOTPSecret) {
      test.skip(true, 'Test 37 did not save the TOTP secret; cannot generate a code to disable 2FA');
      return;
    }

    await fastLogin(context, page, 'userD');
    const settings = new SettingsPage(page);
    await settings.goto();

    const code = generateTOTP(userDTOTPSecret);
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
  });
});
