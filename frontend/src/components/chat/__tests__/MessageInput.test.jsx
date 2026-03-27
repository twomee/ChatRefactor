import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MessageInput from '../MessageInput';
import * as fileApi from '../../../services/fileApi';

vi.mock('../../../services/fileApi');

describe('MessageInput', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders input and send button', () => {
    render(<MessageInput onSend={vi.fn()} />);
    expect(screen.getByPlaceholderText('Type a message...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
  });

  it('send button is disabled when input is empty', () => {
    render(<MessageInput onSend={vi.fn()} />);
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
  });

  it('send button is enabled when input has text', async () => {
    const user = userEvent.setup();
    render(<MessageInput onSend={vi.fn()} />);

    await user.type(screen.getByPlaceholderText('Type a message...'), 'hello');
    expect(screen.getByRole('button', { name: /send/i })).toBeEnabled();
  });

  it('calls onSend with trimmed text on form submit', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageInput onSend={onSend} />);

    await user.type(screen.getByPlaceholderText('Type a message...'), '  hello world  ');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(onSend).toHaveBeenCalledWith('hello world');
  });

  it('clears input after sending', async () => {
    const user = userEvent.setup();
    render(<MessageInput onSend={vi.fn()} />);

    const input = screen.getByPlaceholderText('Type a message...');
    await user.type(input, 'hello');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(input).toHaveValue('');
  });

  it('does not call onSend for whitespace-only input', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageInput onSend={onSend} />);

    await user.type(screen.getByPlaceholderText('Type a message...'), '   ');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(onSend).not.toHaveBeenCalled();
  });

  it('calls uploadFile when a file is selected', async () => {
    fileApi.uploadFile.mockResolvedValue({});
    const user = userEvent.setup();
    render(<MessageInput onSend={vi.fn()} roomId="room-1" />);

    const file = new File(['hello'], 'hello.txt', { type: 'text/plain' });
    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, file);

    await waitFor(() => expect(fileApi.uploadFile).toHaveBeenCalledWith('room-1', file, expect.any(Function)));
  });

  it('shows upload error when uploadFile rejects', async () => {
    fileApi.uploadFile.mockRejectedValue({ response: { data: { error: 'Upload failed' } } });
    const user = userEvent.setup();
    render(<MessageInput onSend={vi.fn()} roomId="room-1" />);

    const file = new File(['hello'], 'hello.txt', { type: 'text/plain' });
    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, file);

    await waitFor(() => expect(screen.getByText('Upload failed')).toBeInTheDocument());
  });

  it('does nothing when file input is cleared without selecting a file', async () => {
    render(<MessageInput onSend={vi.fn()} roomId="room-1" />);
    // Simulate change event with no files selected
    const fileInput = document.querySelector('input[type="file"]');
    fileInput.dispatchEvent(new Event('change', { bubbles: true }));
    expect(fileApi.uploadFile).not.toHaveBeenCalled();
  });
});
