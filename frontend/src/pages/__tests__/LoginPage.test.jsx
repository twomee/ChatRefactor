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
    await user.type(screen.getByPlaceholderText('Password'), 'pass123');
    await user.click(screen.getByRole('button', { name: 'Create Account' }));

    await waitFor(() => {
      expect(authApi.register).toHaveBeenCalledWith('newuser', 'pass123');
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
});
