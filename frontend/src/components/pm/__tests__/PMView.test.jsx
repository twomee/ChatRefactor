import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import PMView from '../PMView';

// Mock fileApi used by MessageList
vi.mock('../../../services/fileApi', () => ({
  downloadFile: vi.fn(),
}));

describe('PMView', () => {
  it('renders header with username', () => {
    render(<PMView username="alice" messages={[]} />);
    expect(screen.getByText('alice')).toBeInTheDocument();
  });

  it('renders avatar initials from username', () => {
    render(<PMView username="bob" messages={[]} />);
    expect(screen.getByText('BO')).toBeInTheDocument();
  });

  it('shows Online status when isOnline is true (default)', () => {
    render(<PMView username="alice" messages={[]} />);
    expect(screen.getByText('Online')).toBeInTheDocument();
    expect(document.querySelector('.pm-status-dot.online')).toBeInTheDocument();
  });

  it('shows Offline status when isOnline is false', () => {
    render(<PMView username="alice" messages={[]} isOnline={false} />);
    expect(screen.getByText('Offline')).toBeInTheDocument();
    expect(document.querySelector('.pm-status-dot.offline')).toBeInTheDocument();
  });

  it('shows offline banner when isOnline is false', () => {
    render(<PMView username="alice" messages={[]} isOnline={false} />);
    expect(screen.getByText(/alice is offline/i)).toBeInTheDocument();
  });

  it('does not show offline banner when isOnline is true', () => {
    render(<PMView username="alice" messages={[]} isOnline={true} />);
    expect(screen.queryByText(/is offline/i)).not.toBeInTheDocument();
  });

  it('does not render an input or send button (input moved to parent panel)', () => {
    render(<PMView username="alice" messages={[]} />);
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument();
  });
});
