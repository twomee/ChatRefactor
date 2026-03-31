import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import AuthenticatedShell from '../AuthenticatedShell';

vi.mock('react-router-dom', () => ({
  Navigate: ({ to }) => <div data-testid="navigate" data-to={to} />,
}));

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../context/PMContext', () => ({
  PMProvider: ({ children }) => <div data-testid="pm-provider">{children}</div>,
}));

vi.mock('../ChatConnectionLayer', () => ({
  default: () => <div data-testid="chat-connection-layer" />,
}));

import { useAuth } from '../../context/AuthContext';

describe('AuthenticatedShell', () => {
  it('redirects to /login when user is not authenticated', () => {
    useAuth.mockReturnValue({ user: null });
    render(<AuthenticatedShell />);
    const nav = screen.getByTestId('navigate');
    expect(nav).toBeInTheDocument();
    expect(nav).toHaveAttribute('data-to', '/login');
  });

  it('renders PMProvider and ChatConnectionLayer when user is authenticated', () => {
    useAuth.mockReturnValue({ user: { username: 'alice' } });
    render(<AuthenticatedShell />);
    expect(screen.getByTestId('pm-provider')).toBeInTheDocument();
    expect(screen.getByTestId('chat-connection-layer')).toBeInTheDocument();
    expect(screen.queryByTestId('navigate')).toBeNull();
  });
});
