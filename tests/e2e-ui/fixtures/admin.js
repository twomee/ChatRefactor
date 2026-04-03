class AdminPage {
  constructor(page) {
    this.page = page;
  }

  async goto() {
    // Try direct URL navigation first
    for (let attempt = 0; attempt < 3; attempt++) {
      await this.page.goto('/admin', { waitUntil: 'domcontentloaded', timeout: 20_000 });
      const loaded = await this.page.waitForSelector('.admin-page', { timeout: 10_000 }).catch(() => null);
      if (loaded) return;

      // Check for 404 or rate limit — fall back to SPA navigation
      const bodyText = await this.page.locator('body').textContent().catch(() => '');
      if (bodyText.includes('404') || bodyText.includes('not found')) {
        // Navigate via SPA: go to /chat first, then use dropdown
        await this.page.goto('/chat', { waitUntil: 'domcontentloaded', timeout: 20_000 });
        await this.page.waitForSelector('.chat-layout', { timeout: 15_000 }).catch(() => {});
        await this.page.locator('[data-testid="user-dropdown-trigger"]').click();
        const adminItem = this.page.locator('[data-testid="dropdown-admin"]');
        const hasAdmin = await adminItem.isVisible().catch(() => false);
        if (hasAdmin) {
          await adminItem.click();
          const loaded2 = await this.page.waitForSelector('.admin-page', { timeout: 15_000 }).catch(() => null);
          if (loaded2) return;
        }
      }
      if (bodyText.includes('rate limit') || bodyText.includes('429')) {
        await this.page.waitForTimeout(5_000);
        continue;
      }
    }
    await this.page.waitForSelector('.admin-page', { timeout: 15_000 });
  }

  async createRoom(name) {
    await this.page.fill('input[placeholder="Room name..."]', name);
    await this.page.click('button:has-text("Create Room")');
  }

  async closeRoom(name) {
    const row = this.page.locator(`tr:has-text("${name}")`);
    await row.locator('button:has-text("Close")').click();
  }

  async openRoom(name) {
    const row = this.page.locator(`tr:has-text("${name}")`);
    await row.locator('button:has-text("Open")').click();
  }

  async getRoomStatus(name) {
    const row = this.page.locator(`tr:has-text("${name}")`);
    return row.locator('.admin-room-status').textContent();
  }

  async promoteUser(username) {
    await this.page.fill('input[placeholder="Username..."]', username);
    await this.page.click('button:has-text("Promote")');
  }

  async expandFiles(roomName) {
    const row = this.page.locator(`tr:has-text("${roomName}")`);
    await row.locator('button:has-text("Files")').click();
  }

  async clickResetDatabase() {
    this.page.once('dialog', dialog => dialog.dismiss());
    await this.page.click('button:has-text("Reset Database")');
  }

  async getStatus() {
    return this.page.locator('.admin-status').textContent();
  }
}

module.exports = { AdminPage };
