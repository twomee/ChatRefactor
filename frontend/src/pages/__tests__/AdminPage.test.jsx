import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('react-grid-layout', () => ({
  Responsive: ({ children }) => <div data-testid="grid-layout">{children}</div>,
}));
vi.mock('react-grid-layout/legacy', () => ({
  WidthProvider: (Component) => Component,
}));
vi.mock('react-grid-layout/css/styles.css', () => ({}));
vi.mock('react-resizable/css/styles.css', () => ({}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/adminApi', () => ({
  getRooms: vi.fn(),
  getUsers: vi.fn(),
  closeAllRooms: vi.fn(),
  openAllRooms: vi.fn(),
  closeRoom: vi.fn(),
  openRoom: vi.fn(),
  resetDatabase: vi.fn(),
  promoteUser: vi.fn(),
}));

vi.mock('../../services/roomApi', () => ({
  createRoom: vi.fn(),
}));

vi.mock('../../services/fileApi', () => ({
  listRoomFiles: vi.fn(),
  downloadFile: vi.fn(),
}));

import * as adminApi from '../../services/adminApi';
import * as roomApi from '../../services/roomApi';
import * as fileApi from '../../services/fileApi';
import AdminPage from '../AdminPage';

function renderAdminPage() {
  return render(
    <MemoryRouter>
      <AdminPage />
    </MemoryRouter>
  );
}

describe('AdminPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    adminApi.getRooms.mockResolvedValue({ data: [
      { id: 1, name: 'general', is_active: true },
      { id: 2, name: 'offtopic', is_active: false },
    ] });
    adminApi.getUsers.mockResolvedValue({ data: {
      all_online: ['alice', 'bob'],
      per_room: { 1: ['alice'] },
    } });
    adminApi.promoteUser.mockResolvedValue({});
    adminApi.closeRoom.mockResolvedValue({});
    adminApi.openRoom.mockResolvedValue({});
    adminApi.closeAllRooms.mockResolvedValue({});
    adminApi.openAllRooms.mockResolvedValue({});
    roomApi.createRoom.mockResolvedValue({ id: 3, name: 'new-room' });
    fileApi.listRoomFiles.mockResolvedValue({ data: [] });
    // Prevent the 3-second polling interval from running indefinitely in tests
    vi.spyOn(globalThis, 'setInterval').mockImplementation(() => 1);
    vi.spyOn(globalThis, 'clearInterval').mockImplementation(() => {});
  });

  it('renders the admin dashboard grid', () => {
    renderAdminPage();
    expect(screen.getByTestId('grid-layout')).toBeInTheDocument();
  });

  it('renders the admin panel header', () => {
    renderAdminPage();
    expect(screen.getByText(/Admin Panel/i)).toBeInTheDocument();
  });

  it('fetches rooms and users on mount', async () => {
    renderAdminPage();
    await waitFor(() => {
      expect(adminApi.getRooms).toHaveBeenCalled();
      expect(adminApi.getUsers).toHaveBeenCalled();
    });
  });

  it('renders room names after loading', async () => {
    renderAdminPage();
    await waitFor(() => {
      expect(screen.getByText('general')).toBeInTheDocument();
      expect(screen.getByText('offtopic')).toBeInTheDocument();
    });
  });

  it('renders online users after loading', async () => {
    renderAdminPage();
    await waitFor(() => {
      // alice appears in both the online users list and the room users column
      expect(screen.getAllByText('alice').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('bob')).toBeInTheDocument();
    });
  });

  it('shows active room as "Open" and closed room as "Closed"', async () => {
    renderAdminPage();
    await waitFor(() => {
      // "Open" appears as both a status badge (general) and an action button (offtopic)
      expect(screen.getAllByText('Open').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('Closed')).toBeInTheDocument();
    });
  });

  it('creates a room when the add-room form is submitted', async () => {
    const user = userEvent.setup();
    renderAdminPage();
    await waitFor(() => expect(adminApi.getRooms).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/room name/i), 'new-room');
    await user.click(screen.getByRole('button', { name: /create room/i }));

    await waitFor(() => {
      expect(roomApi.createRoom).toHaveBeenCalledWith('new-room');
    });
  });

  it('shows status message on successful room creation', async () => {
    const user = userEvent.setup();
    renderAdminPage();
    await waitFor(() => expect(adminApi.getRooms).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/room name/i), 'testroom');
    await user.click(screen.getByRole('button', { name: /create room/i }));

    await waitFor(() => {
      expect(screen.getByText(/testroom.*created/i)).toBeInTheDocument();
    });
  });

  it('promotes a user when the promote form is submitted', async () => {
    const user = userEvent.setup();
    renderAdminPage();
    await waitFor(() => expect(adminApi.getUsers).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText(/username/i), 'alice');
    await user.click(screen.getByRole('button', { name: /^promote$/i }));

    await waitFor(() => {
      expect(adminApi.promoteUser).toHaveBeenCalledWith('alice');
    });
  });

  it('closes a room when the Close button is clicked', async () => {
    const user = userEvent.setup();
    renderAdminPage();
    await waitFor(() => expect(screen.getByText('general')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /^close$/i }));

    await waitFor(() => {
      expect(adminApi.closeRoom).toHaveBeenCalledWith(1);
    });
  });

  it('opens a closed room when the Open button is clicked', async () => {
    const user = userEvent.setup();
    renderAdminPage();
    await waitFor(() => expect(screen.getByText('offtopic')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /^open$/i }));

    await waitFor(() => {
      expect(adminApi.openRoom).toHaveBeenCalledWith(2);
    });
  });

  it('shows room files when Files button is clicked', async () => {
    const user = userEvent.setup();
    fileApi.listRoomFiles.mockResolvedValue({ data: [] });
    renderAdminPage();
    await waitFor(() => expect(screen.getByText('general')).toBeInTheDocument());

    const fileBtns = screen.getAllByRole('button', { name: /files/i });
    await user.click(fileBtns[0]);

    await waitFor(() => {
      expect(fileApi.listRoomFiles).toHaveBeenCalledWith(1);
      expect(screen.getByText(/no files/i)).toBeInTheDocument();
    });
  });

  it('navigates back to chat when Back to Chat is clicked', async () => {
    const user = userEvent.setup();
    renderAdminPage();
    await user.click(screen.getByText('Back to Chat'));
    expect(mockNavigate).toHaveBeenCalledWith('/chat');
  });

  it('closes all rooms when Close All Rooms button is clicked', async () => {
    const user = userEvent.setup();
    renderAdminPage();
    await waitFor(() => expect(adminApi.getRooms).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: /close all rooms/i }));
    await waitFor(() => expect(adminApi.closeAllRooms).toHaveBeenCalled());
  });

  it('opens all rooms when Open All Rooms button is clicked', async () => {
    const user = userEvent.setup();
    renderAdminPage();
    await waitFor(() => expect(adminApi.getRooms).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: /open all rooms/i }));
    await waitFor(() => expect(adminApi.openAllRooms).toHaveBeenCalled());
  });
});
