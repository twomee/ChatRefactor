import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ChatConnectionLayer, { useChatConnection } from '../ChatConnectionLayer';

const mockChatConn = { sendMessage: vi.fn(), joinRoom: vi.fn() };

vi.mock('../../hooks/useMultiRoomChat', () => ({
  useMultiRoomChat: () => mockChatConn,
}));

vi.mock('react-router-dom', () => ({
  Outlet: () => <div data-testid="outlet" />,
  useOutletContext: () => mockChatConn,
}));

describe('ChatConnectionLayer', () => {
  it('renders the Outlet', () => {
    render(<ChatConnectionLayer />);
    expect(screen.getByTestId('outlet')).toBeInTheDocument();
  });

  it('useChatConnection returns the outlet context', () => {
    let result;
    function Consumer() {
      result = useChatConnection();
      return null;
    }
    render(<Consumer />);
    expect(result).toBe(mockChatConn);
  });
});
