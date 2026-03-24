import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PMView from '../PMView';

// Mock fileApi used by MessageList
vi.mock('../../../services/fileApi', () => ({
  downloadFile: vi.fn(),
}));

describe('PMView', () => {
  it('renders header with username and "Private conversation" label', () => {
    render(<PMView username="alice" messages={[]} onSend={vi.fn()} />);
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('Private conversation')).toBeInTheDocument();
  });

  it('renders avatar initials from username', () => {
    render(<PMView username="bob" messages={[]} onSend={vi.fn()} />);
    expect(screen.getByText('BO')).toBeInTheDocument();
  });

  it('renders placeholder with username', () => {
    render(<PMView username="alice" messages={[]} onSend={vi.fn()} />);
    expect(screen.getByPlaceholderText('Message alice...')).toBeInTheDocument();
  });

  it('send button is disabled when input is empty', () => {
    render(<PMView username="alice" messages={[]} onSend={vi.fn()} />);
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
  });

  it('calls onSend with trimmed text when clicking Send', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<PMView username="alice" messages={[]} onSend={onSend} />);

    await user.type(screen.getByPlaceholderText('Message alice...'), '  hello  ');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(onSend).toHaveBeenCalledWith('hello');
  });

  it('sends on Enter key press (not Shift+Enter)', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<PMView username="alice" messages={[]} onSend={onSend} />);

    const input = screen.getByPlaceholderText('Message alice...');
    await user.type(input, 'hello');
    await user.keyboard('{Enter}');

    expect(onSend).toHaveBeenCalledWith('hello');
  });

  it('clears input after sending', async () => {
    const user = userEvent.setup();
    render(<PMView username="alice" messages={[]} onSend={vi.fn()} />);

    const input = screen.getByPlaceholderText('Message alice...');
    await user.type(input, 'hello');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(input).toHaveValue('');
  });
});
