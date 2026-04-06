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
        await this.page.waitForTimeout(30_000);
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
    await this._toggleRoom(name, 'Close', 'Open');
  }

  async openRoom(name) {
    await this._toggleRoom(name, 'Open', 'Close');
  }

  /**
   * Click a room action button and wait for the UI to confirm the state flip.
   * In K8s, the admin panel's fire-and-forget loadData() can take >20s, and
   * navigating away to reload can abort the in-flight API request. So we:
   *  1. Click the button and wait up to 15s for the in-page update.
   *  2. If that times out, wait for the API to settle (the request is still
   *     in-flight), then reload to check the actual server state.
   *  3. If the reload shows the operation didn't complete (e.g. request was
   *     somehow lost), re-click and wait with a generous timeout.
   */
  async _toggleRoom(name, clickLabel, expectLabel) {
    const row = this.page.locator(`tr:has-text("${name}")`).first();
    await row.locator(`button:has-text("${clickLabel}")`).click();

    // 1. Wait for in-page update (loadData callback)
    const flipped = await row.locator(`button:has-text("${expectLabel}")`)
      .waitFor({ timeout: 15_000 }).then(() => true).catch(() => false);
    if (flipped) return;

    // 2. Give the API request a moment to finish server-side before navigating
    await this.page.waitForTimeout(3_000);
    await this.goto();
    const freshRow = this.page.locator(`tr:has-text("${name}")`).first();
    await freshRow.waitFor({ timeout: 15_000 });

    const done = await freshRow.locator(`button:has-text("${expectLabel}")`)
      .isVisible().catch(() => false);
    if (done) return;

    // 3. Operation didn't land — re-click and wait with a longer timeout
    await freshRow.locator(`button:has-text("${clickLabel}")`).click();
    await freshRow.locator(`button:has-text("${expectLabel}")`)
      .waitFor({ timeout: 30_000 });
  }

  async getRoomStatus(name) {
    const row = this.page.locator(`tr:has-text("${name}")`).first();
    return row.locator('.admin-room-status').textContent();
  }

  async promoteUser(username) {
    await this.page.fill('input[placeholder="Username..."]', username);
    await this.page.click('button:has-text("Promote")');
  }

  async expandFiles(roomName) {
    const row = this.page.locator(`tr:has-text("${roomName}")`).first();
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
