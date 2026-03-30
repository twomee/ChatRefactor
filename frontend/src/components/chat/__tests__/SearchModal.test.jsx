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

const mockResults = [
  {
    message_id: 'msg-1',
    sender_name: 'alice',
    content: 'hello world',
    room_id: 1,
    sent_at: '2025-06-01T12:00:00',
  },
  {
    message_id: 'msg-2',
    sender_name: 'bob',
    content: 'hello there',
    room_id: 2,
    sent_at: '2025-06-01T13:00:00',
  },
  {
    message_id: 'msg-3',
    sender_name: 'carol',
    content: 'hello again',
    room_id: 1,
    sent_at: '2025-06-01T14:00:00',
  },
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

    // Click the backdrop overlay (parent of the dialog)
    const dialog = screen.getByRole('dialog');
    await user.click(dialog.parentElement);
    expect(onClose).toHaveBeenCalled();
  });

  it('fires API call after debounce when user types', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    searchApi.searchMessages.mockResolvedValue({
      data: [mockResults[0]],
    });

    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'hello');

    // Advance past debounce timer
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(searchApi.searchMessages).toHaveBeenCalledWith('hello', null, 20, expect.any(Object));
    });
  });

  it('displays search results with avatar initials', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    searchApi.searchMessages.mockResolvedValue({
      data: [mockResults[0]],
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
    expect(screen.getByText('general')).toBeInTheDocument();

    // Verify avatar initials are rendered
    expect(screen.getByText('AL')).toBeInTheDocument();
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

  it('calls onNavigate with room_id AND message_id when a result is clicked', async () => {
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

    // Click the result item
    await user.click(screen.getByText('bob').closest('button'));

    expect(onNavigate).toHaveBeenCalledWith(2, 'msg-nav');
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

  // ── Keyboard navigation tests ──

  it('ArrowDown increments selectedIndex (active class on result)', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    searchApi.searchMessages.mockResolvedValue({ data: mockResults });

    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'hello');
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(screen.getByText('alice')).toBeInTheDocument();
    });

    // Initially no item has active class
    const items = screen.getAllByRole('option');
    expect(items[0].querySelector('.search-result-item.active')).toBeNull();

    // Press ArrowDown — first item should be active
    await user.keyboard('{ArrowDown}');
    expect(items[0].querySelector('.search-result-item.active')).not.toBeNull();

    // Press ArrowDown again — second item should be active
    await user.keyboard('{ArrowDown}');
    expect(items[0].querySelector('.search-result-item.active')).toBeNull();
    expect(items[1].querySelector('.search-result-item.active')).not.toBeNull();
  });

  it('ArrowUp decrements selectedIndex', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    searchApi.searchMessages.mockResolvedValue({ data: mockResults });

    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'hello');
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(screen.getByText('alice')).toBeInTheDocument();
    });

    // Navigate down twice to select bob (index 1)
    await user.keyboard('{ArrowDown}');
    await user.keyboard('{ArrowDown}');

    const items = screen.getAllByRole('option');
    expect(items[1].querySelector('.search-result-item.active')).not.toBeNull();

    // Navigate back up — alice (index 0) should be active
    await user.keyboard('{ArrowUp}');
    expect(items[0].querySelector('.search-result-item.active')).not.toBeNull();
    expect(items[1].querySelector('.search-result-item.active')).toBeNull();
  });

  it('Enter on selected result calls onNavigate with room_id AND message_id', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onNavigate = vi.fn();
    const onClose = vi.fn();
    searchApi.searchMessages.mockResolvedValue({ data: mockResults });

    render(
      <SearchModal isOpen={true} onClose={onClose} rooms={rooms} onNavigate={onNavigate} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'hello');
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(screen.getByText('alice')).toBeInTheDocument();
    });

    // Select first item and press Enter
    await user.keyboard('{ArrowDown}');
    await user.keyboard('{Enter}');

    expect(onNavigate).toHaveBeenCalledWith(1, 'msg-1');
    expect(onClose).toHaveBeenCalled();
  });

  it('selectedIndex resets on query change', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    searchApi.searchMessages.mockResolvedValue({ data: mockResults });

    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'hello');
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(screen.getByText('alice')).toBeInTheDocument();
    });

    // Select first item
    await user.keyboard('{ArrowDown}');
    const items = screen.getAllByRole('option');
    expect(items[0].querySelector('.search-result-item.active')).not.toBeNull();

    // Type more text — selectedIndex should reset, so active class should disappear
    // after the new results come in
    searchApi.searchMessages.mockResolvedValue({ data: mockResults });
    await user.type(input, 'x');
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      const allItems = screen.getAllByRole('option');
      const activeItems = allItems.filter(
        (item) => item.querySelector('.search-result-item.active') !== null,
      );
      expect(activeItems).toHaveLength(0);
    });
  });

  it('renders sender avatar initials in results', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    searchApi.searchMessages.mockResolvedValue({ data: mockResults });

    render(
      <SearchModal isOpen={true} onClose={vi.fn()} rooms={rooms} onNavigate={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('Search messages...');
    await user.type(input, 'hello');
    vi.advanceTimersByTime(350);

    await waitFor(() => {
      expect(screen.getByText('alice')).toBeInTheDocument();
    });

    // Check all three avatar initials are rendered
    expect(screen.getByText('AL')).toBeInTheDocument();
    expect(screen.getByText('BO')).toBeInTheDocument();
    expect(screen.getByText('CA')).toBeInTheDocument();
  });
});
