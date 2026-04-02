# E2E UI Testing with Playwright — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 47 Playwright browser-based e2e UI tests with visual regression, running in isolated Docker/K8s environments via the existing lifecycle pattern.

**Architecture:** Page Object pattern in `fixtures/`, 12 spec files in `tests/`, global setup project registers users via API and saves tokens. Tests inject sessionStorage via `addInitScript` with hostname guard. Two-browser tests use `browser.newContext()`.

**Tech Stack:** Playwright (`@playwright/test`), Chromium, Node.js, `pyotp` (for 2FA TOTP generation in setup)

---

## File Map

### Create
| File | Purpose |
|------|---------|
| `tests/e2e-ui/package.json` | Dependencies: `@playwright/test`, `pyotp` shell calls |
| `tests/e2e-ui/playwright.config.js` | Playwright config (projects, browsers, snapshots) |
| `tests/e2e-ui/.gitignore` | Ignore `test-results/`, `playwright/.auth/`, `node_modules/` |
| `tests/e2e-ui/global.setup.js` | Register test users via API, save tokens to JSON |
| `tests/e2e-ui/fixtures/test-data.js` | Shared constants (users, rooms, file paths) |
| `tests/e2e-ui/fixtures/auth.js` | AuthPage page object |
| `tests/e2e-ui/fixtures/chat.js` | ChatPage page object |
| `tests/e2e-ui/fixtures/admin.js` | AdminPage page object |
| `tests/e2e-ui/fixtures/settings.js` | SettingsPage page object |
| `tests/e2e-ui/fixtures/helpers.js` | Shared helpers (fast login, two-browser setup, refresh-and-verify) |
| `tests/e2e-ui/fixtures/test-file.txt` | Small text file for upload tests |
| `tests/e2e-ui/fixtures/test-image.png` | Small PNG for image upload tests |
| `tests/e2e-ui/tests/auth.spec.js` | Tests 1-8 (auth flows) |
| `tests/e2e-ui/tests/chat-messaging.spec.js` | Tests 9-17 (messages, reactions, search, markdown, links) |
| `tests/e2e-ui/tests/chat-sidebar.spec.js` | Tests 18-20 (exit room, unread, divider) |
| `tests/e2e-ui/tests/files.spec.js` | Tests 21-23 (upload, download, PM files) |
| `tests/e2e-ui/tests/pm.spec.js` | Tests 24-28 (PM flows, room closed toast) |
| `tests/e2e-ui/tests/admin.spec.js` | Tests 29-34 (admin panel) |
| `tests/e2e-ui/tests/settings.spec.js` | Tests 35-38 (password, email, 2FA) |
| `tests/e2e-ui/tests/presence-rooms.spec.js` | Tests 39-42 (room presence) |
| `tests/e2e-ui/tests/presence-pm.spec.js` | Tests 43-44 (PM presence) |
| `tests/e2e-ui/tests/connection.spec.js` | Test 45 (disconnect/reconnect) |
| `tests/e2e-ui/tests/pm-typing.spec.js` | Test 46 (PM typing indicator) |
| `tests/e2e-ui/tests/visual-regression.spec.js` | Test 47 (page screenshots) |
| `.github/workflows/e2e-ui.yml` | CI workflow for UI e2e |

### Modify
| File | Change |
|------|--------|
| `Makefile` | Add `e2e-ui-docker`, `e2e-ui-k8s`, `e2e-ui-run` targets |
| `infra/scripts/e2e-lifecycle.sh` | Add `--ui` flag to switch test runner to Playwright |
| `docs/operations/makefile-reference.md` | Add Section 10: E2E UI Tests |
| `.gitignore` | Add `tests/e2e-ui/test-results/`, `tests/e2e-ui/playwright/.auth/` |

---

## Task 1: Project Scaffolding & Config

