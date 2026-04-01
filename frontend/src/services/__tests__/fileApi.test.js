import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { uploadFile, listRoomFiles, downloadFile, uploadPMFile } from '../fileApi';
import http from '../http';

vi.mock('../http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
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

  describe('uploadPMFile', () => {
    it('posts FormData to /files/upload with recipient and progress callback', async () => {
      http.post.mockResolvedValue({ data: { file_id: 'f2' } });
      const onProgress = vi.fn();
      const file = new File(['data'], 'photo.jpg', { type: 'image/jpeg' });

      await uploadPMFile('bob', file, onProgress);

      expect(http.post).toHaveBeenCalledWith(
        '/files/upload?recipient=bob',
        expect.any(FormData),
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: onProgress,
        },
      );
    });

    it('URL-encodes the recipient username', async () => {
      http.post.mockResolvedValue({ data: {} });
      const file = new File(['x'], 'a.txt');
      await uploadPMFile('alice bob', file);
      expect(http.post).toHaveBeenCalledWith(
        expect.stringContaining('alice%20bob'),
        expect.any(FormData),
        expect.any(Object),
      );
    });
  });

  describe('downloadFile', () => {
    beforeEach(() => { vi.useFakeTimers(); });
    afterEach(() => { vi.useRealTimers(); });

    it('fetches file as blob via Authorization header and triggers download', async () => {
      const blob = new Blob(['file-content'], { type: 'application/octet-stream' });
      http.get.mockResolvedValue({ data: blob });

      // Mock DOM APIs
      const createObjectURL = vi.fn(() => 'blob:http://localhost/fake');
      const revokeObjectURL = vi.fn();
      globalThis.URL.createObjectURL = createObjectURL;
      globalThis.URL.revokeObjectURL = revokeObjectURL;

      const clickSpy = vi.fn();
      const appendSpy = vi.fn();
      const removeSpy = vi.fn();
      vi.spyOn(document, 'createElement').mockReturnValue({
        href: '',
        download: '',
        click: clickSpy,
      });
      vi.spyOn(document.body, 'appendChild').mockImplementation(appendSpy);
      vi.spyOn(document.body, 'removeChild').mockImplementation(removeSpy);

      await downloadFile(42, 'report.pdf');

      expect(http.get).toHaveBeenCalledWith('/files/download/42', {
        responseType: 'blob',
      });
      expect(createObjectURL).toHaveBeenCalledWith(blob);
      expect(clickSpy).toHaveBeenCalled();

      // revokeObjectURL is called after a 100ms delay — advance timers to trigger it
      vi.advanceTimersByTime(100);
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:http://localhost/fake');
    });

    it('throws with permission message on 403 error', async () => {
      http.get.mockRejectedValue({ response: { status: 403 } });
      await expect(downloadFile(1, 'secret.pdf')).rejects.toThrow('You do not have permission to download this file.');
    });

    it('throws with not-found message on 404 error', async () => {
      http.get.mockRejectedValue({ response: { status: 404 } });
      await expect(downloadFile(2, 'missing.pdf')).rejects.toThrow('File not found.');
    });

    it('throws with generic message on other errors', async () => {
      http.get.mockRejectedValue({ response: { status: 500 } });
      await expect(downloadFile(3, 'error.pdf')).rejects.toThrow('Download failed. Please try again.');
    });
  });
});
