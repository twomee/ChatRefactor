import { describe, it, expect, vi, beforeEach } from 'vitest';
import { sendPM } from '../pmApi';
import http from '../http';

vi.mock('../http', () => ({
  default: {
    post: vi.fn(),
  },
}));

describe('pmApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sends PM to the correct endpoint with payload', async () => {
    http.post.mockResolvedValue({ data: { status: 'sent' } });
    await sendPM('bob', 'Hello!');
    expect(http.post).toHaveBeenCalledWith('/pm/send', { to: 'bob', text: 'Hello!' });
  });
});
