# E2E UI Testing with Playwright — Design Spec

**Date:** 2026-04-02
**Status:** Approved

## Goal

Add browser-based e2e UI tests using Playwright to complement the existing 86-test API e2e suite. The API tests validate backend logic; the UI tests validate what users actually see and interact with — rendering, navigation, visual feedback, and CSS regressions.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Test location | `tests/e2e-ui/` | Sibling to `tests/e2e/`, clear separation |
| Browser | Chromium only | 95% coverage, fast CI, single snapshot baseline |
| Snapshot storage | Committed to git | ~1-2MB, reviewable in PR diffs |
| Environment | Separate lifecycle (`e2e-ui-docker`, `e2e-ui-k8s`) | Independent from API e2e, same black-box pattern |
| CI workflow | `.github/workflows/e2e-ui.yml` | Triggers on frontend path changes only |
| Visual regression | `toHaveScreenshot()` with 1% pixel tolerance | Catches CSS/layout regressions, animations disabled |

## Test Coverage — 47 Tests

### 1. Authentication & Login (8 tests)
1. Register (with email + password strength meter) → land on chat → refresh → still logged in
2. Register with duplicate email → error shown
3. Login with wrong password → error + shake animation
4. Login with 2FA → TOTP prompt → enter code → land on chat
5. Login with wrong 2FA code → error message, stays on 2FA screen
6. Logout → redirect to /login → protected route blocked
7. Forgot password → enter email → generic success message → back to login
8. Password visibility toggle → click eye → text shown → click again → hidden

### 2. Chat Rooms — Messaging (9 tests)
9. Join room → send message → appears in list → refresh → still there
10. Edit message → text updated + "(edited)" badge → refresh → persists
11. Delete message → "[deleted]" text shown → refresh → persists
12. Add reaction (picker flow) + remove reaction (re-click) → refresh → persists
13. Clear message history (confirm dialog) → messages gone → refresh → still cleared
14. Typing indicator — User A types → User B sees "typing..." (two browsers)
15. Search (Ctrl+K) → results + PM results → keyboard nav → click → scroll to message + highlight
16. Send markdown (**bold**, `code`, list) → renders as formatted HTML
17. Send URL → link preview card appears → refresh → still renders

### 3. Chat Rooms — Sidebar & Navigation (3 tests)
18. Exit room (click x) → removed from sidebar → appears in "Available" → can rejoin
19. Unread badges — message arrives while in different room → badge appears → click room → clears (two browsers)
20. New messages divider — messages arrive while away → switch back → divider visible (two browsers)

### 4. File Upload & Download (3 tests)
21. Upload file → progress bar → file message + download link → click download → refresh → still there
22. Upload image → inline preview renders → refresh → still visible
23. Upload file in PM → both users see it → download works (two browsers)

### 5. Private Messages (5 tests)
24. Click user → start PM → send → other user sees → replies → refresh → persists (two browsers)
25. Edit PM → "(edited)" badge → refresh → persists. Delete PM → "[deleted]" → refresh → persists
26. Add reaction to PM → badge → refresh → still there
27. Delete DM conversation (click x) → removed from sidebar → refresh → still removed
28. Admin closes room user is in → toast "Room closed" → room removed from sidebar (two browsers)

### 6. Admin Panel (6 tests)
29. Close room → status changes → refresh → still closed. Open room → restored.
30. Mute user (context menu) → muted banner replaces input + toast → kick → toast + removed (two browsers)
31. Promote user to room admin → admin badge → refresh → still admin
32. Create new room → appears in room list → joinable
33. Reset database confirmation → click → confirm dialog → Cancel → nothing happens
34. Files table — expand room files → see name/sender/size → download works

### 7. Settings (4 tests)
35. Change password → success → logout → login with new password
36. Change email → success → refresh → new email shown
37. Enable 2FA → QR + manual key → enter TOTP → enabled → refresh → still enabled
38. Disable 2FA → enter code → disabled → refresh → still disabled

### 8. User Presence & Session — Rooms (4 tests)
39. Room admin logout → re-login → still admin (admin badge visible) (two browsers)
40. User logout → disappears immediately from online list + system message styled differently (two browsers)
41. User in room → refresh → still in room, online, admin preserved, no leave/join system messages (two browsers)
42. User leaves room → offline in that room's user list (two browsers)

### 9. User Presence & Session — PMs (2 tests)
43. Refresh during PM → still in PM, status online for other user (two browsers)
44. Logout during PM → disappears, status offline, offline banner appears (two browsers)

