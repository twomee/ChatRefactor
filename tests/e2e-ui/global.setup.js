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

  const data = await loginRes.json();
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
  tokens.userD = await registerAndLogin(baseURL, USER_D);
  tokens.userE = await registerAndLogin(baseURL, USER_E);

  await fetch(`${baseURL}/rooms`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${tokens.admin.token}`,
    },
    body: JSON.stringify({ name: TEST_ROOM }),
  });

  fs.mkdirSync(TOKENS_DIR, { recursive: true });
  fs.writeFileSync(TOKENS_PATH, JSON.stringify(tokens, null, 2));
});
