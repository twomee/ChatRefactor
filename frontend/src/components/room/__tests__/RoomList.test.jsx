import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RoomList from '../RoomList';

const rooms = [
  { id: 'r1', name: 'general', is_active: true },
  { id: 'r2', name: 'random', is_active: true },
  { id: 'r3', name: 'dev', is_active: true },
];

describe('RoomList', () => {
  it('separates rooms into "Your Rooms" and "Available" sections', () => {
    render(
      <RoomList
        rooms={rooms}
        joinedRooms={new Set(['r1'])}
        activeRoomId="r1"
        onJoin={vi.fn()}
        onExit={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('Your Rooms')).toBeInTheDocument();
    expect(screen.getByText('Available')).toBeInTheDocument();
  });

  it('shows joined rooms with exit button', () => {
    render(
      <RoomList
        rooms={rooms}
        joinedRooms={new Set(['r1'])}
        activeRoomId="r1"
        onJoin={vi.fn()}
        onExit={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    // "general" should appear in Your Rooms with an exit button
    expect(screen.getByText('general')).toBeInTheDocument();
    expect(screen.getByTitle('Exit room')).toBeInTheDocument();
  });

  it('shows available rooms with join button', () => {
    render(
      <RoomList
        rooms={rooms}
        joinedRooms={new Set(['r1'])}
        activeRoomId="r1"
        onJoin={vi.fn()}
        onExit={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    // "random" and "dev" should have Join buttons
    const joinButtons = screen.getAllByText('Join');
    expect(joinButtons).toHaveLength(2);
  });

  it('calls onSelect when clicking a joined room', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <RoomList
        rooms={rooms}
        joinedRooms={new Set(['r1'])}
        activeRoomId={null}
        onJoin={vi.fn()}
        onExit={vi.fn()}
        onSelect={onSelect}
      />,
    );
    await user.click(screen.getByText('general'));
    expect(onSelect).toHaveBeenCalledWith('r1');
  });

  it('calls onJoin when clicking Join on an available room', async () => {
    const user = userEvent.setup();
    const onJoin = vi.fn();
    render(
      <RoomList
        rooms={rooms}
        joinedRooms={new Set(['r1'])}
        activeRoomId="r1"
        onJoin={onJoin}
        onExit={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    const joinButtons = screen.getAllByText('Join');
    await user.click(joinButtons[0]);
    expect(onJoin).toHaveBeenCalledWith('r2');
  });

  it('calls onExit when clicking exit button (without selecting room)', async () => {
    const user = userEvent.setup();
    const onExit = vi.fn();
    const onSelect = vi.fn();
    render(
      <RoomList
        rooms={rooms}
        joinedRooms={new Set(['r1'])}
        activeRoomId="r1"
        onJoin={vi.fn()}
        onExit={onExit}
        onSelect={onSelect}
      />,
    );
    await user.click(screen.getByTitle('Exit room'));
    expect(onExit).toHaveBeenCalledWith('r1');
    // stopPropagation should prevent onSelect from firing
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('displays unread badge when count > 0', () => {
    render(
      <RoomList
        rooms={rooms}
        joinedRooms={new Set(['r1'])}
        activeRoomId={null}
        unreadCounts={{ r1: 5 }}
        onJoin={vi.fn()}
        onExit={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('caps unread badge at 99+', () => {
    render(
      <RoomList
        rooms={rooms}
        joinedRooms={new Set(['r1'])}
        activeRoomId={null}
        unreadCounts={{ r1: 150 }}
        onJoin={vi.fn()}
        onExit={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('99+')).toBeInTheDocument();
  });

  it('shows empty state when no rooms joined', () => {
    render(
      <RoomList
        rooms={rooms}
        joinedRooms={new Set()}
        activeRoomId={null}
        onJoin={vi.fn()}
        onExit={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('No rooms joined yet')).toBeInTheDocument();
  });
});
