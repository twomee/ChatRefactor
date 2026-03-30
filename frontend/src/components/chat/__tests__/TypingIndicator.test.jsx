import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import TypingIndicator from '../TypingIndicator';

describe('TypingIndicator', () => {
  it('renders an empty container when typingUsers is undefined', () => {
    const { container } = render(<TypingIndicator typingUsers={undefined} />);
    const indicator = container.querySelector('.typing-indicator');
    expect(indicator).toBeInTheDocument();
    expect(indicator.textContent).toBe('');
  });

  it('renders an empty container when typingUsers is an empty object', () => {
    const { container } = render(<TypingIndicator typingUsers={{}} />);
    const indicator = container.querySelector('.typing-indicator');
    expect(indicator).toBeInTheDocument();
    expect(indicator.textContent).toBe('');
  });

  it('renders singular "is typing" label for one user', () => {
    render(<TypingIndicator typingUsers={{ alice: Date.now() }} />);
    expect(screen.getByText(/alice is typing/i)).toBeInTheDocument();
  });

  it('renders plural "are typing" label for multiple users', () => {
    render(<TypingIndicator typingUsers={{ alice: Date.now(), bob: Date.now() }} />);
    expect(screen.getByText(/alice, bob are typing/i)).toBeInTheDocument();
  });

  it('renders the animated typing dots when users are typing', () => {
    const { container } = render(<TypingIndicator typingUsers={{ alice: Date.now() }} />);
    const dots = container.querySelector('.typing-dots');
    expect(dots).toBeInTheDocument();
  });

  it('does not render typing dots when no users are typing', () => {
    const { container } = render(<TypingIndicator typingUsers={{}} />);
    expect(container.querySelector('.typing-dots')).toBeNull();
  });
});
