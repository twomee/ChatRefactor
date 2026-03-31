import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import UserList from '../UserList';

vi.mock('../../common/ContextMenu', () => ({
  default: ({ target, onClose }) => (
    <div data-testid="context-menu" data-target={target}>
      <button onClick={onClose}>Close</button>
    </div>
  ),
}));

const baseProps = {
  users: ['alice', 'bob', 'carol'],
  admins: ['alice'],
  mutedUsers: ['carol'],
  currentUser: 'bob',
  isCurrentUserAdmin: false,
  onKick: vi.fn(),
  onMute: vi.fn(),
  onUnmute: vi.fn(),
  onPromote: vi.fn(),
  onStartPM: vi.fn(),
};

describe('UserList', () => {
  it('renders all users with their names', () => {
    render(<UserList {...baseProps} />);
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('bob')).toBeInTheDocument();
    expect(screen.getByText('carol')).toBeInTheDocument();
  });

  it('shows online user count in header', () => {
    render(<UserList {...baseProps} />);
    expect(screen.getByText('(3)')).toBeInTheDocument();
  });

  it('renders initials as avatar for each user', () => {
    render(<UserList {...baseProps} />);
    expect(screen.getByText('AL')).toBeInTheDocument();
    expect(screen.getByText('BO')).toBeInTheDocument();
    expect(screen.getByText('CA')).toBeInTheDocument();
  });

  it('shows Admin badge for admin users', () => {
    render(<UserList {...baseProps} />);
    expect(screen.getByText('Admin')).toBeInTheDocument();
  });

  it('shows Muted badge for muted users', () => {
    render(<UserList {...baseProps} />);
    expect(screen.getByText('Muted')).toBeInTheDocument();
  });

  it('applies is-self class to current user', () => {
    const { container } = render(<UserList {...baseProps} />);
    const items = container.querySelectorAll('.user-item');
    const bobItem = Array.from(items).find(el => el.textContent.includes('bob'));
    expect(bobItem).toHaveClass('is-self');
  });

  it('calls onStartPM when clicking another user', () => {
    render(<UserList {...baseProps} />);
    fireEvent.click(screen.getByText('alice'));
    expect(baseProps.onStartPM).toHaveBeenCalledWith('alice');
  });

  it('does not call onStartPM when clicking self', () => {
    const onStartPM = vi.fn();
    render(<UserList {...baseProps} onStartPM={onStartPM} />);
    fireEvent.click(screen.getByText('bob'));
    expect(onStartPM).not.toHaveBeenCalled();
  });

  it('renders empty list gracefully', () => {
    const { container } = render(<UserList {...baseProps} users={[]} />);
    expect(container.querySelectorAll('.user-item')).toHaveLength(0);
    expect(screen.getByText('(0)')).toBeInTheDocument();
  });

  it('shows admin action buttons when isCurrentUserAdmin is true', () => {
    const { container } = render(<UserList {...baseProps} isCurrentUserAdmin currentUser="alice" />);
    const menuBtns = container.querySelectorAll('.user-item-menu-btn');
    // Other users (bob, carol) get the button; self (alice) does not
    expect(menuBtns).toHaveLength(2);
  });

  it('shows context menu when admin clicks the menu button', () => {
    render(<UserList {...baseProps} isCurrentUserAdmin currentUser="alice" />);
    const menuBtns = screen.getAllByTitle('Admin actions');
    fireEvent.click(menuBtns[0]);
    expect(screen.getByTestId('context-menu')).toBeInTheDocument();
  });

  it('closes context menu when onClose is called', () => {
    render(<UserList {...baseProps} isCurrentUserAdmin currentUser="alice" />);
    fireEvent.click(screen.getAllByTitle('Admin actions')[0]);
    expect(screen.getByTestId('context-menu')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Close'));
    expect(screen.queryByTestId('context-menu')).toBeNull();
  });

  it('does not open context menu on right-click for non-admin users', () => {
    render(<UserList {...baseProps} isCurrentUserAdmin={false} />);
    fireEvent.contextMenu(screen.getByText('alice'));
    expect(screen.queryByTestId('context-menu')).toBeNull();
  });

  it('does not open context menu on right-click on self', () => {
    render(<UserList {...baseProps} isCurrentUserAdmin currentUser="alice" />);
    fireEvent.contextMenu(screen.getByText('alice').closest('.user-item'));
    expect(screen.queryByTestId('context-menu')).toBeNull();
  });

  it('renders with undefined admins and mutedUsers gracefully', () => {
    render(<UserList {...baseProps} admins={undefined} mutedUsers={undefined} />);
    expect(screen.queryByText('Admin')).toBeNull();
    expect(screen.queryByText('Muted')).toBeNull();
  });
});
