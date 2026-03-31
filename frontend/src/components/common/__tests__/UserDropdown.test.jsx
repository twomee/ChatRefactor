import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import UserDropdown from '../UserDropdown';

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

// ── Helpers ───────────────────────────────────────────────────────────────────

const defaultUser = { username: 'testuser', is_global_admin: false };
const adminUser = { username: 'adminuser', is_global_admin: true };

function renderDropdown({ user = defaultUser, onLogout = vi.fn() } = {}) {
  const logoutFn = onLogout;
  render(
    <MemoryRouter>
      <UserDropdown user={user} onLogout={logoutFn} />
    </MemoryRouter>,
  );
  return { logoutFn };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('UserDropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders username and avatar initials', () => {
    renderDropdown();
    expect(screen.getByText('testuser')).toBeInTheDocument();
    expect(screen.getByText('TE')).toBeInTheDocument(); // first two chars uppercased
  });

  it('opens dropdown menu on trigger click', async () => {
    const user = userEvent.setup();
    renderDropdown();

    expect(screen.queryByTestId('user-dropdown-menu')).toBeNull();
    await user.click(screen.getByTestId('user-dropdown-trigger'));
    expect(screen.getByTestId('user-dropdown-menu')).toBeInTheDocument();
  });

  it('closes dropdown on click outside', async () => {
    const user = userEvent.setup();
    renderDropdown();

    await user.click(screen.getByTestId('user-dropdown-trigger'));
    expect(screen.getByTestId('user-dropdown-menu')).toBeInTheDocument();

    // Click outside the dropdown
    await user.click(document.body);
    expect(screen.queryByTestId('user-dropdown-menu')).toBeNull();
  });

  it('closes dropdown on Escape key', async () => {
    const user = userEvent.setup();
    renderDropdown();

    await user.click(screen.getByTestId('user-dropdown-trigger'));
    expect(screen.getByTestId('user-dropdown-menu')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByTestId('user-dropdown-menu')).toBeNull();
  });

  it('shows Settings item that navigates to /settings', async () => {
    const user = userEvent.setup();
    renderDropdown();

    await user.click(screen.getByTestId('user-dropdown-trigger'));
    expect(screen.getByText('Settings')).toBeInTheDocument();

    await user.click(screen.getByTestId('dropdown-settings'));
    expect(mockNavigate).toHaveBeenCalledWith('/settings');
    // Menu should close after navigation
    expect(screen.queryByTestId('user-dropdown-menu')).toBeNull();
  });

  it('shows Admin Panel only when user is_global_admin', async () => {
    const user = userEvent.setup();
    renderDropdown({ user: adminUser });

    await user.click(screen.getByTestId('user-dropdown-trigger'));
    expect(screen.getByText('Admin Panel')).toBeInTheDocument();
  });

  it('does NOT show Admin Panel for non-admin users', async () => {
    const user = userEvent.setup();
    renderDropdown({ user: defaultUser });

    await user.click(screen.getByTestId('user-dropdown-trigger'));
    expect(screen.queryByText('Admin Panel')).toBeNull();
  });

  it('Admin Panel navigates to /admin', async () => {
    const user = userEvent.setup();
    renderDropdown({ user: adminUser });

    await user.click(screen.getByTestId('user-dropdown-trigger'));
    await user.click(screen.getByTestId('dropdown-admin'));
    expect(mockNavigate).toHaveBeenCalledWith('/admin');
  });

  it('shows Logout item that calls onLogout', async () => {
    const user = userEvent.setup();
    const onLogout = vi.fn();
    renderDropdown({ onLogout });

    await user.click(screen.getByTestId('user-dropdown-trigger'));
    expect(screen.getByText('Logout')).toBeInTheDocument();

    await user.click(screen.getByTestId('dropdown-logout'));
    expect(onLogout).toHaveBeenCalledOnce();
  });

  it('closes menu after clicking any item', async () => {
    const user = userEvent.setup();
    renderDropdown();

    await user.click(screen.getByTestId('user-dropdown-trigger'));
    await user.click(screen.getByTestId('dropdown-settings'));
    expect(screen.queryByTestId('user-dropdown-menu')).toBeNull();
  });

  it('toggles dropdown open and closed on trigger clicks', async () => {
    const user = userEvent.setup();
    renderDropdown();

    // Open
    await user.click(screen.getByTestId('user-dropdown-trigger'));
    expect(screen.getByTestId('user-dropdown-menu')).toBeInTheDocument();

    // Close
    await user.click(screen.getByTestId('user-dropdown-trigger'));
    expect(screen.queryByTestId('user-dropdown-menu')).toBeNull();
  });
});
