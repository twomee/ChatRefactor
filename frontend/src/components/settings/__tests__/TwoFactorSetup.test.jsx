import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TwoFactorSetup from '../TwoFactorSetup';

// Mock authApi
vi.mock('../../../services/authApi', () => ({
  get2FAStatus: vi.fn(),
  setup2FA: vi.fn(),
  verifySetup2FA: vi.fn(),
  disable2FA: vi.fn(),
}));

import * as authApi from '../../../services/authApi';

describe('TwoFactorSetup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    authApi.get2FAStatus.mockReturnValue(new Promise(() => {})); // never resolves
    render(<TwoFactorSetup />);
    expect(screen.getByText(/loading 2fa status/i)).toBeInTheDocument();
  });

  it('shows Enable 2FA button when 2FA is disabled', async () => {
    authApi.get2FAStatus.mockResolvedValue({ data: { is_2fa_enabled: false } });
    render(<TwoFactorSetup />);
    await waitFor(() => {
      expect(screen.getByText('Enable 2FA')).toBeInTheDocument();
    });
  });

  it('shows 2FA is enabled message when enabled', async () => {
    authApi.get2FAStatus.mockResolvedValue({ data: { is_2fa_enabled: true } });
    render(<TwoFactorSetup />);
    await waitFor(() => {
      expect(screen.getByText(/2fa is currently enabled/i)).toBeInTheDocument();
    });
  });

  it('shows setup data after clicking Enable 2FA', async () => {
    const user = userEvent.setup();
    authApi.get2FAStatus.mockResolvedValue({ data: { is_2fa_enabled: false } });
    authApi.setup2FA.mockResolvedValue({
      data: { secret: 'ABCDEF1234567890ABCDEF1234567890', otpauth_uri: 'otpauth://totp/cHATBOX:testuser?secret=ABCDEF' },
    });

    render(<TwoFactorSetup />);
    await waitFor(() => {
      expect(screen.getByText('Enable 2FA')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Enable 2FA'));

    await waitFor(() => {
      expect(screen.getByText(/ABCDEF1234567890ABCDEF1234567890/)).toBeInTheDocument();
      expect(screen.getByTestId('tfa-setup-code')).toBeInTheDocument();
    });
  });

  it('calls verifySetup2FA when code is submitted', async () => {
    const user = userEvent.setup();
    authApi.get2FAStatus.mockResolvedValue({ data: { is_2fa_enabled: false } });
    authApi.setup2FA.mockResolvedValue({
      data: { secret: 'TESTSECRET1234567890123456789012', otpauth_uri: 'otpauth://test' },
    });
    authApi.verifySetup2FA.mockResolvedValue({ data: { message: '2FA enabled' } });

    render(<TwoFactorSetup />);
    await waitFor(() => screen.getByText('Enable 2FA'));
    await user.click(screen.getByText('Enable 2FA'));
    await waitFor(() => screen.getByTestId('tfa-setup-code'));

    await user.type(screen.getByTestId('tfa-setup-code'), '123456');
    await user.click(screen.getByText('Verify & Enable'));

    await waitFor(() => {
      expect(authApi.verifySetup2FA).toHaveBeenCalledWith('123456');
    });
  });

  it('shows error when setup fails', async () => {
    const user = userEvent.setup();
    authApi.get2FAStatus.mockResolvedValue({ data: { is_2fa_enabled: false } });
    authApi.setup2FA.mockRejectedValue({
      response: { data: { detail: '2FA is already enabled' } },
    });

    render(<TwoFactorSetup />);
    await waitFor(() => screen.getByText('Enable 2FA'));
    await user.click(screen.getByText('Enable 2FA'));

    await waitFor(() => {
      expect(screen.getByText('2FA is already enabled')).toBeInTheDocument();
    });
  });
});
