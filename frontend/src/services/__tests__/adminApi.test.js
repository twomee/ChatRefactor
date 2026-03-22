import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  getRooms, getUsers, closeAllRooms, openAllRooms,
  closeRoom, openRoom, resetDatabase, promoteUser,
} from '../adminApi';
import http from '../http';

vi.mock('../http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('adminApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getRooms calls GET /admin/rooms', async () => {
    http.get.mockResolvedValue({ data: [] });
    await getRooms();
    expect(http.get).toHaveBeenCalledWith('/admin/rooms');
  });

  it('getUsers calls GET /admin/users', async () => {
    http.get.mockResolvedValue({ data: [] });
    await getUsers();
    expect(http.get).toHaveBeenCalledWith('/admin/users');
  });

  it('closeAllRooms calls POST /admin/chat/close', async () => {
    http.post.mockResolvedValue({ data: {} });
    await closeAllRooms();
    expect(http.post).toHaveBeenCalledWith('/admin/chat/close');
  });

  it('openAllRooms calls POST /admin/chat/open', async () => {
    http.post.mockResolvedValue({ data: {} });
    await openAllRooms();
    expect(http.post).toHaveBeenCalledWith('/admin/chat/open');
  });

  it('closeRoom calls POST /admin/rooms/{roomId}/close', async () => {
    http.post.mockResolvedValue({ data: {} });
    await closeRoom('room-42');
    expect(http.post).toHaveBeenCalledWith('/admin/rooms/room-42/close');
  });

  it('openRoom calls POST /admin/rooms/{roomId}/open', async () => {
    http.post.mockResolvedValue({ data: {} });
    await openRoom('room-42');
    expect(http.post).toHaveBeenCalledWith('/admin/rooms/room-42/open');
  });

  it('resetDatabase calls DELETE /admin/db', async () => {
    http.delete.mockResolvedValue({ data: {} });
    await resetDatabase();
    expect(http.delete).toHaveBeenCalledWith('/admin/db');
  });

  it('promoteUser calls POST with URL-encoded username', async () => {
    http.post.mockResolvedValue({ data: {} });
    await promoteUser('alice bob');
    expect(http.post).toHaveBeenCalledWith('/admin/promote?username=alice%20bob');
  });
});
