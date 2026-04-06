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
