import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: { username: 'testuser', is_global_admin: false },
  })),
}));

vi.mock('../../components/common/Logo', () => ({
  default: () => <span data-testid="logo">Logo</span>,
}));

vi.mock('../../components/settings/ProfileSection', () => ({
  default: () => <div data-testid="profile-section">ProfileSection</div>,
}));

vi.mock('../../components/settings/TwoFactorSetup', () => ({
  default: () => <div data-testid="two-factor-setup">TwoFactorSetup</div>,
}));

import SettingsPage from '../SettingsPage';

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function renderSettingsPage() {
    return render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
  }

  it('renders the settings page with title', () => {
    renderSettingsPage();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('renders Logo in the header', () => {
    renderSettingsPage();
    expect(screen.getByTestId('logo')).toBeInTheDocument();
  });

  it('renders Profile section', () => {
    renderSettingsPage();
    expect(screen.getByText('Profile')).toBeInTheDocument();
    expect(screen.getByTestId('profile-section')).toBeInTheDocument();
  });

  it('renders Security section with TwoFactorSetup', () => {
    renderSettingsPage();
    expect(screen.getByText('Security')).toBeInTheDocument();
    expect(screen.getByTestId('two-factor-setup')).toBeInTheDocument();
  });

  it('Back to Chat button navigates to /chat', async () => {
    const user = userEvent.setup();
    renderSettingsPage();

    await user.click(screen.getByTestId('back-to-chat'));
    expect(mockNavigate).toHaveBeenCalledWith('/chat');
  });

  it('adds page-active class on mount', () => {
    renderSettingsPage();
    expect(document.body.classList.contains('page-active')).toBe(true);
  });

  it('removes page-active class on unmount', () => {
    const { unmount } = renderSettingsPage();
    unmount();
    expect(document.body.classList.contains('page-active')).toBe(false);
  });
});
