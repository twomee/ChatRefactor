class SettingsPage {
  constructor(page) {
    this.page = page;
  }

  async goto() {
    await this.page.goto('/settings');
    await this.page.waitForSelector('.settings-page');
  }

  async changePassword(current, newPass, confirm) {
    await this.page.fill('input[placeholder="Current Password"]', current);
    await this.page.fill('input[placeholder="New Password"]', newPass);
    await this.page.fill('input[placeholder="Confirm New Password"]', confirm);
    await this.page.click('button:has-text("Update Password")');
  }

  async changeEmail(newEmail, currentPassword) {
    await this.page.fill('input[placeholder="New Email"]', newEmail);
    await this.page.fill('input[placeholder="Current Password"]', currentPassword);
    await this.page.click('button:has-text("Update Email")');
  }

  async enable2FA() {
    await this.page.click('button:has-text("Enable 2FA")');
    await this.page.waitForSelector('img[alt*="QR"], canvas');
  }

  async getManualKey() {
    await this.page.click('text=Cannot scan');
    const key = await this.page.locator('.manual-key, .totp-manual-key').textContent();
    return key.trim();
  }

  async enter2FACode(code) {
    await this.page.fill('input[placeholder*="6-digit"], input[name="totp"]', code);
    await this.page.click('button:has-text("Verify")');
  }

  async disable2FA(code) {
    await this.page.fill('input[placeholder*="code to disable"], input[name="totp"]', code);
    await this.page.click('button:has-text("Disable 2FA")');
  }

  async getStatusMessage() {
    const el = this.page.locator('.settings-status, .success-message, .error-message').first();
    await el.waitFor({ timeout: 5000 });
    return el.textContent();
  }

  async getCurrentEmail() {
    return this.page.locator('.current-email, .profile-email').textContent();
  }
}

module.exports = { SettingsPage };
