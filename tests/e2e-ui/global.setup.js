const { test } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const { ADMIN, USER_A, USER_B, USER_C, USER_D, USER_E, TEST_ROOM } = require('./fixtures/test-data');

const TOKENS_DIR = path.join(__dirname, 'playwright', '.auth');
const TOKENS_PATH = path.join(TOKENS_DIR, 'tokens.json');

async function registerAndLogin(baseURL, user) {
  const regBody = { username: user.username, password: user.password };
  if (user.email) regBody.email = user.email;

  let retries = 5;
  while (retries > 0) {
    const regRes = await fetch(`${baseURL}/auth/register`, {
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

  let loginRes;
  retries = 5;
  while (retries > 0) {
    loginRes = await fetch(`${baseURL}/auth/login`, {
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

  if (!loginRes) {
    throw new Error(`Login failed for ${user.username}: all retries exhausted (rate limited)`);
  }

  const data = await loginRes.json();

  // Handle 2FA-enabled users: if login returns requires_2fa, we can't proceed
  // without a TOTP code. Log a warning — tests that need this user will skip.
  if (data.requires_2fa) {
    console.warn(`WARNING: User ${user.username} has 2FA enabled from a previous run. Creating a fresh user.`);
    // Create a fresh user variant to bypass 2FA
    const freshUser = { ...user, username: user.username + '_' + Date.now().toString(36) };
    if (freshUser.email) freshUser.email = freshUser.username + '@test.com';
    const freshRegBody = { username: freshUser.username, password: freshUser.password };
    if (freshUser.email) freshRegBody.email = freshUser.email;
    await fetch(`${baseURL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(freshRegBody),
    });
    const freshLoginRes = await fetch(`${baseURL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: freshUser.username, password: freshUser.password }),
    });
    const freshData = await freshLoginRes.json();
    return {
      token: freshData.access_token,
      user: { username: freshUser.username, user_id: freshData.user_id, is_global_admin: freshData.is_global_admin || false },
    };
  }

  if (!data.access_token) {
    throw new Error(`Login failed for ${user.username}: ${JSON.stringify(data)}`);
  }
  return {
    token: data.access_token,
    user: { username: user.username, user_id: data.user_id, is_global_admin: data.is_global_admin || false },
  };
}

test('register all test users and save tokens', async () => {
  test.setTimeout(120_000); // 2 min — rate limiting may cause retries
  const baseURL = process.env.BASE_URL || 'http://localhost:8090';
  const tokens = {};

  tokens.admin = await registerAndLogin(baseURL, ADMIN);
  tokens.userA = await registerAndLogin(baseURL, USER_A);
  tokens.userB = await registerAndLogin(baseURL, USER_B);
  tokens.userC = await registerAndLogin(baseURL, USER_C);

  // Timestamp suffix for fresh user variants
  const ts = Date.now().toString(36);

  // Dedicated users for logout tests — tokens get blacklisted on logout,
  // which would break any subsequent test reusing the same token.
  const logoutUser = { username: `logout_ui_${ts}`, email: `logout_ui_${ts}@test.com`, password: 'Test1234!' };
  tokens.logoutUser = await registerAndLogin(baseURL, logoutUser);
  // Separate user for presence Test 40 (logout disappearance)
  const logoutPresence = { username: `logpres_${ts}`, email: `logpres_${ts}@test.com`, password: 'Test1234!' };
  tokens.logoutPresence = await registerAndLogin(baseURL, logoutPresence);
  // Separate user for PM Test 44 (PM logout shows offline) — token blacklisted on logout
  const logoutPM = { username: `logpm_${ts}`, email: `logpm_${ts}@test.com`, password: 'Test1234!' };
  tokens.logoutPM = await registerAndLogin(baseURL, logoutPM);
  // Users D and E are used for settings tests (password change, 2FA).
  // Previous runs may have modified their credentials, so always create fresh users.
  const freshD = { username: `delta_ui_${ts}`, email: `delta_ui_${ts}@test.com`, password: USER_D.password };
  const freshE = { username: `echo_ui_${ts}`, email: `echo_ui_${ts}@test.com`, password: USER_E.password };
  tokens.userD = await registerAndLogin(baseURL, freshD);
  tokens.userE = await registerAndLogin(baseURL, freshE);
  // Dedicated user for Test 31 (promote to room admin).
  // Using a fresh user prevents state pollution of userB across runs since
  // there is no demote API endpoint to clean up after the test.
  const promoteTarget = { username: `promote_${ts}`, email: `promote_${ts}@test.com`, password: 'Test1234!' };
  tokens.promoteTarget = await registerAndLogin(baseURL, promoteTarget);

  // Create the test room (may already exist)
  await fetch(`${baseURL}/rooms`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${tokens.admin.token}`,
    },
    body: JSON.stringify({ name: TEST_ROOM }),
  });

  // Ensure the test room is open (it may have been closed by a previous test run)
  // First, find the room ID from the admin rooms endpoint
  const adminRoomsRes = await fetch(`${baseURL}/admin/rooms`, {
    headers: { 'Authorization': `Bearer ${tokens.admin.token}` },
  }).catch(() => null);
  if (adminRoomsRes?.ok) {
    const adminRooms = await adminRoomsRes.json();
    const testRoom = adminRooms.find(r => r.name === TEST_ROOM);
    if (testRoom && !testRoom.is_active) {
      const openRes = await fetch(`${baseURL}/admin/rooms/${testRoom.id}/open`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${tokens.admin.token}` },
      }).catch(() => null);
      if (!openRes?.ok) {
        console.warn(`WARNING: Failed to open test room "${TEST_ROOM}" (status: ${openRes?.status}). Tests that need an open room may fail.`);
      }
    }
  }

  fs.mkdirSync(TOKENS_DIR, { recursive: true });
  fs.writeFileSync(TOKENS_PATH, JSON.stringify(tokens, null, 2));
});
