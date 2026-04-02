class AdminPage {
  constructor(page) {
    this.page = page;
  }

  async goto() {
    await this.page.goto('/admin');
    await this.page.waitForSelector('.admin-page');
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
    return row.locator('.admin-room-status, td:nth-child(3)').textContent();
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
