import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MessageList from '../MessageList';

// Mock fileApi to avoid import side effects
vi.mock('../../../services/fileApi', () => ({
  downloadFile: vi.fn(),
}));

// Mock useAuth so MessageList can access user context in tests
vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'testuser' }, token: 'fake-token' }),
}));

describe('MessageList', () => {
  it('renders nothing for empty message list', () => {
    const { container } = render(<MessageList messages={[]} />);
    expect(container.querySelector('.msg')).toBeNull();
  });

  it('renders system messages with correct class', () => {
    const messages = [{ isSystem: true, text: 'Alice joined the room' }];
    render(<MessageList messages={messages} />);
    expect(screen.getByText('Alice joined the room')).toBeInTheDocument();
    expect(screen.getByText('Alice joined the room').closest('.msg')).toHaveClass('msg-system');
  });

  it('renders regular messages with author and avatar initials', () => {
    const messages = [{ from: 'alice', text: 'Hello everyone!' }];
    render(<MessageList messages={messages} />);
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('Hello everyone!')).toBeInTheDocument();
    expect(screen.getByText('AL')).toBeInTheDocument(); // initials
  });

  it('renders file messages with download link', () => {
    const messages = [{ isFile: true, from: 'bob', text: 'report.pdf', fileId: 'f1', fileSize: 2048 }];
    render(<MessageList messages={messages} />);
    const link = screen.getByText('report.pdf');
    expect(link.closest('button')).toBeInTheDocument();
    expect(screen.getByText('(2.0 KB)')).toBeInTheDocument();
  });

  it('renders private messages with direction labels', () => {
    const messages = [{ isPrivate: true, isSelf: true, from: 'me', to: 'alice', text: 'secret' }];
    render(<MessageList messages={messages} />);
    expect(screen.getByText('You → alice')).toBeInTheDocument();
    expect(screen.getByText('secret')).toBeInTheDocument();
  });

  it('handles null/undefined messages gracefully', () => {
    const { container } = render(<MessageList messages={null} />);
    expect(container.querySelector('.msg')).toBeNull();
  });

  it('generates initials correctly — first 2 chars uppercase', () => {
    const messages = [{ from: 'bob', text: 'hi' }];
    render(<MessageList messages={messages} />);
    expect(screen.getByText('BO')).toBeInTheDocument();
  });

  it('highlights @mentions in regular messages', () => {
    const messages = [{ from: 'alice', text: 'Hey @bob check this out' }];
    const { container } = render(<MessageList messages={messages} currentUser="testuser" />);
    const mention = container.querySelector('.mention');
    expect(mention).toBeInTheDocument();
    expect(mention.textContent).toBe('@bob');
  });

  it('highlights self-mention with mention-self class', () => {
    const messages = [{ from: 'alice', text: 'Hey @testuser look at this' }];
    const { container } = render(<MessageList messages={messages} currentUser="testuser" />);
    const mention = container.querySelector('.mention-self');
    expect(mention).toBeInTheDocument();
    expect(mention.textContent).toBe('@testuser');
  });

  it('does not highlight mentions in system messages', () => {
    const messages = [{ isSystem: true, text: '@alice joined the room' }];
    const { container } = render(<MessageList messages={messages} />);
    expect(container.querySelector('.mention')).toBeNull();
  });

  it('renders "New messages" divider after the last-read message', () => {
    const messages = [
      { from: 'alice', text: 'old message', msg_id: 'msg-1' },
      { from: 'bob', text: 'new message', msg_id: 'msg-2' },
    ];
    const { container } = render(
      <MessageList messages={messages} lastReadMessageId="msg-1" />
    );
    const divider = container.querySelector('.new-messages-divider');
    expect(divider).toBeInTheDocument();
    expect(divider.textContent).toBe('New messages');
  });

  it('does not render divider when lastReadMessageId is the last message', () => {
    const messages = [
      { from: 'alice', text: 'old message', msg_id: 'msg-1' },
      { from: 'bob', text: 'latest', msg_id: 'msg-2' },
    ];
    const { container } = render(
      <MessageList messages={messages} lastReadMessageId="msg-2" />
    );
    expect(container.querySelector('.new-messages-divider')).toBeNull();
  });

  it('does not render divider when lastReadMessageId is not provided', () => {
    const messages = [
      { from: 'alice', text: 'msg', msg_id: 'msg-1' },
      { from: 'bob', text: 'msg2', msg_id: 'msg-2' },
    ];
    const { container } = render(<MessageList messages={messages} />);
    expect(container.querySelector('.new-messages-divider')).toBeNull();
  });

  // ── Phase 1: Deleted messages ───────────────────────────────────────────

  it('renders deleted messages with muted "[deleted]" style', () => {
    const messages = [{ from: 'alice', text: '[deleted]', is_deleted: true }];
    const { container } = render(<MessageList messages={messages} />);
    expect(container.querySelector('.msg-deleted-text')).toBeInTheDocument();
    expect(container.querySelector('.msg-deleted-text').textContent).toBe('[deleted]');
  });

  it('does not render edit/delete actions for deleted messages', () => {
    const messages = [{ from: 'testuser', text: '[deleted]', is_deleted: true, msg_id: 'msg1' }];
    const { container } = render(<MessageList messages={messages} currentUser="testuser" />);
    expect(container.querySelector('.msg-actions')).toBeNull();
  });

  // ── Phase 1: Edited badge ───────────────────────────────────────────────

  it('renders "(edited)" badge when edited_at is present', () => {
    const messages = [{ from: 'alice', text: 'updated text', edited_at: '2024-01-01T00:00:00Z', msg_id: 'msg1' }];
    render(<MessageList messages={messages} />);
    expect(screen.getByText('(edited)')).toBeInTheDocument();
  });

  it('does not render "(edited)" badge when edited_at is absent', () => {
    const messages = [{ from: 'alice', text: 'normal message', msg_id: 'msg1' }];
    render(<MessageList messages={messages} />);
    expect(screen.queryByText('(edited)')).toBeNull();
  });

  // ── Phase 1: Edit / Delete action buttons ──────────────────────────────

  it('shows edit and delete buttons for own messages', () => {
    const messages = [{ from: 'testuser', text: 'my message', msg_id: 'msg1' }];
    const { container } = render(
      <MessageList messages={messages} currentUser="testuser" onEditMessage={vi.fn()} onDeleteMessage={vi.fn()} />
    );
    const actions = container.querySelector('.msg-actions');
    expect(actions).toBeInTheDocument();
    const buttons = actions.querySelectorAll('.msg-action-btn');
    expect(buttons).toHaveLength(2);
  });

  it('does not show edit/delete buttons for other users\' messages', () => {
    const messages = [{ from: 'alice', text: 'alice message', msg_id: 'msg1' }];
    const { container } = render(
      <MessageList messages={messages} currentUser="testuser" onEditMessage={vi.fn()} onDeleteMessage={vi.fn()} />
    );
    expect(container.querySelector('.msg-actions')).toBeNull();
  });

  it('calls onEditMessage with the message when edit button is clicked', async () => {
    const onEditMessage = vi.fn();
    const user = userEvent.setup();
    const msg = { from: 'testuser', text: 'my message', msg_id: 'msg1' };
    render(
      <MessageList messages={[msg]} currentUser="testuser" onEditMessage={onEditMessage} onDeleteMessage={vi.fn()} />
    );
    await user.click(screen.getByTitle('Edit'));
    expect(onEditMessage).toHaveBeenCalledWith(expect.objectContaining({ msg_id: 'msg1' }));
  });

  it('calls onDeleteMessage with the message when delete button is clicked', async () => {
    const onDeleteMessage = vi.fn();
    const user = userEvent.setup();
    const msg = { from: 'testuser', text: 'my message', msg_id: 'msg1' };
    render(
      <MessageList messages={[msg]} currentUser="testuser" onEditMessage={vi.fn()} onDeleteMessage={onDeleteMessage} />
    );
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
    const { container } = render(<MessageList messages={messages} currentUser="testuser" />);
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
    const { container } = render(<MessageList messages={messages} currentUser="testuser" />);
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
    render(
      <MessageList messages={messages} currentUser="testuser" onAddReaction={onAddReaction} onRemoveReaction={vi.fn()} />
    );
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
    render(
      <MessageList messages={messages} currentUser="testuser" onAddReaction={vi.fn()} onRemoveReaction={onRemoveReaction} />
    );
    await user.click(screen.getByTitle('testuser'));
    expect(onRemoveReaction).toHaveBeenCalledWith('msg1', '👍');
  });

  it('renders the add-reaction (+) button when onAddReaction is provided', () => {
    const messages = [{ from: 'alice', text: 'hi', msg_id: 'msg1', reactions: [] }];
    const { container } = render(
      <MessageList messages={messages} currentUser="testuser" onAddReaction={vi.fn()} />
    );
    expect(container.querySelector('.reaction-add-btn')).toBeInTheDocument();
  });
});