### 10. Connection & Resilience (1 test)
45. WebSocket disconnect → "Reconnecting..." indicator → reconnect → indicator gone → messages resume

### 11. PM Typing (1 test)
46. User A types in PM → User B sees typing indicator (two browsers)

### 12. Visual Regression (1 test)
47. Full-page screenshots: Login (both tabs), Chat (room + empty state + @mention), PM view, Settings, Admin dashboard

## Architecture

### Project Structure
```
tests/e2e-ui/
├── playwright.config.js
├── package.json
├── global.setup.js              # Registers users via API, saves tokens
├── fixtures/
│   ├── auth.js                  # AuthPage page object
│   ├── chat.js                  # ChatPage page object
│   ├── admin.js                 # AdminPage page object
│   ├── settings.js              # SettingsPage page object
│   └── test-data.js             # Users, rooms, file paths
├── tests/
│   ├── auth.spec.js
│   ├── chat-messaging.spec.js
│   ├── chat-sidebar.spec.js
│   ├── files.spec.js
│   ├── pm.spec.js
│   ├── admin.spec.js
│   ├── settings.spec.js
│   ├── presence-rooms.spec.js
│   ├── presence-pm.spec.js
│   ├── connection.spec.js
│   ├── pm-typing.spec.js
│   └── visual-regression.spec.js
├── snapshots/                   # Committed baseline PNGs
└── test-results/                # Gitignored
```

### Playwright Config
- Chromium only, headless
- `workers: 1` — tests share server state
- `retries: 1` — WebSocket tests can be flaky
- `BASE_URL` from env (defaults to `http://localhost:8090`)
- Screenshots/video/trace on failure only
- `maxDiffPixelRatio: 0.01`, `animations: 'disabled'`

### Project Dependencies (Execution Order)
```js
projects: [
  { name: 'setup', testMatch: '**/global.setup.js' },
  { name: 'e2e', dependencies: ['setup'], testMatch: '**/*.spec.js' },
]
```

### Authentication Strategy
- `global.setup.js` registers all test users via API (fetch), saves tokens to `playwright/.auth/tokens.json`
- All specs (except `auth.spec.js`) use `context.addInitScript()` to inject sessionStorage with hostname guard:
```js
await context.addInitScript(({ token, user }) => {
  if (window.location.hostname === 'localhost') {
    sessionStorage.setItem('token', token);
    sessionStorage.setItem('user', JSON.stringify(user));
  }
}, { token, user });
```
- Only `auth.spec.js` tests the actual login UI flow

### Page Objects
- `AuthPage` — register, login, loginWith2FA, logout, forgotPassword, togglePasswordVisibility, getErrorMessage, getPasswordStrength
- `ChatPage` — joinRoom, exitRoom, sendMessage, editMessage, deleteMessage, addReaction, removeReaction, clearHistory, uploadFile, openSearch, rightClickUser, muteUser, kickUser, getOnlineUsers, getMutedBanner, getTypingIndicator, getUnreadBadge, getNewMessagesDivider
- `AdminPage` — createRoom, closeRoom, openRoom, promoteUser, expandFiles, downloadFile, clickResetDatabase
- `SettingsPage` — changePassword, changeEmail, enable2FA, disable2FA, getManualKey, getStatusMessage

### Two-Browser Tests (~16 tests)
Use `browser.newContext()` for isolated sessions:
```js
test('typing indicator', async ({ browser }) => {
  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();
  const pageA = await ctxA.newPage();
  const pageB = await ctxB.newPage();
  // inject auth for each, interact, assert
});
```

### Lifecycle & CI
- Makefile: `e2e-ui-docker`, `e2e-ui-k8s`, `e2e-ui-run` (expects running env)
- Extends `e2e-lifecycle.sh` with `--ui` flag (changes test runner to Playwright)
- CI: `.github/workflows/e2e-ui.yml` — triggers on `frontend/**`, `tests/e2e-ui/**` path changes
- Snapshot updates: `npx playwright test --update-snapshots` locally, commit PNGs to PR

### Visual Regression
- ~12 committed PNG baselines in `snapshots/`
- Inline screenshots during journeys + 1 dedicated visual regression test
- `maxDiffPixelRatio: 0.01` — allows anti-aliasing differences
- `animations: 'disabled'` — freezes CSS transitions for deterministic screenshots

## Intentionally Excluded
- Placeholder buttons (emoji/GIF/voice — not functional)
- Layout drag & resize (React Grid Layout library behavior)
- Browser OS notifications (unreliable in headless Chromium)
- Auto-scroll internals (verified by messages appearing in view)
- Copy message button (low regression risk)
