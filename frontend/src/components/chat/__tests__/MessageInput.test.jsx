import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MessageInput from '../MessageInput';

describe('MessageInput', () => {
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
});
