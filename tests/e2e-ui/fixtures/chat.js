class ChatPage {
  constructor(page) {
    this.page = page;
  }

  // ── Rooms ──
  async joinRoom(name) {
    await this.page.click(`.room-item:has-text("${name}") >> text=Join`);
  }

  async exitRoom(name) {
    const room = this.page.locator(`.room-item:has-text("${name}")`);
    await room.hover();
    await room.locator('.room-exit-btn, .room-close-btn').click();
  }

  async switchRoom(name) {
    await this.page.click(`.room-item:has-text("${name}")`);
    await this.page.waitForTimeout(500);
  }

  async getUnreadBadge(roomName) {
    const badge = this.page.locator(`.room-item:has-text("${roomName}") .unread-badge`);
    if (await badge.isVisible()) return badge.textContent();
    return null;
  }

  async getNewMessagesDivider() {
    return this.page.locator('.new-messages-divider');
  }

  // ── Messages ──
  async sendMessage(text) {
    await this.page.fill('.msg-input input, .msg-input textarea', text);
    await this.page.keyboard.press('Enter');
  }

  async getMessage(text) {
    return this.page.locator(`.msg:has-text("${text}")`);
  }

  async editMessage(msgText, newText) {
    const msg = this.page.locator(`.msg:has-text("${msgText}")`);
    await msg.hover();
    await msg.locator('.msg-action-edit, [title="Edit"]').click();
    await this.page.fill('.msg-input input, .msg-input textarea', newText);
    await this.page.keyboard.press('Enter');
  }

  async deleteMessage(msgText) {
    const msg = this.page.locator(`.msg:has-text("${msgText}")`);
    await msg.hover();
    await msg.locator('.msg-action-delete, [title="Delete"]').click();
  }

  async addReaction(msgText, emoji) {
    const msg = this.page.locator(`.msg:has-text("${msgText}")`);
    await msg.locator('.reaction-add-btn, [title="Add reaction"]').click();
    await this.page.locator(`[data-emoji-mart] button[aria-label*="${emoji}"]`).first().click();
  }

  async removeReaction(msgText, emoji) {
    const msg = this.page.locator(`.msg:has-text("${msgText}")`);
    await msg.locator(`.reaction-chip:has-text("${emoji}")`).click();
  }

  async clearHistory() {
    await this.page.click('.clear-history-btn, [title*="Clear"]');
    await this.page.click('[data-testid="clear-yes"], button:has-text("Yes")');
  }

  // ── Files ──
  async uploadFile(filePath) {
    const input = this.page.locator('input[type="file"]');
    await input.setInputFiles(filePath);
  }

  async getFileMessage(fileName) {
    return this.page.locator(`.msg:has-text("${fileName}")`);
  }

  // ── Search ──
  async openSearch() {
    await this.page.keyboard.press('Control+k');
    await this.page.waitForSelector('.search-modal');
  }

  async search(query) {
    await this.page.fill('.search-modal input', query);
    await this.page.waitForTimeout(500);
  }

  async getSearchResults() {
    return this.page.locator('.search-result');
  }

  async clickSearchResult(index) {
    await this.page.locator('.search-result').nth(index).click();
  }

  // ── User list (admin actions) ──
  async rightClickUser(username) {
    await this.page.locator(`.user-item:has-text("${username}")`).click({ button: 'right' });
  }

  async clickContextMenuItem(text) {
    await this.page.locator(`.context-menu-item:has-text("${text}")`).click();
  }

  async muteUser(username) {
    await this.rightClickUser(username);
    await this.clickContextMenuItem('Mute');
  }

  async kickUser(username) {
    await this.rightClickUser(username);
    await this.clickContextMenuItem('Kick');
  }

  async promoteUser(username) {
    await this.rightClickUser(username);
    await this.clickContextMenuItem('Make Admin');
  }

  // ── Presence ──
  async getOnlineUsers() {
    const items = this.page.locator('.user-item .user-item-name');
    return items.allTextContents();
  }

  async isUserInList(username) {
    return this.page.locator(`.user-item:has-text("${username}")`).isVisible();
  }

  async getMutedBanner() {
    return this.page.locator('.muted-banner');
  }

  async getTypingIndicator() {
    return this.page.locator('.typing-indicator');
  }

  async getConnectionStatus() {
    return this.page.locator('.connection-status');
  }

  // ── PM ──
  async startPM(username) {
    await this.page.locator(`.user-item:has-text("${username}")`).click();
  }

  async getPMOfflineBanner() {
    return this.page.locator('.pm-offline-banner');
  }

  async deletePMConversation(username) {
    const pm = this.page.locator(`.pm-item:has-text("${username}")`);
    await pm.hover();
    await pm.locator('.pm-close-btn, .pm-delete-btn').click();
  }

  async clearPMHistory() {
    await this.page.click('[data-testid="clear-pm-history"]');
    await this.page.click('[data-testid="clear-pm-yes"]');
  }

  // ── Toast ──
  async getToast() {
    return this.page.locator('.toast-card').first();
  }

  async waitForToast(text) {
    await this.page.locator(`.toast-card:has-text("${text}")`).waitFor({ timeout: 5000 });
  }
}

module.exports = { ChatPage };
