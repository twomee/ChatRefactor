import { describe, it, expect, vi, beforeEach } from 'vitest';
import { uploadFile, listRoomFiles, getDownloadUrl } from '../fileApi';
import http from '../http';

vi.mock('../http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

vi.mock('../../config/constants', () => ({
  API_BASE: 'http://localhost:8000',
}));

describe('fileApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  describe('uploadFile', () => {
    it('posts FormData to /files/upload with room_id and progress callback', async () => {
      http.post.mockResolvedValue({ data: { file_id: 'f1' } });
      const onProgress = vi.fn();
      const file = new File(['content'], 'test.txt', { type: 'text/plain' });

      await uploadFile('room-1', file, onProgress);

      expect(http.post).toHaveBeenCalledWith(
        '/files/upload?room_id=room-1',
        expect.any(FormData),
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: onProgress,
        },
      );
    });
  });

  describe('listRoomFiles', () => {
    it('calls GET /files/room/{roomId}', async () => {
      http.get.mockResolvedValue({ data: [] });
      await listRoomFiles('room-1');
      expect(http.get).toHaveBeenCalledWith('/files/room/room-1');
    });
  });

  describe('getDownloadUrl', () => {
    it('returns URL with file ID and token from sessionStorage', () => {
      sessionStorage.setItem('token', 'my-jwt');
      const url = getDownloadUrl('file-42');
      expect(url).toBe('http://localhost:8000/files/download/file-42?token=my-jwt');
    });

    it('returns URL with null token when no token stored', () => {
      const url = getDownloadUrl('file-42');
      expect(url).toBe('http://localhost:8000/files/download/file-42?token=null');
    });
  });
});
