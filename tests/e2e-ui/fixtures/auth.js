const { injectRuntimeConfig } = require('./helpers');

class AuthPage {
  constructor(page) {
    this.page = page;
    this._configInjected = false;
  }

  async goto() {
    // Ensure the frontend's API calls go to BASE_URL, not the container default.
    if (!this._configInjected) {
      await injectRuntimeConfig(this.page.context());
      this._configInjected = true;
    }
    await this.page.goto('/login');
    await this.page.waitForSelector('.login-card');
  }

  async switchToRegister() {
    await this.page.click('.login-tab:has-text("Register")');
  }

  async switchToLogin() {
    await this.page.click('.login-tab:has-text("Sign In")');
  }

  /**
   * Register a new user. The app does NOT auto-login after registration —
   * it shows "Registered! Now log in." and switches to the login tab.
   * This helper registers then logs in so the caller lands on /chat.
   */
  async register(username, email, password) {
    await this.switchToRegister();
    await this.page.fill('input[name="username"]', username);
    await this.page.fill('input[name="email"]', email);
    await this.page.fill('input[name="password"]', password);
    await this.page.click('button[type="submit"]');

    // Wait for the success message and automatic switch to login tab
    await this.page.waitForSelector('.login-error.success', { timeout: 10_000 });

    // Now log in with the same credentials
    await this.page.fill('input[name="username"]', username);
    await this.page.fill('input[name="password"]', password);
    await this.page.click('button[type="submit"]');
  }

  async login(username, password) {
    await this.page.fill('input[name="username"]', username);
    await this.page.fill('input[name="password"]', password);
    await this.page.click('button[type="submit"]');
  }

  async enter2FACode(code) {
    await this.page.fill('[data-testid="totp-input"]', code);
    await this.page.click('button[type="submit"]');
  }

  async logout() {
    await this.page.click('[data-testid="user-dropdown-trigger"]');
    await this.page.click('[data-testid="dropdown-logout"]');
  }

  async forgotPassword(email) {
    await this.page.click('text=Forgot password?');
    await this.page.fill('[data-testid="forgot-email-input"]', email);
    await this.page.click('button[type="submit"]');
  }

  async togglePasswordVisibility() {
    await this.page.click('.input-icon-btn');
  }

  async getErrorMessage() {
    const el = this.page.locator('.login-error.error, .field-error').first();
    await el.waitFor({ timeout: 5000 });
    return el.textContent();
  }

  async getSuccessMessage() {
    const el = this.page.locator('.login-error.success').first();
    await el.waitFor({ timeout: 5000 });
    return el.textContent();
  }

  async getPasswordStrength() {
    return this.page.locator('[data-testid="password-strength"]');
  }

  async hasShakeAnimation() {
    const card = this.page.locator('.login-card');
    return card.evaluate(el => el.classList.contains('shake'));
  }

  async isOn2FAScreen() {
    return this.page.locator('[data-testid="totp-input"]').isVisible();
  }
}

module.exports = { AuthPage };
