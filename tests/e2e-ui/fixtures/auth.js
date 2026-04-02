class AuthPage {
  constructor(page) {
    this.page = page;
  }

  async goto() {
    await this.page.goto('/login');
    await this.page.waitForSelector('.login-card');
  }

  async switchToRegister() {
    await this.page.click('.tab:has-text("Register"), button:has-text("Register")');
  }

  async switchToLogin() {
    await this.page.click('.tab:has-text("Sign In"), button:has-text("Sign In")');
  }

  async register(username, email, password) {
    await this.switchToRegister();
    await this.page.fill('input[name="username"]', username);
    await this.page.fill('input[name="email"]', email);
    await this.page.fill('input[name="password"]', password);
    await this.page.click('button[type="submit"]');
  }

  async login(username, password) {
    await this.page.fill('input[name="username"]', username);
    await this.page.fill('input[name="password"]', password);
    await this.page.click('button[type="submit"]');
  }

  async enter2FACode(code) {
    await this.page.fill('input[name="totp"]', code);
    await this.page.click('button[type="submit"]');
  }

  async logout() {
    await this.page.click('.user-dropdown-trigger');
    await this.page.click('text=Logout');
  }

  async forgotPassword(email) {
    await this.page.click('text=Forgot password?');
    await this.page.fill('input[name="email"]', email);
    await this.page.click('button[type="submit"]');
  }

  async togglePasswordVisibility() {
    await this.page.click('.password-toggle');
  }

  async getErrorMessage() {
    const el = this.page.locator('.login-error, .field-error').first();
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
    return this.page.locator('input[name="totp"]').isVisible();
  }
}

module.exports = { AuthPage };
