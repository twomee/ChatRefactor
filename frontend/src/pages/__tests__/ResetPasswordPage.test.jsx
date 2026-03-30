import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../services/authApi', () => ({
  resetPassword: vi.fn(),
}));

vi.mock('../../components/common/Logo', () => ({
  default: () => <span data-testid="logo">Logo</span>,
}));

import * as authApi from '../../services/authApi';
import ResetPasswordPage from '../ResetPasswordPage';

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderWithToken(token = 'x-tok') {
  const url = token ? `/reset-password?token=${token}` : '/reset-password';
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ResetPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the reset password form with logo', () => {
    renderWithToken();
    expect(screen.getByTestId('logo')).toBeInTheDocument();
    expect(screen.getByText('Reset Your Password')).toBeInTheDocument();
    expect(screen.getByTestId('reset-new-password')).toBeInTheDocument();
    expect(screen.getByTestId('reset-confirm-password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reset password/i })).toBeInTheDocument();
  });

  it('shows error when passwords do not match', async () => {
    const user = userEvent.setup();
    renderWithToken();

    await user.type(screen.getByTestId('reset-new-password'), 'x-val-a');
    await user.type(screen.getByTestId('reset-confirm-password'), 'x-val-b');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument();
  });

  it('shows error when password is too short', async () => {
    const user = userEvent.setup();
    renderWithToken();

    await user.type(screen.getByTestId('reset-new-password'), 'abc');
    await user.type(screen.getByTestId('reset-confirm-password'), 'abc');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    expect(screen.getByText('Password must be at least 6 characters.')).toBeInTheDocument();
  });

  it('shows error when no token in URL', async () => {
    const user = userEvent.setup();
    renderWithToken('');

    await user.type(screen.getByTestId('reset-new-password'), 'x-new-val');
    await user.type(screen.getByTestId('reset-confirm-password'), 'x-new-val');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    expect(screen.getByText('Invalid or missing reset token.')).toBeInTheDocument();
  });

  it('calls resetPassword API and shows success message on valid submit', async () => {
    authApi.resetPassword.mockResolvedValue({ message: 'ok' });
    const user = userEvent.setup();
    renderWithToken('x-tok-a');

    await user.type(screen.getByTestId('reset-new-password'), 'x-new-val');
    await user.type(screen.getByTestId('reset-confirm-password'), 'x-new-val');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(authApi.resetPassword).toHaveBeenCalledWith('x-tok-a', 'x-new-val');
      expect(screen.getByText(/password has been reset successfully/i)).toBeInTheDocument();
    });
  });

  it('shows Back to Login link after success', async () => {
    authApi.resetPassword.mockResolvedValue({ message: 'ok' });
    const user = userEvent.setup();
    renderWithToken('x-tok-a');

    await user.type(screen.getByTestId('reset-new-password'), 'x-new-val');
    await user.type(screen.getByTestId('reset-confirm-password'), 'x-new-val');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText('Back to Login')).toBeInTheDocument();
    });
  });

  it('shows API error message on reset failure', async () => {
    authApi.resetPassword.mockRejectedValue({
      response: { data: { detail: 'Token has expired' } },
    });
    const user = userEvent.setup();
    renderWithToken('x-tok-e');

    await user.type(screen.getByTestId('reset-new-password'), 'x-new-val');
    await user.type(screen.getByTestId('reset-confirm-password'), 'x-new-val');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText('Token has expired')).toBeInTheDocument();
    });
  });

  it('shows fallback error when API response has no detail', async () => {
    authApi.resetPassword.mockRejectedValue(new Error('Network error'));
    const user = userEvent.setup();
    renderWithToken('x-tok-s');

    await user.type(screen.getByTestId('reset-new-password'), 'x-new-val');
    await user.type(screen.getByTestId('reset-confirm-password'), 'x-new-val');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText('Failed to reset password. The link may have expired.')).toBeInTheDocument();
    });
  });
});
