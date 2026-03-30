import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsModal from '../SettingsModal';

// TwoFactorSetup makes API calls on mount — mock it to keep tests fast/isolated
vi.mock('../TwoFactorSetup', () => ({
  default: () => <div data-testid="two-factor-setup">2FA Setup</div>,
}));

describe('SettingsModal', () => {
  it('renders nothing when open is false', () => {
    const { container } = render(<SettingsModal open={false} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the settings panel when open is true', () => {
    render(<SettingsModal open={true} onClose={vi.fn()} />);
    expect(screen.getByRole('dialog', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('renders the TwoFactorSetup component in the body', () => {
    render(<SettingsModal open={true} onClose={vi.fn()} />);
    expect(screen.getByTestId('two-factor-setup')).toBeInTheDocument();
  });

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<SettingsModal open={true} onClose={onClose} />);

    await user.click(screen.getByLabelText('Close settings'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when Escape key is pressed', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<SettingsModal open={true} onClose={onClose} />);

    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not add Escape listener when closed', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<SettingsModal open={false} onClose={onClose} />);

    await user.keyboard('{Escape}');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('calls onClose when the backdrop itself is clicked', () => {
    const onClose = vi.fn();
    const { container } = render(<SettingsModal open={true} onClose={onClose} />);

    // Click the backdrop element directly (not a child)
    const backdrop = container.querySelector('.settings-backdrop');
    fireEvent.click(backdrop, { target: backdrop });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not call onClose when clicking inside the panel', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<SettingsModal open={true} onClose={onClose} />);

    // Clicking the panel heading should NOT close the modal
    await user.click(screen.getByText('Settings'));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('calls onClose on Enter/Space keydown on the backdrop itself', () => {
    const onClose = vi.fn();
    const { container } = render(<SettingsModal open={true} onClose={onClose} />);

    const backdrop = container.querySelector('.settings-backdrop');
    // Simulate Enter key with target === currentTarget
    fireEvent.keyDown(backdrop, { key: 'Enter', target: backdrop });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
