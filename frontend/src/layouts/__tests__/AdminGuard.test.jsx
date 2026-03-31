import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import AdminGuard from '../AdminGuard';

vi.mock('react-router-dom', () => ({
  Navigate: ({ to }) => <div data-testid="navigate" data-to={to} />,
}));

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from '../../context/AuthContext';

describe('AdminGuard', () => {
  it('redirects to /chat when user is not a global admin', () => {
    useAuth.mockReturnValue({ user: { username: 'alice', is_global_admin: false } });
    render(<AdminGuard><div>admin content</div></AdminGuard>);
    const nav = screen.getByTestId('navigate');
    expect(nav).toBeInTheDocument();
    expect(nav).toHaveAttribute('data-to', '/chat');
    expect(screen.queryByText('admin content')).toBeNull();
  });

  it('redirects to /chat when user has no is_global_admin field', () => {
    useAuth.mockReturnValue({ user: { username: 'alice' } });
    render(<AdminGuard><div>admin content</div></AdminGuard>);
    expect(screen.getByTestId('navigate')).toBeInTheDocument();
  });

  it('redirects to /chat when user is null', () => {
    useAuth.mockReturnValue({ user: null });
    render(<AdminGuard><div>admin content</div></AdminGuard>);
    expect(screen.getByTestId('navigate')).toBeInTheDocument();
  });

  it('renders children when user is a global admin', () => {
    useAuth.mockReturnValue({ user: { username: 'admin', is_global_admin: true } });
    render(<AdminGuard><div>admin content</div></AdminGuard>);
    expect(screen.getByText('admin content')).toBeInTheDocument();
    expect(screen.queryByTestId('navigate')).toBeNull();
  });
});
