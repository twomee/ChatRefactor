import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ConnectionStatus from '../ConnectionStatus';

describe('ConnectionStatus', () => {
  it('renders nothing when status is "connected"', () => {
    const { container } = render(<ConnectionStatus status="connected" />);
    expect(container.querySelector('.connection-status')).toBeNull();
  });

  it('shows "Reconnecting..." when status is "reconnecting"', () => {
    render(<ConnectionStatus status="reconnecting" />);
    expect(screen.getByText('Reconnecting...')).toBeInTheDocument();
  });

  it('shows "Disconnected" when status is "disconnected"', () => {
    render(<ConnectionStatus status="disconnected" />);
    expect(screen.getByText('Disconnected')).toBeInTheDocument();
  });

  it('applies correct CSS class for reconnecting', () => {
    const { container } = render(<ConnectionStatus status="reconnecting" />);
    expect(container.querySelector('.connection-status')).toHaveClass('reconnecting');
  });

  it('applies correct CSS class for disconnected', () => {
    const { container } = render(<ConnectionStatus status="disconnected" />);
    expect(container.querySelector('.connection-status')).toHaveClass('disconnected');
  });

  it('renders the pulsing dot indicator', () => {
    const { container } = render(<ConnectionStatus status="reconnecting" />);
    expect(container.querySelector('.connection-dot')).toBeInTheDocument();
  });
});
