class SettingsPage {
  constructor(page) {
    this.page = page;
  }

  async goto() {
    await this.page.goto('/settings');
    await this.page.waitForSelector('.settings-layout');
  }

  async changePassword(current, newPass, confirm) {
    await this.page.fill('#current-password', current);
    await this.page.fill('#new-password', newPass);
    await this.page.fill('#confirm-password', confirm);
    await this.page.click('button:has-text("Update Password")');
  }

  async changeEmail(newEmail, currentPassword) {
    await this.page.fill('#new-email', newEmail);
    await this.page.fill('#email-password', currentPassword);
    await this.page.click('button:has-text("Update Email")');
  }

  async enable2FA() {
    await this.page.click('button:has-text("Enable 2FA")');
    await this.page.waitForSelector('img[alt*="QR"]');
  }

  async getManualKey() {
    await this.page.click('text=Cannot scan');
    // The manual key is displayed in a div with monospace font inside the tfa-panel
    const keyEl = this.page.locator('.tfa-panel div[style*="monospace"]');
    await keyEl.waitFor({ timeout: 5000 });
    const key = await keyEl.textContent();
    return key.trim();
  }

  async enter2FACode(code) {
    await this.page.fill('[data-testid="tfa-setup-code"]', code);
    await this.page.click('button:has-text("Verify")');
  }

  async disable2FA(code) {
    await this.page.fill('[data-testid="tfa-disable-code"]', code);
    await this.page.click('button:has-text("Disable 2FA")');
  }

  async getStatusMessage() {
    const el = this.page.locator('.settings-error, .settings-success, .tfa-msg').first();
    await el.waitFor({ timeout: 5000 });
    return el.textContent();
  }

  async getCurrentEmail() {
    return this.page.locator('.settings-current-value').textContent();
  }
}

module.exports = { SettingsPage };