**Files:**
- Create: `tests/e2e-ui/package.json`
- Create: `tests/e2e-ui/playwright.config.js`
- Create: `tests/e2e-ui/.gitignore`
- Modify: `.gitignore`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "chatbox-e2e-ui",
  "private": true,
  "scripts": {
    "test": "npx playwright test",
    "test:headed": "npx playwright test --headed",
    "test:debug": "npx playwright test --debug",
    "update-snapshots": "npx playwright test --update-snapshots"
  },
  "devDependencies": {
    "@playwright/test": "^1.52.0"
  }
}
```

- [ ] **Step 2: Create playwright.config.js**

```js
// @ts-check
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 1,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],

  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,
    },
  },

  snapshotPathTemplate: '{testDir}/../snapshots/{arg}{ext}',

  projects: [
    {
      name: 'setup',
      testMatch: /global\.setup\.js/,
    },
    {
      name: 'e2e',
      dependencies: ['setup'],
      use: {
        baseURL: process.env.BASE_URL || 'http://localhost:8090',
        browserName: 'chromium',
        headless: true,
        screenshot: 'only-on-failure',
        video: 'retain-on-failure',
        trace: 'retain-on-failure',
        actionTimeout: 10_000,
        navigationTimeout: 15_000,
      },
    },
  ],
});
```

- [ ] **Step 3: Create .gitignore**

```
node_modules/
test-results/
playwright-report/
playwright/.auth/
```

- [ ] **Step 4: Add entries to root .gitignore**

Append to `/home/ido/Desktop/Chat-Project-Final/.gitignore`:
```
# Playwright UI e2e
tests/e2e-ui/node_modules/
tests/e2e-ui/test-results/
tests/e2e-ui/playwright-report/
tests/e2e-ui/playwright/.auth/
```

- [ ] **Step 5: Install dependencies and Playwright browsers**

```bash
cd tests/e2e-ui && npm install && npx playwright install chromium
```

- [ ] **Step 6: Commit**

```bash
git add tests/e2e-ui/package.json tests/e2e-ui/playwright.config.js tests/e2e-ui/.gitignore .gitignore tests/e2e-ui/package-lock.json
git commit -m "feat(e2e-ui): scaffold Playwright project with config"
```

---

## Task 2: Test Data & Fixtures (Helpers)

**Files:**
- Create: `tests/e2e-ui/fixtures/test-data.js`
- Create: `tests/e2e-ui/fixtures/helpers.js`
- Create: `tests/e2e-ui/fixtures/test-file.txt`
- Create: `tests/e2e-ui/fixtures/test-image.png`

- [ ] **Step 1: Create test-data.js**

```js
// Shared constants for all UI e2e tests.
// Usernames are suffixed with _ui to avoid collision with API e2e users.

const ADMIN = {
  username: process.env.ADMIN_USERNAME || 'admin',
  password: process.env.ADMIN_PASSWORD || 'changeme',
};

const USER_A = { username: 'alice_ui', email: 'alice_ui@test.com', password: 'Test1234!' };
const USER_B = { username: 'bob_ui', email: 'bob_ui@test.com', password: 'Test1234!' };
const USER_C = { username: 'charlie_ui', email: 'charlie_ui@test.com', password: 'Test1234!' };
const USER_D = { username: 'delta_ui', email: 'delta_ui@test.com', password: 'Test1234!' };
const USER_E = { username: 'echo_ui', email: 'echo_ui@test.com', password: 'Test1234!' };

const TEST_ROOM = 'ui-test-room';
const TEST_FILE = 'fixtures/test-file.txt';
const TEST_IMAGE = 'fixtures/test-image.png';

module.exports = { ADMIN, USER_A, USER_B, USER_C, USER_D, USER_E, TEST_ROOM, TEST_FILE, TEST_IMAGE };
```

- [ ] **Step 2: Create helpers.js**

```js
const fs = require('fs');
const path = require('path');

const TOKENS_PATH = path.join(__dirname, '..', 'playwright', '.auth', 'tokens.json');

function loadTokens() {
  return JSON.parse(fs.readFileSync(TOKENS_PATH, 'utf-8'));
}

/**
 * Fast login — inject sessionStorage token via addInitScript.
 * Only auth.spec.js uses the real login UI; everything else uses this.
 */
async function fastLogin(context, page, userKey) {
  const tokens = loadTokens();
  const { token, user } = tokens[userKey];
  await context.addInitScript(({ token, user }) => {
    if (window.location.hostname !== '') {
      window.sessionStorage.setItem('token', token);
      window.sessionStorage.setItem('user', JSON.stringify(user));
    }
  }, { token, user });
  await page.goto('/chat');
  await page.waitForSelector('.chat-page, .room-list-panel', { timeout: 10_000 });
}

/**
 * Create a two-browser setup for multi-user tests.
 * Returns { pageA, pageB, ctxA, ctxB } with each user logged in.
 */
async function twoBrowsers(browser, userKeyA, userKeyB) {
  const tokens = loadTokens();

  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();

  const tokenA = tokens[userKeyA];
  const tokenB = tokens[userKeyB];

  await ctxA.addInitScript(({ token, user }) => {
    if (window.location.hostname !== '') {
      window.sessionStorage.setItem('token', token);
      window.sessionStorage.setItem('user', JSON.stringify(user));
    }
  }, { token: tokenA.token, user: tokenA.user });

  await ctxB.addInitScript(({ token, user }) => {
    if (window.location.hostname !== '') {
      window.sessionStorage.setItem('token', token);
      window.sessionStorage.setItem('user', JSON.stringify(user));
    }
  }, { token: tokenB.token, user: tokenB.user });

  const pageA = await ctxA.newPage();
  const pageB = await ctxB.newPage();

  return { pageA, pageB, ctxA, ctxB };
}

