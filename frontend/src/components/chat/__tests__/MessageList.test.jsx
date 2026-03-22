import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import MessageList from '../MessageList';

// Mock fileApi to avoid import side effects
vi.mock('../../../services/fileApi', () => ({
  getDownloadUrl: vi.fn((fileId) => `http://localhost:8000/files/download/${fileId}?token=test`),
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
    expect(link.closest('a')).toHaveAttribute('href', expect.stringContaining('/files/download/f1'));
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
});
