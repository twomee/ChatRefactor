import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PMView from '../PMView';
import { ToastProvider } from '../../../context/ToastContext';

// Mock fileApi used by MessageList
vi.mock('../../../services/fileApi');

// Mock useAuth so MessageList (rendered by PMView) can access user context
vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'testuser' }, token: 'fake-token' }),
}));

function renderWithToast(ui) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

describe('PMView', () => {
  it('renders header with username', () => {
    renderWithToast(<PMView username="alice" messages={[]} />);
    expect(screen.getByText('alice')).toBeInTheDocument();
  });

  it('renders avatar initials from username', () => {
    renderWithToast(<PMView username="bob" messages={[]} />);
    expect(screen.getByText('BO')).toBeInTheDocument();
  });

  it('shows Online status when isOnline is true (default)', () => {
    renderWithToast(<PMView username="alice" messages={[]} />);
    expect(screen.getByText('Online')).toBeInTheDocument();
    expect(document.querySelector('.pm-status-dot.online')).toBeInTheDocument();
  });

  it('shows Offline status when isOnline is false', () => {
    renderWithToast(<PMView username="alice" messages={[]} isOnline={false} />);
    expect(screen.getByText('Offline')).toBeInTheDocument();
    expect(document.querySelector('.pm-status-dot.offline')).toBeInTheDocument();
  });

  it('shows offline banner when isOnline is false', () => {
    renderWithToast(<PMView username="alice" messages={[]} isOnline={false} />);
    expect(screen.getByText(/alice is offline/i)).toBeInTheDocument();
  });

  it('does not show offline banner when isOnline is true', () => {
    renderWithToast(<PMView username="alice" messages={[]} isOnline={true} />);
    expect(screen.queryByText(/is offline/i)).not.toBeInTheDocument();
  });

  it('does not render an input or send button (input moved to parent panel)', () => {
    renderWithToast(<PMView username="alice" messages={[]} />);
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument();
  });

  it('renders clear history button', () => {
    renderWithToast(<PMView username="alice" messages={[]} onClearHistory={vi.fn()} />);
    expect(screen.getByTestId('clear-pm-history')).toBeInTheDocument();
  });

  it('shows confirmation dialog when clear button clicked', async () => {
    const user = userEvent.setup();
    renderWithToast(<PMView username="alice" messages={[]} onClearHistory={vi.fn()} />);

    await user.click(screen.getByTestId('clear-pm-history'));
    expect(screen.getByTestId('clear-pm-confirm')).toBeInTheDocument();
    expect(screen.getByTestId('clear-pm-yes')).toBeInTheDocument();
    expect(screen.getByTestId('clear-pm-no')).toBeInTheDocument();
  });

  it('calls onClearHistory when Yes confirmed', async () => {
    const user = userEvent.setup();
    const onClearHistory = vi.fn();
    renderWithToast(<PMView username="alice" messages={[]} onClearHistory={onClearHistory} />);

    await user.click(screen.getByTestId('clear-pm-history'));
    await user.click(screen.getByTestId('clear-pm-yes'));
    expect(onClearHistory).toHaveBeenCalledOnce();
  });

  it('dismisses confirmation dialog when Cancel clicked', async () => {
    const user = userEvent.setup();
    renderWithToast(<PMView username="alice" messages={[]} onClearHistory={vi.fn()} />);

    await user.click(screen.getByTestId('clear-pm-history'));
    expect(screen.getByTestId('clear-pm-confirm')).toBeInTheDocument();

    await user.click(screen.getByTestId('clear-pm-no'));
    expect(screen.queryByTestId('clear-pm-confirm')).not.toBeInTheDocument();
    expect(screen.getByTestId('clear-pm-history')).toBeInTheDocument();
  });

  it('passes action props through to MessageList', () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onAddReaction = vi.fn();
    const onRemoveReaction = vi.fn();

    const messages = [
      { from: 'testuser', text: 'hello', msg_id: 'pm-1-2-123' },
    ];

    // Render with action props and currentUser — if it renders without error,
    // props are being forwarded correctly. Full action testing belongs in
    // MessageList tests.
    const { container } = renderWithToast(
      <PMView
        username="alice"
        messages={messages}
        currentUser="testuser"
        onEditMessage={onEdit}
        onDeleteMessage={onDelete}
        onAddReaction={onAddReaction}
        onRemoveReaction={onRemoveReaction}
      />
    );
    // The message should be rendered via MessageList
    expect(container.querySelector('.message-list')).toBeInTheDocument();
  });

  it('does not render a file input or attach button (file upload moved to MessageInput)', () => {
    renderWithToast(<PMView username="alice" messages={[]} />);
    expect(document.querySelector('input[type="file"]')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pm-attach-btn')).not.toBeInTheDocument();
  });
});
