import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../../services/fileApi', () => ({
  uploadFile: vi.fn(),
}));

import * as fileApi from '../../../services/fileApi';
import FileProgress from '../FileProgress';

describe('FileProgress (FileUpload)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Attach file label', () => {
    render(<FileProgress roomId="room-1" />);
    expect(screen.getByText('Attach file')).toBeInTheDocument();
  });

  it('calls uploadFile when a file is selected', async () => {
    fileApi.uploadFile.mockResolvedValue({});
    render(<FileProgress roomId="room-1" />);

    const input = document.querySelector('.file-upload-input');
    const file = new File(['content'], 'test.txt', { type: 'text/plain' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(fileApi.uploadFile).toHaveBeenCalledWith('room-1', file, expect.any(Function));
    });
  });

  it('does nothing when no file is selected', async () => {
    render(<FileProgress roomId="room-1" />);
    const input = document.querySelector('.file-upload-input');
    fireEvent.change(input, { target: { files: [] } });
    expect(fileApi.uploadFile).not.toHaveBeenCalled();
  });

  it('shows error message on upload failure', async () => {
    fileApi.uploadFile.mockRejectedValue({ response: { data: { error: 'File too large' } } });
    render(<FileProgress roomId="room-1" />);

    const input = document.querySelector('.file-upload-input');
    const file = new File(['x'], 'big.zip');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('File too large')).toBeInTheDocument();
    });
  });

  it('shows "Upload failed" when no specific error message in response', async () => {
    fileApi.uploadFile.mockRejectedValue({ response: {} });
    render(<FileProgress roomId="room-1" />);

    const input = document.querySelector('.file-upload-input');
    fireEvent.change(input, { target: { files: [new File(['x'], 'f.txt')] } });

    await waitFor(() => {
      expect(screen.getByText('Upload failed')).toBeInTheDocument();
    });
  });

  it('shows progress bar while uploading', async () => {
    let capturedProgressCb;
    fileApi.uploadFile.mockImplementation((_roomId, _file, onProgress) => {
      capturedProgressCb = onProgress;
      return new Promise(() => {}); // never resolves (still uploading)
    });

    const { container } = render(<FileProgress roomId="room-1" />);
    const input = document.querySelector('.file-upload-input');
    fireEvent.change(input, { target: { files: [new File(['x'], 'f.txt')] } });

    // Simulate progress update
    capturedProgressCb({ loaded: 50, total: 100 });
    await waitFor(() => {
      expect(container.querySelector('.file-progress-bar')).toBeInTheDocument();
      expect(screen.getByText('50%')).toBeInTheDocument();
    });
  });
});
