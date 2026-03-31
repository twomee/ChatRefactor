import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import LoginPage from '../LoginPage';

// Mock dependencies
const mockLogin = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ login: mockLogin }),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/authApi', () => ({
  register: vi.fn(),
  login: vi.fn(),
  verifyLogin2FA: vi.fn(),
  forgotPassword: vi.fn(),
}));

vi.mock('../../components/common/Logo', () => ({
  default: () => <div data-testid="logo">Logo</div>,
}));

import * as authApi from '../../services/authApi';

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function renderPage() {
    return render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
  }

  it('renders sign in and register tabs', () => {
    renderPage();
    const tabs = screen.getAllByRole('button');
    const tabTexts = tabs.map(t => t.textContent);
    expect(tabTexts).toContain('Sign In');
    expect(tabTexts).toContain('Register');
  });

  it('renders username and password inputs', () => {
    renderPage();
    expect(screen.getByPlaceholderText('Username')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Password')).toBeInTheDocument();
  });

  it('shows "Sign In" submit button by default', () => {
    renderPage();
    // Both the tab and submit button say "Sign In" — verify the submit one exists
    const submitButtons = screen.getAllByText('Sign In').filter(el => el.getAttribute('type') === 'submit');
    expect(submitButtons).toHaveLength(1);
    expect(submitButtons[0]).toHaveClass('btn-primary');
  });

  it('switches to register mode and shows "Create Account" button', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByText('Register'));
    expect(screen.getByRole('button', { name: 'Create Account' })).toBeInTheDocument();
  });

  it('calls login API and navigates to /chat on successful login', async () => {
    const user = userEvent.setup();
    authApi.login.mockResolvedValue({
      data: { access_token: 'jwt', username: 'alice', is_global_admin: false },
    });
    renderPage();

    await user.type(screen.getByPlaceholderText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Password'), 'pass123');
    // Click the submit button (type=submit)
    const submitBtn = screen.getAllByText('Sign In').find(el => el.getAttribute('type') === 'submit');
    await user.click(submitBtn);

    await waitFor(() => {
      expect(authApi.login).toHaveBeenCalledWith('alice', 'pass123');
      expect(mockLogin).toHaveBeenCalledWith('jwt', { username: 'alice', is_global_admin: false });
      expect(mockNavigate).toHaveBeenCalledWith('/chat');
    });
  });

  it('calls register API and switches to login mode on success', async () => {
    const user = userEvent.setup();
    authApi.register.mockResolvedValue({ data: {} });
    renderPage();

    await user.click(screen.getByText('Register'));
    await user.type(screen.getByPlaceholderText('Username'), 'newuser');
    await user.type(screen.getByPlaceholderText('Email'), 'new@example.com');
    await user.type(screen.getByPlaceholderText('Password'), 'pass123');
    await user.click(screen.getByRole('button', { name: 'Create Account' }));

    await waitFor(() => {
      expect(authApi.register).toHaveBeenCalledWith('newuser', 'pass123', 'new@example.com');
      expect(screen.getByText('Registered! Now log in.')).toBeInTheDocument();
    });
  });

  it('displays error message on login failure', async () => {
    const user = userEvent.setup();
    authApi.login.mockRejectedValue({
      response: { data: { detail: 'Invalid credentials' } },
    });
    renderPage();

    await user.type(screen.getByPlaceholderText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Password'), 'wrong');
    const submitBtn = screen.getAllByText('Sign In').find(el => el.getAttribute('type') === 'submit');
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
    });
  });

  it('shows generic error when response has no detail', async () => {
    const user = userEvent.setup();
    authApi.login.mockRejectedValue(new Error('Network error'));
    renderPage();

    await user.type(screen.getByPlaceholderText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Password'), 'pass');
    const submitBtn = screen.getAllByText('Sign In').find(el => el.getAttribute('type') === 'submit');
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });
  });

  // ── 2FA tests ───────────────────────────────────────────────────────

  it('shows TOTP code input when login returns requires_2fa', async () => {
    const user = userEvent.setup();
    authApi.login.mockResolvedValue({
      data: { requires_2fa: true, temp_token: 'temp123', message: '2FA required' },
    });
    renderPage();

    await user.type(screen.getByPlaceholderText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Password'), 'pass123');
    const submitBtn = screen.getAllByText('Sign In').find(el => el.getAttribute('type') === 'submit');
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByTestId('totp-input')).toBeInTheDocument();
      expect(screen.getByText('Two-Factor Authentication')).toBeInTheDocument();
      expect(screen.getByText('Verify')).toBeInTheDocument();
    });
  });

  it('completes 2FA login and navigates to /chat', async () => {
    const user = userEvent.setup();
    authApi.login.mockResolvedValue({
      data: { requires_2fa: true, temp_token: 'temp123', message: '2FA required' },
    });
    authApi.verifyLogin2FA.mockResolvedValue({
      data: { access_token: 'jwt2fa', username: 'alice', is_global_admin: false, token_type: 'bearer' },
    });
    renderPage();

    await user.type(screen.getByPlaceholderText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Password'), 'pass123');
    const submitBtn = screen.getAllByText('Sign In').find(el => el.getAttribute('type') === 'submit');
    await user.click(submitBtn);

    await waitFor(() => screen.getByTestId('totp-input'));
    await user.type(screen.getByTestId('totp-input'), '123456');
    await user.click(screen.getByText('Verify'));

    await waitFor(() => {
      expect(authApi.verifyLogin2FA).toHaveBeenCalledWith('temp123', '123456');
      expect(mockLogin).toHaveBeenCalledWith('jwt2fa', { username: 'alice', is_global_admin: false });
      expect(mockNavigate).toHaveBeenCalledWith('/chat');
    });
  });

  it('shows Back to Login button on 2FA screen and returns to login', async () => {
    const user = userEvent.setup();
    authApi.login.mockResolvedValue({
      data: { requires_2fa: true, temp_token: 'temp123', message: '2FA required' },
    });
    renderPage();

    await user.type(screen.getByPlaceholderText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Password'), 'pass123');
    const submitBtn = screen.getAllByText('Sign In').find(el => el.getAttribute('type') === 'submit');
    await user.click(submitBtn);

    await waitFor(() => screen.getByText('Back to Login'));
    await user.click(screen.getByText('Back to Login'));

    // Should be back to the normal login form
    expect(screen.getByPlaceholderText('Username')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Password')).toBeInTheDocument();
  });

  // ── Mode switching ──────────────────────────────────────────────────

  it('switches back to login mode when Sign In tab is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    // Switch to register
    await user.click(screen.getByText('Register'));
    expect(screen.getByRole('button', { name: 'Create Account' })).toBeInTheDocument();

    // Switch back to login
    await user.click(screen.getByText('Sign In'));
    const submitBtns = screen.getAllByText('Sign In').filter(el => el.getAttribute('type') === 'submit');
    expect(submitBtns).toHaveLength(1);
  });

  // ── Forgot password ─────────────────────────────────────────────────

  it('shows forgot password form when "Forgot password?" link is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByText('Forgot password?'));
    expect(screen.getByText('Reset Your Password')).toBeInTheDocument();
    expect(screen.getByTestId('forgot-email-input')).toBeInTheDocument();
  });

  it('calls forgotPassword API and shows success message', async () => {
    const user = userEvent.setup();
    authApi.forgotPassword.mockResolvedValue({ data: {} });
    renderPage();

    await user.click(screen.getByText('Forgot password?'));
    await user.type(screen.getByTestId('forgot-email-input'), 'alice@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(authApi.forgotPassword).toHaveBeenCalledWith('alice@example.com');
      // Always shows the same message to prevent email enumeration
      expect(screen.getByText(/a reset link has been sent/i)).toBeInTheDocument();
    });
  });

  // ── user_id persistence ─────────────────────────────────────────────

  it('stores user_id from login response in user context', async () => {
    const user = userEvent.setup();
    authApi.login.mockResolvedValue({
      data: { access_token: 'tok', username: 'alice', is_global_admin: false, user_id: 42 },
    });
    renderPage();

    await user.type(screen.getByPlaceholderText('Username'), 'alice');
    await user.type(screen.getByPlaceholderText('Password'), 'pass');
    const submitBtn = screen.getAllByText('Sign In').find(el => el.getAttribute('type') === 'submit');
    await user.click(submitBtn);

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith(
        'tok',
        expect.objectContaining({ username: 'alice', user_id: 42 }),
      );
    });
  });
});
