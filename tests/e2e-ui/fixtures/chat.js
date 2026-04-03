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
    await room.locator('.room-exit-btn').click();
  }

  async switchRoom(name) {
    // Wait for the room list to load — retry if rooms aren't appearing (rate limit recovery)
    for (let attempt = 0; attempt < 3; attempt++) {
      const hasRooms = await this.page.locator('.room-item, .room-item-available').first()
        .waitFor({ timeout: 10_000 }).then(() => true).catch(() => false);
      if (hasRooms) break;
      // Rooms didn't load — try reloading the page
      await this.page.reload({ waitUntil: 'domcontentloaded' });
      await this.page.waitForSelector('.chat-layout', { timeout: 15_000 }).catch(() => {});
    }
    await this.page.waitForSelector('.room-item, .room-item-available', { timeout: 15_000 });

    // If the room has a Join button (in "Available" section), join it first
    const joinBtn = this.page.locator(`.room-item-available:has-text("${name}") .room-join-btn`);
    const joinVisible = await joinBtn.waitFor({ timeout: 2_000 }).then(() => true).catch(() => false);
    if (joinVisible) {
      await joinBtn.click();
      // After join, the room auto-selects — wait for input or muted banner
      await this.page.waitForSelector('.message-input, .muted-banner', { timeout: 10_000 });
      return;
    }
    // Room is already joined — click to select it
    await this.page.locator(`.room-item:has-text("${name}")`).first().click();
    await this.page.waitForSelector('.message-input, .muted-banner', { timeout: 10_000 });
  }

  async getUnreadBadge(roomName) {
    const badge = this.page.locator(`.room-item:has-text("${roomName}") .unread-badge`);
    const isVisible = await badge.isVisible().catch(() => false);
    if (isVisible) return badge.textContent();
    return null;
  }

  async getNewMessagesDivider() {
    return this.page.locator('.new-messages-divider');
  }

  // ── Messages ──
  async waitForConnection() {
    // Wait until the "Reconnecting..." status disappears (WebSocket is connected)
    const reconnecting = this.page.locator('text=Reconnecting');
    await reconnecting.waitFor({ state: 'hidden', timeout: 15_000 }).catch(() => {});
  }

  async sendMessage(text) {
    await this.waitForConnection();
    const input = this.page.locator('.message-input');
    await input.waitFor({ timeout: 10_000 });
    await input.click();
    await input.fill(text);
    // Small delay to ensure React state updates before pressing Enter
    await this.page.waitForTimeout(100);
    await this.page.keyboard.press('Enter');
    // Wait for the send to complete (input should clear)
    await this.page.waitForTimeout(300);
  }

  async getMessage(text) {
    return this.page.locator(`.msg:has-text("${text}")`);
  }

  async editMessage(msgText, newText) {
    const msg = this.page.locator(`.msg:has-text("${msgText}")`).first();
    await msg.scrollIntoViewIfNeeded();
    await msg.hover();
    // Wait for the Edit button to appear (revealed by hover via CSS)
    const editBtn = msg.locator('.msg-action-btn[title="Edit"]');
    await editBtn.waitFor({ timeout: 5_000 });
    await editBtn.click();
    // Wait for the edit banner to appear
    await this.page.locator('.edit-banner').waitFor({ timeout: 5_000 });
    const input = this.page.locator('.message-input');
    await input.click();
    await input.fill(newText);
    await this.page.waitForTimeout(100);
    await this.page.keyboard.press('Enter');
    // Wait for the edit to complete (banner should disappear)
    await this.page.locator('.edit-banner').waitFor({ state: 'hidden', timeout: 5_000 }).catch(() => {});
    await this.page.waitForTimeout(500);
  }

  async deleteMessage(msgText) {
    const msg = this.page.locator(`.msg:has-text("${msgText}")`).first();
    await msg.scrollIntoViewIfNeeded();
    await msg.hover();
    const deleteBtn = msg.locator('.msg-action-btn[title="Delete"]');
    await deleteBtn.waitFor({ timeout: 5_000 });
    await deleteBtn.click();
  }

  async addReaction(msgText, emojiChar) {
    const msg = this.page.locator(`.msg:has-text("${msgText}")`).first();
    // Wait for message to be present, then scroll into view
    await msg.waitFor({ timeout: 10_000 });
    await msg.scrollIntoViewIfNeeded();
    await msg.locator('.reaction-add-btn').click();
    // emoji-mart renders inside a web component / shadow-dom like structure.
    // The popover div is .emoji-picker-popover. We need to wait for it to render.
    const picker = this.page.locator('.emoji-picker-popover');
    await picker.waitFor({ timeout: 5_000 });
    // Wait a moment for emoji-mart to fully render its buttons
    await this.page.waitForTimeout(500);
    // emoji-mart uses <button> elements with aria-label containing the emoji name
    // or the emoji character as text content.
    const emojiBtn = picker.locator(`button:has-text("${emojiChar}")`).first();
    const found = await emojiBtn.waitFor({ timeout: 3_000 }).then(() => true).catch(() => false);
    if (found) {
      await emojiBtn.click({ force: true });
    } else {
      // Fallback: search for emoji by aria-label, or click any available emoji
      const anyEmoji = picker.locator('button[aria-label]').first();
      await anyEmoji.waitFor({ timeout: 3_000 });
      await anyEmoji.click({ force: true });
    }
  }

  async removeReaction(msgText, emoji) {
    const msg = this.page.locator(`.msg:has-text("${msgText}")`).first();
    await msg.locator(`.reaction-chip:has-text("${emoji}")`).first().click();
  }

  async clearHistory() {
    await this.page.click('[data-testid="clear-room-history"]');
    await this.page.click('[data-testid="clear-room-yes"]');
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
    await this.page.fill('.search-modal-input', query);
    await this.page.waitForTimeout(500);
  }

  async getSearchResults() {
    return this.page.locator('.search-result-item');
  }

  async clickSearchResult(index) {
    await this.page.locator('.search-result-item').nth(index).click();
  }

  // ── User list (admin actions) ──
  async openUserContextMenu(username) {
    // Try the ⋮ button first (more reliable than right-click since it's always visible for admins)
    const menuBtn = this.page.locator(`.user-item:has-text("${username}") .user-item-menu-btn`);
    const hasMenuBtn = await menuBtn.waitFor({ timeout: 5_000 }).then(() => true).catch(() => false);
    if (hasMenuBtn) {
      await menuBtn.click();
    } else {
      // Fallback to right-click
      await this.page.locator(`.user-item:has-text("${username}")`).click({ button: 'right' });
    }
    // Wait for context menu to appear
    await this.page.locator('.context-menu').waitFor({ timeout: 5_000 });
  }

  async clickContextMenuItem(text) {
    await this.page.locator(`.context-menu-item:has-text("${text}")`).click();
  }

  async muteUser(username) {
    await this.openUserContextMenu(username);
    await this.clickContextMenuItem('Mute');
  }

  async kickUser(username) {
    await this.openUserContextMenu(username);
    await this.clickContextMenuItem('Kick');
  }

  async promoteUser(username) {
    await this.openUserContextMenu(username);
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
    // First check if there's a PM item in the sidebar (existing conversation)
    const pmItem = this.page.locator(`.pm-item:has-text("${username}")`);
    const hasPmItem = await pmItem.isVisible({ timeout: 2_000 }).catch(() => false);
    if (hasPmItem) {
      await pmItem.click();
      return;
    }
    // Otherwise click the user in the user list to initiate a PM
    const userItem = this.page.locator(`.user-item:has-text("${username}")`);
    await userItem.waitFor({ timeout: 10_000 });
    await userItem.click();
  }

  async getPMOfflineBanner() {
    return this.page.locator('.pm-offline-banner');
  }

  async deletePMConversation(username) {
    const pm = this.page.locator(`.pm-item:has-text("${username}")`);
    await pm.hover();
    await pm.locator('.pm-close-btn').click();
  }

  async clearPMHistory() {
    await this.page.click('[data-testid="clear-pm-history"]');
    await this.page.click('[data-testid="clear-pm-yes"]');
  }

  // ── Toast ──
  async getToast() {
    return this.page.locator('[data-testid="toast-card"]').first();
  }

  async waitForToast(text) {
    await this.page.locator(`[data-testid="toast-card"]:has-text("${text}")`).waitFor({ timeout: 5000 });
  }
}

module.exports = { ChatPage };
