import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MessageList from '../MessageList';
import { ToastProvider } from '../../../context/ToastContext';

// Mock fileApi to avoid import side effects
vi.mock('../../../services/fileApi', () => ({
  downloadFile: vi.fn(),
}));

// Mock useAuth so MessageList can access user context in tests
vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'testuser' }, token: 'fake-token' }),
}));

function renderWithToast(ui) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

describe('MessageList', () => {
  it('renders nothing for empty message list', () => {
    const { container } = renderWithToast(<MessageList messages={[]} />);
    expect(container.querySelector('.msg')).toBeNull();
  });

  it('renders system messages with correct class', () => {
    const messages = [{ isSystem: true, text: 'Alice joined the room' }];
    renderWithToast(<MessageList messages={messages} />);
    expect(screen.getByText('Alice joined the room')).toBeInTheDocument();
    expect(screen.getByText('Alice joined the room').closest('.msg')).toHaveClass('msg-system');
  });

  it('renders regular messages with author and avatar initials', () => {
    const messages = [{ from: 'alice', text: 'Hello everyone!' }];
    renderWithToast(<MessageList messages={messages} />);
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('Hello everyone!')).toBeInTheDocument();
    expect(screen.getByText('AL')).toBeInTheDocument(); // initials
  });

  it('renders file messages with download link', () => {
    const messages = [{ isFile: true, from: 'bob', text: 'report.pdf', fileId: 'f1', fileSize: 2048 }];
    renderWithToast(<MessageList messages={messages} />);
    const button = screen.getByRole('button', { name: /report\.pdf/ });
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('report.pdf');
    expect(button).toHaveTextContent('2.0 KB');
  });

  it('renders private messages with direction labels', () => {
    const messages = [{ isPrivate: true, isSelf: true, from: 'me', to: 'alice', text: 'secret' }];
    renderWithToast(<MessageList messages={messages} />);
    expect(screen.getByText('You → alice')).toBeInTheDocument();
    expect(screen.getByText('secret')).toBeInTheDocument();
  });

  it('handles null/undefined messages gracefully', () => {
    const { container } = renderWithToast(<MessageList messages={null} />);
    expect(container.querySelector('.msg')).toBeNull();
  });

  it('generates initials correctly — first 2 chars uppercase', () => {
    const messages = [{ from: 'bob', text: 'hi' }];
    renderWithToast(<MessageList messages={messages} />);
    expect(screen.getByText('BO')).toBeInTheDocument();
  });

  it('highlights @mentions in regular messages', () => {
    const messages = [{ from: 'alice', text: 'Hey @bob check this out' }];
    const { container } = renderWithToast(<MessageList messages={messages} currentUser="testuser" />);
    const mention = container.querySelector('.mention');
    expect(mention).toBeInTheDocument();
    expect(mention.textContent).toBe('@bob');
  });

  it('highlights self-mention with mention-self class', () => {
    const messages = [{ from: 'alice', text: 'Hey @testuser look at this' }];
    const { container } = renderWithToast(<MessageList messages={messages} currentUser="testuser" />);
    const mention = container.querySelector('.mention-self');
    expect(mention).toBeInTheDocument();
    expect(mention.textContent).toBe('@testuser');
  });

  it('does not highlight mentions in system messages', () => {
    const messages = [{ isSystem: true, text: '@alice joined the room' }];
    const { container } = renderWithToast(<MessageList messages={messages} />);
    expect(container.querySelector('.mention')).toBeNull();
  });

  it('renders "New messages" divider after the last-read message', () => {
    const messages = [
      { from: 'alice', text: 'old message', msg_id: 'msg-1' },
      { from: 'bob', text: 'new message', msg_id: 'msg-2' },
    ];
    const { container } = renderWithToast(<MessageList messages={messages} lastReadMessageId="msg-1" />);
    const divider = container.querySelector('.new-messages-divider');
    expect(divider).toBeInTheDocument();
    expect(divider.textContent).toBe('New messages');
  });

  it('does not render divider when lastReadMessageId is the last message', () => {
    const messages = [
      { from: 'alice', text: 'old message', msg_id: 'msg-1' },
      { from: 'bob', text: 'latest', msg_id: 'msg-2' },
    ];
    const { container } = renderWithToast(<MessageList messages={messages} lastReadMessageId="msg-2" />);
    expect(container.querySelector('.new-messages-divider')).toBeNull();
  });

  it('does not render divider when lastReadMessageId is not provided', () => {
    const messages = [
      { from: 'alice', text: 'msg', msg_id: 'msg-1' },
      { from: 'bob', text: 'msg2', msg_id: 'msg-2' },
    ];
    const { container } = renderWithToast(<MessageList messages={messages} />);
    expect(container.querySelector('.new-messages-divider')).toBeNull();
  });

  // ── Phase 1: Deleted messages ───────────────────────────────────────────

  it('renders deleted messages with muted "[deleted]" style', () => {
    const messages = [{ from: 'alice', text: '[deleted]', is_deleted: true }];
    const { container } = renderWithToast(<MessageList messages={messages} />);
    expect(container.querySelector('.msg-deleted-text')).toBeInTheDocument();
    expect(container.querySelector('.msg-deleted-text').textContent).toBe('[deleted]');
  });

  it('does not render edit/delete actions for deleted messages', () => {
    const messages = [{ from: 'testuser', text: '[deleted]', is_deleted: true, msg_id: 'msg1' }];
    const { container } = renderWithToast(<MessageList messages={messages} currentUser="testuser" />);
    expect(container.querySelector('.msg-actions')).toBeNull();
  });

  // ── Phase 1: Edited badge ───────────────────────────────────────────────

  it('renders "(edited)" badge when edited_at is present', () => {
    const messages = [{ from: 'alice', text: 'updated text', edited_at: '2024-01-01T00:00:00Z', msg_id: 'msg1' }];
    renderWithToast(<MessageList messages={messages} />);
    expect(screen.getByText('(edited)')).toBeInTheDocument();
  });

  it('does not render "(edited)" badge when edited_at is absent', () => {
    const messages = [{ from: 'alice', text: 'normal message', msg_id: 'msg1' }];
    renderWithToast(<MessageList messages={messages} />);
    expect(screen.queryByText('(edited)')).toBeNull();
  });

  // ── Phase 1: Edit / Delete action buttons ──────────────────────────────

  it('shows copy, edit and delete buttons for own messages', () => {
    const messages = [{ from: 'testuser', text: 'my message', msg_id: 'msg1' }];
    const { container } = renderWithToast(<MessageList messages={messages} currentUser="testuser" onEditMessage={vi.fn()} onDeleteMessage={vi.fn()} />);
    const actions = container.querySelector('.msg-actions');
    expect(actions).toBeInTheDocument();
    // Copy + Edit + Delete
    const buttons = actions.querySelectorAll('.msg-action-btn');
    expect(buttons).toHaveLength(3);
  });

  it('shows only copy button for other users\' messages (no edit/delete)', () => {
    const messages = [{ from: 'alice', text: 'alice message', msg_id: 'msg1' }];
    renderWithToast(<MessageList messages={messages} currentUser="testuser" onEditMessage={vi.fn()} onDeleteMessage={vi.fn()} />);
    // Copy is always available
    expect(screen.getByTitle('Copy')).toBeInTheDocument();
    // Edit and Delete are only for own messages
    expect(screen.queryByTitle('Edit')).toBeNull();
    expect(screen.queryByTitle('Delete')).toBeNull();
  });

  it('shows copy button for all messages including other users\'', () => {
    const messages = [{ from: 'alice', text: 'hello world', msg_id: 'msg1' }];
    const { container } = renderWithToast(<MessageList messages={messages} currentUser="testuser" />);
    expect(container.querySelector('[data-testid="copy-message-btn"]')).toBeInTheDocument();
  });

  it('calls navigator.clipboard.writeText when copy button is clicked', () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    // jsdom doesn't implement navigator.clipboard; install a getter so the
    // component can access it synchronously when the button is clicked.
    Object.defineProperty(window.navigator, 'clipboard', {
      get: () => ({ writeText }),
      configurable: true,
    });
    const messages = [{ from: 'alice', text: 'copy me', msg_id: 'msg1' }];
    const { container } = renderWithToast(<MessageList messages={messages} currentUser="testuser" />);
    fireEvent.click(container.querySelector('[data-testid="copy-message-btn"]'));
    expect(writeText).toHaveBeenCalledWith('copy me');
  });

  it('calls onEditMessage with the message when edit button is clicked', async () => {
    const onEditMessage = vi.fn();
    const user = userEvent.setup();
    const msg = { from: 'testuser', text: 'my message', msg_id: 'msg1' };
    renderWithToast(<MessageList messages={[msg]} currentUser="testuser" onEditMessage={onEditMessage} onDeleteMessage={vi.fn()} />);
    await user.click(screen.getByTitle('Edit'));
    expect(onEditMessage).toHaveBeenCalledWith(expect.objectContaining({ msg_id: 'msg1' }));
  });

  it('calls onDeleteMessage with the message when delete button is clicked', async () => {
    const onDeleteMessage = vi.fn();
    const user = userEvent.setup();
    const msg = { from: 'testuser', text: 'my message', msg_id: 'msg1' };
    renderWithToast(<MessageList messages={[msg]} currentUser="testuser" onEditMessage={vi.fn()} onDeleteMessage={onDeleteMessage} />);
    await user.click(screen.getByTitle('Delete'));
    expect(onDeleteMessage).toHaveBeenCalledWith(expect.objectContaining({ msg_id: 'msg1' }));
  });

  // ── Phase 1: Emoji reactions ─────────────────────────────────────────────

  it('renders reaction chips for messages with reactions', () => {
    const messages = [{
      from: 'alice',
      text: 'hello',
      msg_id: 'msg1',
      reactions: [
        { emoji: '👍', username: 'bob', user_id: 2 },
        { emoji: '👍', username: 'charlie', user_id: 3 },
        { emoji: '❤️', username: 'dave', user_id: 4 },
      ],
    }];
    const { container } = renderWithToast(<MessageList messages={messages} currentUser="testuser" />);
    const chips = container.querySelectorAll('.reaction-chip');
    expect(chips).toHaveLength(2); // 👍 and ❤️ grouped
  });

  it('marks own reaction chip with reaction-mine class', () => {
    const messages = [{
      from: 'alice',
      text: 'hello',
      msg_id: 'msg1',
      reactions: [{ emoji: '👍', username: 'testuser', user_id: 1 }],
    }];
    const { container } = renderWithToast(<MessageList messages={messages} currentUser="testuser" />);
    expect(container.querySelector('.reaction-mine')).toBeInTheDocument();
  });

  it('calls onAddReaction when clicking an unreacted chip', async () => {
    const onAddReaction = vi.fn();
    const user = userEvent.setup();
    const messages = [{
      from: 'alice',
      text: 'hello',
      msg_id: 'msg1',
      reactions: [{ emoji: '👍', username: 'bob', user_id: 2 }],
    }];
    renderWithToast(<MessageList messages={messages} currentUser="testuser" onAddReaction={onAddReaction} onRemoveReaction={vi.fn()} />);
    await user.click(screen.getByTitle('bob'));
    expect(onAddReaction).toHaveBeenCalledWith('msg1', '👍');
  });

  it('calls onRemoveReaction when clicking an already-reacted chip', async () => {
    const onRemoveReaction = vi.fn();
    const user = userEvent.setup();
    const messages = [{
      from: 'alice',
      text: 'hello',
      msg_id: 'msg1',
      reactions: [{ emoji: '👍', username: 'testuser', user_id: 1 }],
    }];
    renderWithToast(<MessageList messages={messages} currentUser="testuser" onAddReaction={vi.fn()} onRemoveReaction={onRemoveReaction} />);
    await user.click(screen.getByTitle('testuser'));
    expect(onRemoveReaction).toHaveBeenCalledWith('msg1', '👍');
  });

  it('renders the add-reaction (+) button when onAddReaction is provided', () => {
    const messages = [{ from: 'alice', text: 'hi', msg_id: 'msg1', reactions: [] }];
    const { container } = renderWithToast(<MessageList messages={messages} currentUser="testuser" onAddReaction={vi.fn()} />);
    expect(container.querySelector('.reaction-add-btn')).toBeInTheDocument();
  });

  // ── Phase D2: Scroll-to-message highlight ───────────────────────────────

  it('adds data-msg-id attributes to message elements', () => {
    const messages = [
      { from: 'alice', text: 'first', msg_id: 'msg-1' },
      { from: 'bob', text: 'second', msg_id: 'msg-2' },
    ];
    const { container } = renderWithToast(<MessageList messages={messages} />);
    expect(container.querySelector('[data-msg-id="msg-1"]')).toBeInTheDocument();
    expect(container.querySelector('[data-msg-id="msg-2"]')).toBeInTheDocument();
  });

  it('adds msg-highlight class to the targeted message when highlightMessageId is set', () => {
    const messages = [
      { from: 'alice', text: 'first', msg_id: 'msg-1' },
      { from: 'bob', text: 'second', msg_id: 'msg-2' },
    ];
    // Mock scrollIntoView since jsdom doesn't implement it
    Element.prototype.scrollIntoView = vi.fn();

    const { container } = renderWithToast(<MessageList messages={messages} highlightMessageId="msg-2" />);
    const targetEl = container.querySelector('[data-msg-id="msg-2"]');
    expect(targetEl).toBeInTheDocument();
    expect(targetEl.classList.contains('msg-highlight')).toBe(true);
  });
});
