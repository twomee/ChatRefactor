import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SearchModal from '../SearchModal';
import * as searchApi from '../../../services/searchApi';

vi.mock('../../../services/searchApi');

const rooms = [
  { id: 1, name: 'general' },
  { id: 2, name: 'random' },
];

describe('SearchModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <SearchModal isOpen={false} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders modal with search input when isOpen is true', () => {
    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );
    expect(screen.getByPlaceholderText('Search messages...')).toBeInTheDocument();
    expect(screen.getByText('ESC')).toBeInTheDocument();
  });

  it('shows hint text when query is empty', () => {
    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );
    expect(screen.getByText('Type to search across all messages')).toBeInTheDocument();
  });

  it('calls onClose when Escape is pressed', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onClose = vi.fn();
    render(
      <SearchModal isOpen={true} onClose={onClose} rooms={rooms} onNavigate={vi.fn()} />,
    );

    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when overlay is clicked', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onClose = vi.fn();
    render(
      <SearchModal isOpen={true} onClose={onClose} rooms={rooms} onNavigate={vi.fn()} />,
    );

    // Click the overlay (the element with role="dialog")
    const overlay = screen.getByRole('dialog');
    await user.click(overlay);
    expect(onClose).toHaveBeenCalled();
  });

  it('fires API call after debounce when user types', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    searchApi.searchMessages.mockResolvedValue({
      data: [
        {
          message_id: 'msg-1',
          sender_name: 'alice',
          content: 'hello world',
          room_id: 1,
          sent_at: '2025-06-01T12:00:00',
        },
      ],
    });

    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'hello');

    // Advance past debounce timer
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(searchApi.searchMessages).toHaveBeenCalledWith('hello');
    });
  });

  it('displays search results', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    searchApi.searchMessages.mockResolvedValue({
      data: [
        {
          message_id: 'msg-1',
          sender_name: 'alice',
          content: 'hello world',
          room_id: 1,
          sent_at: '2025-06-01T12:00:00',
        },
      ],
    });

    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'hello');
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(screen.getByText('alice')).toBeInTheDocument();
    });

    // Verify room name is shown
    expect(screen.getByText('#general')).toBeInTheDocument();
  });

  it('shows "No messages found" when search returns empty', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    searchApi.searchMessages.mockResolvedValue({ data: [] });

    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'xyznoexist');
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(screen.getByText('No messages found')).toBeInTheDocument();
    });
  });

  it('calls onNavigate and onClose when a result is clicked', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onNavigate = vi.fn();
    const onClose = vi.fn();
    searchApi.searchMessages.mockResolvedValue({
      data: [
        {
          message_id: 'msg-nav',
          sender_name: 'bob',
          content: 'navigate test',
          room_id: 2,
          sent_at: '2025-06-01T12:00:00',
        },
      ],
    });

    render(
      <SearchModal isOpen={true} onClose={onClose} rooms={rooms} onNavigate={onNavigate} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'navigate');
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(screen.getByText('bob')).toBeInTheDocument();
    });

    // Click the result item (text is split by highlight <mark>, so use role)
    await user.click(screen.getByRole('option'));

    expect(onNavigate).toHaveBeenCalledWith(2);
    expect(onClose).toHaveBeenCalled();
  });

  it('shows error message when API call fails', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    searchApi.searchMessages.mockRejectedValue(new Error('Network error'));

    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'error');
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(screen.getByText('Search failed. Please try again.')).toBeInTheDocument();
    });
  });
});
