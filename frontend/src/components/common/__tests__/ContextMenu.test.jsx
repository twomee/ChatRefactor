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

  it('does not show "Send private message" when onStartPM is not provided', () => {
    render(<ContextMenu {...defaultProps} />);
    expect(screen.queryByText('Send private message')).not.toBeInTheDocument();
  });

  it('shows "Send private message" when onStartPM is provided', () => {
    render(<ContextMenu {...defaultProps} onStartPM={vi.fn()} />);
    expect(screen.getByText('Send private message')).toBeInTheDocument();
  });

  it('calls onStartPM and onClose when clicking "Send private message"', async () => {
    const user = userEvent.setup();
    const onStartPM = vi.fn();
    const onClose = vi.fn();
    render(<ContextMenu {...defaultProps} onStartPM={onStartPM} onClose={onClose} />);

    await user.click(screen.getByText('Send private message'));
    expect(onStartPM).toHaveBeenCalledWith('bob');
    expect(onClose).toHaveBeenCalled();
  });

  it('positions menu at the click coordinates when space is available', () => {
    // Give the viewport plenty of room so clamping doesn't change the position.
    // JSDOM's getBoundingClientRect returns 0-size, so vw - 0 - 8 >> x/y.
    Object.defineProperty(window, 'innerWidth',  { writable: true, configurable: true, value: 1920 });
    Object.defineProperty(window, 'innerHeight', { writable: true, configurable: true, value: 1080 });
    render(<ContextMenu {...defaultProps} />);
    const menu = document.querySelector('.context-menu');
    expect(menu.style.top).toBe('200px');
    expect(menu.style.left).toBe('100px');
  });

  it('clamps the menu to stay within the right/bottom viewport edges', () => {
    // Mock getBoundingClientRect BEFORE render so useLayoutEffect sees it.
    const getBCRSpy = vi.spyOn(Element.prototype, 'getBoundingClientRect')
      .mockReturnValue({ width: 160, height: 200, top: 0, left: 0, bottom: 0, right: 0, x: 0, y: 0, toJSON: () => {} });

    Object.defineProperty(window, 'innerWidth',  { writable: true, configurable: true, value: 200 });
    Object.defineProperty(window, 'innerHeight', { writable: true, configurable: true, value: 300 });

    render(<ContextMenu {...defaultProps} x={180} y={270} />);
    const menu = document.querySelector('.context-menu');

    // x: Math.min(180, 200-160-8)=32 → Math.max(8, 32)=32
    // y: Math.min(270, 300-200-8)=92 → Math.max(8, 92)=92
    expect(parseInt(menu.style.left, 10)).toBeLessThan(180);
    expect(parseInt(menu.style.top,  10)).toBeLessThan(270);

    getBCRSpy.mockRestore();
  });
});
