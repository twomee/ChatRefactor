import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PMList from '../PMList';

describe('PMList', () => {
  it('shows section title', () => {
    render(<PMList onSelectPM={vi.fn()} />);
    expect(screen.getByText('Private Messages')).toBeInTheDocument();
  });

  it('shows empty state when no threads exist', () => {
    render(<PMList threads={{}} onSelectPM={vi.fn()} />);
    expect(screen.getByText('No conversations yet')).toBeInTheDocument();
  });

  it('renders a thread entry for each conversation', () => {
    const threads = {
      alice: [{ text: 'hi' }],
      bob: [{ text: 'hey' }],
    };
    render(<PMList threads={threads} pmUnread={{}} onSelectPM={vi.fn()} />);
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('bob')).toBeInTheDocument();
  });

  it('shows unread badge for unread messages', () => {
    const threads = { alice: [{ text: 'hi' }] };
    render(<PMList threads={threads} pmUnread={{ alice: 3 }} onSelectPM={vi.fn()} />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('caps unread badge at 99+', () => {
    const threads = { alice: [{ text: 'hi' }] };
    render(<PMList threads={threads} pmUnread={{ alice: 200 }} onSelectPM={vi.fn()} />);
    expect(screen.getByText('99+')).toBeInTheDocument();
  });

  it('calls onSelectPM when clicking a thread', async () => {
    const user = userEvent.setup();
    const onSelectPM = vi.fn();
    const threads = { alice: [{ text: 'hi' }] };
    render(<PMList threads={threads} pmUnread={{}} onSelectPM={onSelectPM} />);

    await user.click(screen.getByText('alice'));
    expect(onSelectPM).toHaveBeenCalledWith('alice');
  });

  it('renders avatar initials for usernames', () => {
    const threads = { alice: [{ text: 'hi' }] };
    render(<PMList threads={threads} pmUnread={{}} onSelectPM={vi.fn()} />);
    expect(screen.getByText('AL')).toBeInTheDocument();
  });
});
