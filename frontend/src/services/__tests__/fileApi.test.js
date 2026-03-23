import { describe, it, expect, vi, beforeEach } from 'vitest';
import { uploadFile, listRoomFiles, downloadFile } from '../fileApi';
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

  describe('downloadFile', () => {
    it('fetches file as blob via Authorization header and triggers download', async () => {
      const blob = new Blob(['file-content'], { type: 'application/octet-stream' });
      http.get.mockResolvedValue({ data: blob });

      // Mock DOM APIs
      const createObjectURL = vi.fn(() => 'blob:http://localhost/fake');
      const revokeObjectURL = vi.fn();
      global.URL.createObjectURL = createObjectURL;
      global.URL.revokeObjectURL = revokeObjectURL;

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
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:http://localhost/fake');
    });
  });
});
