import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ContextMenu from '../ContextMenu';

const defaultProps = {
  x: 100,
  y: 200,
  target: 'bob',
  isMuted: false,
  isTargetAdmin: false,
  onKick: vi.fn(),
  onMute: vi.fn(),
  onUnmute: vi.fn(),
  onPromote: vi.fn(),
  onClose: vi.fn(),
};

describe('ContextMenu', () => {
  it('renders target username in header', () => {
    render(<ContextMenu {...defaultProps} />);
    expect(screen.getByText('bob')).toBeInTheDocument();
  });

  it('shows Kick, Mute, Make Admin for non-admin target', () => {
    render(<ContextMenu {...defaultProps} />);
    expect(screen.getByText('Kick')).toBeInTheDocument();
    expect(screen.getByText('Mute')).toBeInTheDocument();
    expect(screen.getByText('Make Admin')).toBeInTheDocument();
  });

  it('shows Unmute instead of Mute when target is muted', () => {
    render(<ContextMenu {...defaultProps} isMuted={true} />);
    expect(screen.queryByText('Mute')).not.toBeInTheDocument();
    expect(screen.getByText('Unmute')).toBeInTheDocument();
  });

  it('shows "Already an admin" for admin targets', () => {
    render(<ContextMenu {...defaultProps} isTargetAdmin={true} />);
    expect(screen.queryByText('Kick')).not.toBeInTheDocument();
    expect(screen.queryByText('Mute')).not.toBeInTheDocument();
    expect(screen.getByText('Already an admin')).toBeInTheDocument();
  });

  it('calls onKick and onClose when clicking Kick', async () => {
    const user = userEvent.setup();
    const onKick = vi.fn();
    const onClose = vi.fn();
    render(<ContextMenu {...defaultProps} onKick={onKick} onClose={onClose} />);

    await user.click(screen.getByText('Kick'));
    expect(onKick).toHaveBeenCalledWith('bob');
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onMute and onClose when clicking Mute', async () => {
    const user = userEvent.setup();
    const onMute = vi.fn();
    const onClose = vi.fn();
    render(<ContextMenu {...defaultProps} onMute={onMute} onClose={onClose} />);

    await user.click(screen.getByText('Mute'));
    expect(onMute).toHaveBeenCalledWith('bob');
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onPromote and onClose when clicking Make Admin', async () => {
    const user = userEvent.setup();
    const onPromote = vi.fn();
    const onClose = vi.fn();
    render(<ContextMenu {...defaultProps} onPromote={onPromote} onClose={onClose} />);

    await user.click(screen.getByText('Make Admin'));
    expect(onPromote).toHaveBeenCalledWith('bob');
    expect(onClose).toHaveBeenCalled();
  });

  it('is positioned at the provided x, y coordinates', () => {
    const { container } = render(<ContextMenu {...defaultProps} />);
    const menu = container.querySelector('.context-menu');
    expect(menu.style.top).toBe('200px');
    expect(menu.style.left).toBe('100px');
  });
});