/**
 * Refresh the page and wait for the app to reload.
 */
async function refreshAndWait(page) {
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('.chat-page, .room-list-panel, .login-page, .settings-page, .admin-page', { timeout: 10_000 });
}

module.exports = { loadTokens, fastLogin, twoBrowsers, refreshAndWait };
```

- [ ] **Step 3: Create test files for upload tests**

```bash
echo "This is a test file for e2e upload testing." > tests/e2e-ui/fixtures/test-file.txt
```

For the test image, create a minimal 1x1 red PNG (base64 decoded):
```bash
echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg==" | base64 -d > tests/e2e-ui/fixtures/test-image.png
```

- [ ] **Step 4: Commit**

```bash
git add tests/e2e-ui/fixtures/
git commit -m "feat(e2e-ui): add test data, helpers, and test files"
```

---

## Task 3: Global Setup (User Registration)

**Files:**
- Create: `tests/e2e-ui/global.setup.js`

- [ ] **Step 1: Create global.setup.js**

```js
const { test } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const { ADMIN, USER_A, USER_B, USER_C, USER_D, USER_E, TEST_ROOM } = require('./fixtures/test-data');

const TOKENS_DIR = path.join(__dirname, 'playwright', '.auth');
const TOKENS_PATH = path.join(TOKENS_DIR, 'tokens.json');

async function registerAndLogin(baseURL, user) {
  // Register (ignore 409 — already exists)
  const regBody = { username: user.username, password: user.password };
  if (user.email) regBody.email = user.email;

  let retries = 5;
  while (retries > 0) {
    const regRes = await fetch(`${baseURL}/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(regBody),
    });
    if (regRes.status === 429) {
      retries--;
      await new Promise(r => setTimeout(r, 15_000));
      continue;
    }
    break;
  }

  // Login
  let loginRes;
  retries = 5;
  while (retries > 0) {
    loginRes = await fetch(`${baseURL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user.username, password: user.password }),
    });
    if (loginRes.status === 429) {
      retries--;
      await new Promise(r => setTimeout(r, 15_000));
      continue;
    }
    break;
  }

  const data = await loginRes.json();
  return {
    token: data.token,
    user: { username: user.username, user_id: data.user_id, is_global_admin: data.is_global_admin || false },
  };
}

