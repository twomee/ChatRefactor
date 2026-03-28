import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import MessageList from '../MessageList';

// Mock fileApi to avoid import side effects
vi.mock('../../../services/fileApi', () => ({
  downloadFile: vi.fn(),
}));

// Mock useAuthenticatedImage so InlineImage renders deterministically in tests
vi.mock('../../../hooks/useAuthenticatedImage', () => ({
  default: vi.fn((fileId) => {
    // Return a fake blob URL to simulate a successful image load
    if (fileId) return { url: `blob:mock-url-${fileId}`, error: false };
    return { url: null, error: false };
  }),
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
    expect(link.closest('a')).toBeInTheDocument();
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

  it('renders image files with inline preview component', () => {
    const messages = [{ isFile: true, from: 'bob', text: 'photo.png', fileId: 'f1', fileSize: 4096 }];
    render(<MessageList messages={messages} />);
    // InlineImage with mocked hook should render an <img> with the blob URL
    const img = screen.getByAltText('photo.png');
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute('src', 'blob:mock-url-f1');
    expect(img).toHaveClass('msg-inline-image');
  });

  it('still renders non-image files as download links', () => {
    const messages = [{ isFile: true, from: 'bob', text: 'report.pdf', fileId: 'f1', fileSize: 2048 }];
    render(<MessageList messages={messages} />);
    expect(screen.getByText('report.pdf')).toBeInTheDocument();
    // Should be an anchor link, not an img
    expect(screen.getByText('report.pdf').closest('a')).toBeInTheDocument();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('does not leak JWT token in image src URLs', () => {
    const messages = [{ isFile: true, from: 'bob', text: 'photo.jpg', fileId: 'f2', fileSize: 8192 }];
    const { container } = render(<MessageList messages={messages} />);
    const imgs = container.querySelectorAll('img');
    imgs.forEach(img => {
      expect(img.src).not.toContain('token=');
      expect(img.src).toMatch(/^blob:/);
    });
  });
});
