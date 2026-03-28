import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import TypingIndicator from '../TypingIndicator';

describe('TypingIndicator', () => {
  it('renders an empty container when typingUsers is undefined', () => {
    const { container } = render(<TypingIndicator />);
    const el = container.querySelector('.typing-indicator');
    expect(el).toBeInTheDocument();
    expect(el.textContent).toBe('');
  });

  it('renders an empty container when typingUsers is an empty object', () => {
    const { container } = render(<TypingIndicator typingUsers={{}} />);
    const el = container.querySelector('.typing-indicator');
    expect(el).toBeInTheDocument();
    expect(el.textContent).toBe('');
  });

  it('renders singular text when one user is typing', () => {
    render(<TypingIndicator typingUsers={{ alice: Date.now() }} />);
    expect(screen.getByText(/alice is typing/)).toBeInTheDocument();
  });

  it('renders plural text when multiple users are typing', () => {
    render(<TypingIndicator typingUsers={{ alice: Date.now(), bob: Date.now() }} />);
    expect(screen.getByText(/alice, bob are typing/)).toBeInTheDocument();
  });

  it('renders animated dots', () => {
    const { container } = render(<TypingIndicator typingUsers={{ alice: Date.now() }} />);
    const dots = container.querySelectorAll('.typing-dots span');
    expect(dots).toHaveLength(3);
  });
});