test('register all test users and save tokens', async () => {
  const baseURL = process.env.BASE_URL || 'http://localhost:8090';

  const tokens = {};

  // Admin login (already exists in the system)
  tokens.admin = await registerAndLogin(baseURL, ADMIN);

  // Register test users
  tokens.userA = await registerAndLogin(baseURL, USER_A);
  tokens.userB = await registerAndLogin(baseURL, USER_B);
  tokens.userC = await registerAndLogin(baseURL, USER_C);
  tokens.userD = await registerAndLogin(baseURL, USER_D);
  tokens.userE = await registerAndLogin(baseURL, USER_E);

  // Create test room (admin only)
  await fetch(`${baseURL}/rooms`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${tokens.admin.token}`,
    },
    body: JSON.stringify({ name: TEST_ROOM }),
  });

  // Save tokens
  fs.mkdirSync(TOKENS_DIR, { recursive: true });
  fs.writeFileSync(TOKENS_PATH, JSON.stringify(tokens, null, 2));
});
```

- [ ] **Step 2: Verify setup runs**

```bash
cd tests/e2e-ui && npx playwright test --project=setup
```

Expected: PASS — tokens.json created at `playwright/.auth/tokens.json`

- [ ] **Step 3: Commit**

```bash
git add tests/e2e-ui/global.setup.js
git commit -m "feat(e2e-ui): add global setup — register users and save tokens"
```

---

## Task 4: Page Objects

**Files:**
- Create: `tests/e2e-ui/fixtures/auth.js`
- Create: `tests/e2e-ui/fixtures/chat.js`
- Create: `tests/e2e-ui/fixtures/admin.js`
- Create: `tests/e2e-ui/fixtures/settings.js`

- [ ] **Step 1: Create auth.js page object**

```js
class AuthPage {
  constructor(page) {
    this.page = page;
  }

  async goto() {
    await this.page.goto('/login');
    await this.page.waitForSelector('.login-card');
  }

  async switchToRegister() {
    await this.page.click('text=Register');
  }

  async switchToLogin() {
    await this.page.click('text=Sign In');
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
```

- [ ] **Step 2: Create chat.js page object**

```js
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
    await this.page.waitForTimeout(500); // debounce
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
```

- [ ] **Step 3: Create admin.js page object**

```js
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

  async confirmResetDatabase() {
    this.page.once('dialog', dialog => dialog.accept());
    await this.page.click('button:has-text("Reset Database")');
  }

  async getStatus() {
    return this.page.locator('.admin-status').textContent();
  }
}

module.exports = { AdminPage };
```

- [ ] **Step 4: Create settings.js page object**

```js
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
```

- [ ] **Step 5: Commit**

```bash
git add tests/e2e-ui/fixtures/auth.js tests/e2e-ui/fixtures/chat.js tests/e2e-ui/fixtures/admin.js tests/e2e-ui/fixtures/settings.js
git commit -m "feat(e2e-ui): add page object fixtures for all pages"
```

---

## Task 5: Auth Spec (Tests 1-8)

**Files:**
- Create: `tests/e2e-ui/tests/auth.spec.js`

- [ ] **Step 1: Write auth.spec.js**

This is the only spec that uses the real login UI (no fast-login). All 8 auth tests go in this file. Each test creates a fresh browser context.

Tests to implement:
1. `register and land on chat` — fill register form with unique username → redirects to /chat → refresh → still on /chat
2. `duplicate email error` — register with existing email → error message visible
3. `wrong password error with shake` — login with wrong password → error text + shake class on card
4. `login with 2FA` — login user that has 2FA enabled → TOTP screen appears → enter valid code → lands on /chat (requires enabling 2FA via API in test setup)
5. `wrong 2FA code` — enter invalid 6-digit code → error message, still on 2FA screen
6. `logout redirects to login` — login → logout → on /login → goto /chat → redirected back to /login
7. `forgot password flow` — click forgot → fill email → success message → click back → login form
8. `password visibility toggle` — click eye icon → input type changes to text → click again → back to password

- [ ] **Step 2: Run auth spec against running environment**

```bash
cd tests/e2e-ui && npx playwright test tests/auth.spec.js --headed
```

- [ ] **Step 3: Fix any selector mismatches**

Page objects use generic selectors that may need tuning to match actual DOM. Update `fixtures/auth.js` selectors as needed.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e-ui/tests/auth.spec.js tests/e2e-ui/fixtures/auth.js
git commit -m "feat(e2e-ui): add auth spec — tests 1-8"
```

---

## Task 6: Chat Messaging Spec (Tests 9-17)

**Files:**
- Create: `tests/e2e-ui/tests/chat-messaging.spec.js`

Tests to implement (use `fastLogin` for all):
9. `send message and survives refresh` — join room → send → visible → refresh → still there
10. `edit message shows edited badge` — send → edit → new text + "(edited)" visible → refresh → persists
11. `delete message shows deleted text` — send → delete → "[deleted]" visible → refresh → persists
12. `add and remove reaction` — send → add reaction (picker) → badge visible → remove (click chip) → gone → refresh → state persists
13. `clear message history with confirmation` — send messages → clear (confirm Yes) → empty → refresh → still empty
14. `typing indicator` — two browsers: A types → B sees typing indicator (use `twoBrowsers`)
15. `search messages with keyboard nav` — send known message → Ctrl+K → search → arrow keys → Enter → scrolls to message with highlight
16. `markdown rendering` — send `**bold** and \`code\`` → check rendered HTML has `<strong>` and `<code>` tags
17. `link preview` — send message with URL → wait for preview card → refresh → still rendered

- [ ] **Step 1: Write chat-messaging.spec.js**
- [ ] **Step 2: Run and fix selectors**
- [ ] **Step 3: Commit**

```bash
git add tests/e2e-ui/tests/chat-messaging.spec.js tests/e2e-ui/fixtures/chat.js
git commit -m "feat(e2e-ui): add chat messaging spec — tests 9-17"
```

---

## Task 7: Chat Sidebar Spec (Tests 18-20)

**Files:**
- Create: `tests/e2e-ui/tests/chat-sidebar.spec.js`

Tests (18-20):
18. `exit room and rejoin` — join room → click × → removed from joined → visible in available → click Join → back in joined
19. `unread badges` — two browsers: B sends message while A in different room → badge on room → A clicks → badge clears
20. `new messages divider` — two browsers: B sends messages while A away → A switches back → "New messages" divider visible

- [ ] **Step 1: Write chat-sidebar.spec.js**
- [ ] **Step 2: Run and fix selectors**
- [ ] **Step 3: Commit**

```bash
git add tests/e2e-ui/tests/chat-sidebar.spec.js
git commit -m "feat(e2e-ui): add chat sidebar spec — tests 18-20"
```

---

## Task 8: Files Spec (Tests 21-23)

**Files:**
- Create: `tests/e2e-ui/tests/files.spec.js`

Tests (21-23):
21. `upload file and download` — click upload → select test-file.txt → progress → file message visible → click download → refresh → still there
22. `upload image shows inline preview` — upload test-image.png → `<img>` visible in message → refresh → still visible
23. `upload file in PM` — two browsers: A uploads file in PM to B → B sees file message → B downloads

Note: Use `page.locator('input[type="file"]').setInputFiles()` — no native file dialog needed.

- [ ] **Step 1: Write files.spec.js**
- [ ] **Step 2: Run and fix selectors**
- [ ] **Step 3: Commit**

```bash
git add tests/e2e-ui/tests/files.spec.js
git commit -m "feat(e2e-ui): add files spec — tests 21-23"
```

---

## Task 9: PM Spec (Tests 24-28)

**Files:**
- Create: `tests/e2e-ui/tests/pm.spec.js`

Tests (24-28):
24. `PM send and receive` — two browsers: A clicks B in user list → sends PM → B sees it in PM list → B replies → A sees reply → refresh → persists
25. `PM edit and delete` — A sends PM → edits → "(edited)" visible → refresh → persists. Sends another → deletes → "[deleted]" → refresh → persists
26. `PM reaction` — A sends PM → adds reaction → badge visible → refresh → still there
27. `delete DM conversation` — A clicks × on PM conversation → removed from sidebar → refresh → still removed
28. `room closed toast` — two browsers: admin closes room that B is in → B sees "Room closed" toast → room removed from B's sidebar

- [ ] **Step 1: Write pm.spec.js**
- [ ] **Step 2: Run and fix selectors**
- [ ] **Step 3: Commit**

```bash
git add tests/e2e-ui/tests/pm.spec.js
git commit -m "feat(e2e-ui): add PM spec — tests 24-28"
```

---

## Task 10: Admin Spec (Tests 29-34)

**Files:**
- Create: `tests/e2e-ui/tests/admin.spec.js`

Tests (29-34):
29. `close and open room` — admin navigates to /admin → close room → status shows "Closed" → refresh → still closed → open → status "Open"
30. `mute and kick user` — two browsers: admin mutes B (context menu) → B sees muted banner, input hidden → admin kicks B → B gets toast, removed from room
31. `promote user to room admin` — admin promotes B → B sees "Admin" badge in user list → refresh → still admin
32. `create room` — admin types room name → click Create → room appears in list → another user can join
33. `reset database confirmation cancel` — admin clicks "Reset Database" → dialog appears → Cancel → nothing happens
34. `files table expand and download` — admin clicks Files on room → file list expands → name, sender, size visible → download button works

- [ ] **Step 1: Write admin.spec.js**
- [ ] **Step 2: Run and fix selectors**
- [ ] **Step 3: Commit**

```bash
git add tests/e2e-ui/tests/admin.spec.js
git commit -m "feat(e2e-ui): add admin spec — tests 29-34"
```

---

## Task 11: Settings Spec (Tests 35-38)

**Files:**
- Create: `tests/e2e-ui/tests/settings.spec.js`

Tests (35-38) — use dedicated users (USER_D, USER_E) to avoid breaking other tests:
35. `change password` — navigate to /settings → change password → success → logout → login with new password
36. `change email` — change email → success message → refresh → new email visible in profile
37. `enable 2FA` — click Enable → QR visible → click "Cannot scan" → manual key visible → generate TOTP code → verify → enabled → refresh → still enabled
38. `disable 2FA` — generate TOTP code → enter → disable → refresh → shows disabled state

Note: For TOTP code generation, call `node -e "..."` with a simple TOTP implementation, or use the API to get the secret and compute the code. The setup test for 2FA (test 37) gets the manual key from the UI, then uses it to generate codes.

- [ ] **Step 1: Write settings.spec.js**
- [ ] **Step 2: Run and fix selectors**
- [ ] **Step 3: Commit**

```bash
git add tests/e2e-ui/tests/settings.spec.js
git commit -m "feat(e2e-ui): add settings spec — tests 35-38"
```

---

## Task 12: Presence Rooms Spec (Tests 39-42)

**Files:**
- Create: `tests/e2e-ui/tests/presence-rooms.spec.js`

All tests use two browsers.

Tests (39-42):
39. `admin role survives logout and re-login` — A is room admin → A logs out → A logs back in → A still has admin badge in room
40. `logout immediate disappearance` — A and B in same room → A logs out → B sees A removed from user list immediately + system message styled as `.msg-system`
41. `refresh preserves state` — A and B in room, A is admin → A refreshes → B still sees A online, no leave/join messages, A still has admin badge
42. `leave shows offline` — A and B in room → A exits room → B sees A removed from user list

- [ ] **Step 1: Write presence-rooms.spec.js**
- [ ] **Step 2: Run and fix selectors**
- [ ] **Step 3: Commit**

```bash
git add tests/e2e-ui/tests/presence-rooms.spec.js
git commit -m "feat(e2e-ui): add presence rooms spec — tests 39-42"
```

---

## Task 13: Presence PM Spec (Tests 43-44)

**Files:**
- Create: `tests/e2e-ui/tests/presence-pm.spec.js`

Tests (43-44):
43. `PM refresh preserves state` — A and B in PM → A refreshes → B still sees A online in PM header
44. `PM logout shows offline` — A and B in PM → A logs out → B sees A's status change to "Offline" + offline banner appears

- [ ] **Step 1: Write presence-pm.spec.js**
- [ ] **Step 2: Run and fix selectors**
- [ ] **Step 3: Commit**

```bash
git add tests/e2e-ui/tests/presence-pm.spec.js
git commit -m "feat(e2e-ui): add presence PM spec — tests 43-44"
```

---

## Task 14: Connection & PM Typing Specs (Tests 45-46)

**Files:**
- Create: `tests/e2e-ui/tests/connection.spec.js`
- Create: `tests/e2e-ui/tests/pm-typing.spec.js`

Test 45 (connection): Simulate disconnect by blocking WebSocket via `page.route('**/ws/**', route => route.abort())` → "Reconnecting..." visible → unblock → indicator disappears

Test 46 (PM typing): Two browsers: A opens PM with B → A types in input → B sees typing indicator in PM view

- [ ] **Step 1: Write connection.spec.js and pm-typing.spec.js**
- [ ] **Step 2: Run and fix selectors**
- [ ] **Step 3: Commit**

```bash
git add tests/e2e-ui/tests/connection.spec.js tests/e2e-ui/tests/pm-typing.spec.js
git commit -m "feat(e2e-ui): add connection and PM typing specs — tests 45-46"
```

---

## Task 15: Visual Regression Spec (Test 47)

**Files:**
- Create: `tests/e2e-ui/tests/visual-regression.spec.js`

Test 47: Navigate each page in a known state and screenshot:
- Login page (sign-in tab) → `toHaveScreenshot('login-signin.png')`
- Login page (register tab, type weak password for strength meter) → `toHaveScreenshot('login-register.png')`
- Chat page (room selected, send a message with `@mention`) → `toHaveScreenshot('chat-room.png')`
- Chat page (no room selected — empty state) → `toHaveScreenshot('chat-empty.png')`
- PM view (active conversation) → `toHaveScreenshot('chat-pm.png')`
- Settings page → `toHaveScreenshot('settings.png')`
- Admin dashboard → `toHaveScreenshot('admin.png')`

- [ ] **Step 1: Write visual-regression.spec.js**
- [ ] **Step 2: Run with `--update-snapshots` to generate baselines**

```bash
cd tests/e2e-ui && npx playwright test tests/visual-regression.spec.js --update-snapshots
```

- [ ] **Step 3: Verify snapshot PNGs in `snapshots/`**
- [ ] **Step 4: Commit**

```bash
git add tests/e2e-ui/tests/visual-regression.spec.js tests/e2e-ui/snapshots/
git commit -m "feat(e2e-ui): add visual regression spec — test 47 with baseline snapshots"
```

---

## Task 16: Lifecycle & Makefile Integration

**Files:**
- Modify: `infra/scripts/e2e-lifecycle.sh`
- Modify: `Makefile`

- [ ] **Step 1: Add `--ui` and `--all` flags to e2e-lifecycle.sh**

After the `PYTEST_ARGS` parsing (line 18), add:

```bash
# Check for --ui or --all flags
TEST_MODE="api"
for arg in "${PYTEST_ARGS[@]}"; do
    case "$arg" in
        --ui)  TEST_MODE="ui"; PYTEST_ARGS=("${PYTEST_ARGS[@]/$arg}") ;;
        --all) TEST_MODE="all"; PYTEST_ARGS=("${PYTEST_ARGS[@]/$arg}") ;;
    esac
done
```

Modify the `run_tests()` function to handle both modes:

```bash
run_tests() {
    local kong_url="$1"

    if [ "$TEST_MODE" = "api" ] || [ "$TEST_MODE" = "all" ]; then
        step "Running API e2e tests against $kong_url..."
        KONG_URL="$kong_url" python3 -m pytest "$PROJECT_ROOT/tests/e2e/" \
            -v --tb=short -c "$PROJECT_ROOT/tests/e2e/pytest.ini" \
            "${PYTEST_ARGS[@]}" || EXIT_CODE=$?
    fi

    if [ "$TEST_MODE" = "ui" ] || [ "$TEST_MODE" = "all" ]; then
        step "Running UI e2e tests against $kong_url..."
        cd "$PROJECT_ROOT/tests/e2e-ui"
        npm ci --silent 2>/dev/null || npm install --silent
        npx playwright install chromium --with-deps 2>/dev/null
        BASE_URL="$kong_url" npx playwright test || EXIT_CODE=$?
        cd "$PROJECT_ROOT"
    fi

    if [ "$EXIT_CODE" -eq 0 ]; then
        success "All tests passed!"
    else
        fail "Tests failed (exit code $EXIT_CODE)"
    fi
}
```

- [ ] **Step 2: Add Makefile targets**

Append to the e2e section in `Makefile`:

```makefile
e2e-ui-setup: ## Install Playwright e2e dependencies
	cd tests/e2e-ui && npm install && npx playwright install chromium

e2e-ui-docker: ## Black box Docker Compose: up → run Playwright → down
	@bash $(E2E_LIFECYCLE) docker --ui

e2e-ui-k8s: ## Black box K8s: Kind cluster → deploy → Playwright → delete
	@bash $(E2E_LIFECYCLE) k8s --ui

e2e-ui-run: ## Run Playwright tests against already-running environment
	cd tests/e2e-ui && npx playwright test

e2e-ui-update-snapshots: ## Regenerate visual regression baselines
	cd tests/e2e-ui && npx playwright test tests/visual-regression.spec.js --update-snapshots
```

- [ ] **Step 3: Commit**

```bash
git add infra/scripts/e2e-lifecycle.sh Makefile
git commit -m "feat(e2e-ui): add lifecycle --ui flag and Makefile targets"
```

---

## Task 17: CI Workflow

**Files:**
- Create: `.github/workflows/e2e-ui.yml`

- [ ] **Step 1: Create e2e-ui.yml**

```yaml
name: E2E — UI (Playwright)

on:
  push:
    branches: [main]
    paths:
      - "frontend/**"
      - "tests/e2e-ui/**"
      - ".github/workflows/e2e-ui.yml"
  pull_request:
    branches: [main]
    paths:
      - "frontend/**"
      - "tests/e2e-ui/**"
      - ".github/workflows/e2e-ui.yml"

concurrency:
  group: e2e-ui-${{ github.ref }}
  cancel-in-progress: true

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"

jobs:
  e2e-ui:
    name: E2E UI (Playwright)
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Create .env for CI
        run: |
          TOTP_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
          cat > .env <<EOF
          APP_ENV=dev
          POSTGRES_PASSWORD=chatbox_pass
          REDIS_PASSWORD=chatbox_redis_pass
          SECRET_KEY=ci-test-secret-key-not-for-production
          ADMIN_USERNAME=admin
          ADMIN_PASSWORD=changeme
          CORS_ORIGINS=http://localhost:3000,http://localhost:5173
          TOTP_ENCRYPTION_KEY=${TOTP_KEY}
          VITE_API_BASE=http://localhost:8090
          VITE_WS_BASE=ws://localhost:8090
          EOF

      - name: Start e2e environment
        run: |
          docker compose -p chatbox-e2e \
            -f docker-compose.yml \
            -f docker-compose.e2e.yml \
            up -d --build --quiet-pull

      - name: Wait for services to be healthy
        run: |
          echo "Waiting for Kong on port 8090..."
          timeout=120
          elapsed=0
          while ! curl -sf http://localhost:8090 > /dev/null 2>&1; do
            if [ "$elapsed" -ge "$timeout" ]; then
              echo "Timed out waiting for Kong"
              docker compose -p chatbox-e2e -f docker-compose.yml -f docker-compose.e2e.yml logs
              exit 1
            fi
            sleep 3
            elapsed=$((elapsed + 3))
          done
          echo "Kong responding on port 8090"

      - name: Install Playwright
        run: |
          cd tests/e2e-ui
          npm ci
          npx playwright install chromium --with-deps

      - name: Run Playwright tests
        env:
          BASE_URL: http://localhost:8090
          ADMIN_USERNAME: admin
          ADMIN_PASSWORD: changeme
        run: |
          cd tests/e2e-ui && npx playwright test

      - name: Upload test artifacts
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: |
            tests/e2e-ui/test-results/
            tests/e2e-ui/playwright-report/
          retention-days: 7

      - name: Dump service logs
        if: always()
        run: |
          mkdir -p tests/e2e-ui/logs
          for svc in auth-service chat-service message-service file-service kong frontend; do
            docker compose -p chatbox-e2e \
              -f docker-compose.yml \
              -f docker-compose.e2e.yml \
              logs "$svc" > "tests/e2e-ui/logs/$svc.log" 2>&1 || true
          done

      - name: Tear down environment
        if: always()
        run: |
          docker compose -p chatbox-e2e \
            -f docker-compose.yml \
            -f docker-compose.e2e.yml \
            down -v --remove-orphans
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/e2e-ui.yml
git commit -m "ci: add Playwright UI e2e workflow"
```

---

## Task 18: Documentation

**Files:**
- Modify: `docs/operations/makefile-reference.md`

- [ ] **Step 1: Add Section 10 to makefile-reference.md**

Append after Section 9:

```markdown
## 10. E2E UI Tests (Playwright)

Browser-based e2e tests using Playwright that validate the actual UI — rendering, user interactions, navigation, and visual regression. Complements the API e2e tests (Section 9) which validate backend logic.

### Quick Start

```bash
# 1. Install Playwright and Chromium (one time)
make e2e-ui-setup

# 2. Run all UI tests in an isolated Docker Compose environment
make e2e-ui-docker
# This does: build → start → wait → Playwright tests → dump logs → tear down
```

### How It Works

Same black-box lifecycle as API e2e tests:

1. **Spin up** clean Docker Compose or Kind cluster
2. **Wait** for services
3. **Run** Playwright test suite (47 tests, Chromium, headless)
4. **Dump** logs on failure
5. **Tear down** everything

### All Targets

| Target | Description |
|--------|-------------|
| `make e2e-ui-setup` | Install Playwright + Chromium browser (one time) |
| `make e2e-ui-docker` | Black box Docker Compose → Playwright → tear down (~3-5 min) |
| `make e2e-ui-k8s` | Black box Kind cluster → Playwright → delete (~15 min) |
| `make e2e-ui-run` | Run Playwright against already-running environment |
| `make e2e-ui-update-snapshots` | Regenerate visual regression baseline images |

### Test Categories

| Spec File | Tests | Description |
|-----------|-------|-------------|
| `auth.spec.js` | 8 | Register, login, 2FA, logout, forgot password |
| `chat-messaging.spec.js` | 9 | Send, edit, delete, reactions, search, markdown, links |
| `chat-sidebar.spec.js` | 3 | Exit room, unread badges, new messages divider |
| `files.spec.js` | 3 | Upload, download, PM files, image preview |
| `pm.spec.js` | 5 | PM send/receive, edit/delete, reactions, room closed toast |
| `admin.spec.js` | 6 | Close/open rooms, mute/kick, promote, create room |
| `settings.spec.js` | 4 | Password, email, enable/disable 2FA |
| `presence-rooms.spec.js` | 4 | Admin role, logout/refresh presence, leave offline |
| `presence-pm.spec.js` | 2 | PM refresh/logout presence |
| `connection.spec.js` | 1 | WebSocket disconnect/reconnect indicator |
| `pm-typing.spec.js` | 1 | PM typing indicator |
| `visual-regression.spec.js` | 1 | Full-page screenshots of all 5 pages |

### Visual Regression

Baseline screenshots are committed to `tests/e2e-ui/snapshots/`. After an intentional UI change:

```bash
# Regenerate baselines
make e2e-ui-update-snapshots

# Review diffs, then commit
git add tests/e2e-ui/snapshots/
git commit -m "update visual regression baselines after [change]"
```

GitHub renders image diffs in PRs so reviewers can see exactly what changed.

### Running Against Your Dev Environment

If your dev environment is already running:

```bash
# Point Playwright at your dev Kong
BASE_URL=http://localhost:80 make e2e-ui-run
```

### Debugging Failed Tests

On failure, Playwright saves screenshots, video, and traces to `tests/e2e-ui/test-results/`. Open the HTML report:

```bash
cd tests/e2e-ui && npx playwright show-report
```

### CI

The UI e2e tests run automatically via `.github/workflows/e2e-ui.yml` on every PR and push to main that changes `frontend/**` or `tests/e2e-ui/**`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/operations/makefile-reference.md
git commit -m "docs: add Section 10 — E2E UI Tests (Playwright)"
```

---

## Task 19: Branch, Push, and PR

- [ ] **Step 1: Create branch from main**

```bash
git checkout main && git pull
git checkout -b feat/e2e-ui-playwright
```

- [ ] **Step 2: Cherry-pick or recommit all work onto the branch**
- [ ] **Step 3: Push and create PR**

```bash
git push -u origin feat/e2e-ui-playwright
gh pr create --title "feat: add Playwright e2e UI tests (47 tests)" --body "..."
```

---

## Task 20: Run E2E UI Tests Locally

- [ ] **Step 1: Start the Docker Compose e2e environment**

```bash
make e2e-ui-docker
```

Or if environment is already running:

```bash
make e2e-ui-run
```

- [ ] **Step 2: Fix any failing tests**

Iterate: run → fix selectors/assertions → re-run until all 47 pass.

- [ ] **Step 3: Generate visual regression baselines**

```bash
make e2e-ui-update-snapshots
```

- [ ] **Step 4: Final commit and push**

```bash
git add -A && git commit -m "fix(e2e-ui): stabilize all tests and update snapshots"
git push
```
