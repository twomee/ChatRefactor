import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../../services/authApi', () => ({
  getProfile: vi.fn(),
  updateEmail: vi.fn(),
  updatePassword: vi.fn(),
}));

import * as authApi from '../../../services/authApi';
import ProfileSection from '../ProfileSection';

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderProfileSection() {
  return render(<ProfileSection />);
}

// Helper to scope queries within the Change Email form
function emailForm() {
  return within(screen.getByRole('heading', { name: 'Change Email' }).closest('form'));
}

// Helper to scope queries within the Change Password form
function passwordForm() {
  return within(screen.getByRole('heading', { name: 'Change Password' }).closest('form'));
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ProfileSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authApi.getProfile.mockResolvedValue({ username: 'testuser', email: 'test@example.com' });
  });

  it('renders Change Email and Change Password headings', () => {
    renderProfileSection();
    expect(screen.getByText('Change Email')).toBeInTheDocument();
    expect(screen.getByText('Change Password')).toBeInTheDocument();
  });

  it('fetches and displays current email on mount', async () => {
    renderProfileSection();
    await waitFor(() => {
      expect(screen.getByText(/Current email:/)).toBeInTheDocument();
      expect(screen.getByText('test@example.com')).toBeInTheDocument();
    });
  });

  it('does not show current email when profile has no email', async () => {
    authApi.getProfile.mockResolvedValue({ username: 'testuser', email: null });
    renderProfileSection();
    await waitFor(() => {
      expect(authApi.getProfile).toHaveBeenCalled();
    });
    expect(screen.queryByText(/Current email:/)).not.toBeInTheDocument();
  });

  it('does not call updateEmail when new email field is empty', async () => {
    const user = userEvent.setup();
    renderProfileSection();
    await waitFor(() => expect(authApi.getProfile).toHaveBeenCalled());

    // Submit without filling in any fields — HTML5 required prevents submission
    // so updateEmail should never be called
    await user.click(emailForm().getByRole('button', { name: /update email/i }));
    expect(authApi.updateEmail).not.toHaveBeenCalled();
  });

  it('calls updateEmail and shows success on valid email submit', async () => {
    authApi.updateEmail.mockResolvedValue({ message: 'Email updated' });
    const user = userEvent.setup();
    renderProfileSection();
    await waitFor(() => expect(authApi.getProfile).toHaveBeenCalled());

    const ef = emailForm();
    await user.type(ef.getByLabelText('New Email'), 'new@example.com');
    await user.type(ef.getByLabelText('Current Password'), 'x-cur');
    await user.click(ef.getByRole('button', { name: /update email/i }));

    await waitFor(() => {
      expect(authApi.updateEmail).toHaveBeenCalledWith('new@example.com', 'x-cur');
      expect(screen.getByText('Email updated successfully.')).toBeInTheDocument();
    });
  });

  it('shows API error message on email update failure', async () => {
    authApi.updateEmail.mockRejectedValue({ response: { data: { detail: 'Wrong password' } } });
    const user = userEvent.setup();
    renderProfileSection();
    await waitFor(() => expect(authApi.getProfile).toHaveBeenCalled());

    const ef = emailForm();
    await user.type(ef.getByLabelText('New Email'), 'new@example.com');
    await user.type(ef.getByLabelText('Current Password'), 'x-wrong');
    await user.click(ef.getByRole('button', { name: /update email/i }));

    await waitFor(() => {
      expect(screen.getByText('Wrong password')).toBeInTheDocument();
    });
  });

  it('shows error when passwords do not match', async () => {
    const user = userEvent.setup();
    renderProfileSection();
    await waitFor(() => expect(authApi.getProfile).toHaveBeenCalled());

    const pf = passwordForm();
    await user.type(pf.getByLabelText('Current Password'), 'x-cur');
    await user.type(pf.getByLabelText('New Password'), 'x-new-1');
    await user.type(pf.getByLabelText('Confirm New Password'), 'x-new-2');
    await user.click(pf.getByRole('button', { name: /update password/i }));

    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument();
  });

  it('shows error when new password is too short', async () => {
    const user = userEvent.setup();
    renderProfileSection();
    await waitFor(() => expect(authApi.getProfile).toHaveBeenCalled());

    const pf = passwordForm();
    await user.type(pf.getByLabelText('Current Password'), 'x-cur');
    await user.type(pf.getByLabelText('New Password'), 'abc');
    await user.type(pf.getByLabelText('Confirm New Password'), 'abc');
    await user.click(pf.getByRole('button', { name: /update password/i }));

    expect(screen.getByText('New password must be at least 8 characters.')).toBeInTheDocument();
  });

  it('calls updatePassword and shows success on valid submit', async () => {
    authApi.updatePassword.mockResolvedValue({ message: 'Password updated' });
    const user = userEvent.setup();
    renderProfileSection();
    await waitFor(() => expect(authApi.getProfile).toHaveBeenCalled());

    const pf = passwordForm();
    await user.type(pf.getByLabelText('Current Password'), 'x-cur-val');
    await user.type(pf.getByLabelText('New Password'), 'x-new-val');
    await user.type(pf.getByLabelText('Confirm New Password'), 'x-new-val');
    await user.click(pf.getByRole('button', { name: /update password/i }));

    await waitFor(() => {
      expect(authApi.updatePassword).toHaveBeenCalledWith('x-cur-val', 'x-new-val');
      expect(screen.getByText('Password updated successfully.')).toBeInTheDocument();
    });
  });

  it('shows API error message on password update failure', async () => {
    authApi.updatePassword.mockRejectedValue({ response: { data: { detail: 'Incorrect current password' } } });
    const user = userEvent.setup();
    renderProfileSection();
    await waitFor(() => expect(authApi.getProfile).toHaveBeenCalled());

    const pf = passwordForm();
    await user.type(pf.getByLabelText('Current Password'), 'x-wrong');
    await user.type(pf.getByLabelText('New Password'), 'x-new-val');
    await user.type(pf.getByLabelText('Confirm New Password'), 'x-new-val');
    await user.click(pf.getByRole('button', { name: /update password/i }));

    await waitFor(() => {
      expect(screen.getByText('Incorrect current password')).toBeInTheDocument();
    });
  });
});
