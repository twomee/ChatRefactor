// src/components/settings/__tests__/AccountSection.test.jsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AccountSection from '../AccountSection';

describe('AccountSection', () => {
  describe('Clear Room History', () => {
    it('renders the clear room history section', () => {
      render(<AccountSection />);
      expect(screen.getByText('Clear Room History')).toBeDefined();
      expect(screen.getByLabelText('Select Room')).toBeDefined();
    });

    it('clear history button is disabled when no room is entered', () => {
      render(<AccountSection />);
      const buttons = screen.getAllByText('Clear History');
      expect(buttons[0].disabled).toBe(true);
    });

    it('clear history button enables when room name is typed', () => {
      render(<AccountSection />);
      const input = screen.getByLabelText('Select Room');
      fireEvent.change(input, { target: { value: 'general' } });
      const buttons = screen.getAllByText('Clear History');
      expect(buttons[0].disabled).toBe(false);
    });

    it('shows confirmation dialog on first click', () => {
      render(<AccountSection />);
      const input = screen.getByLabelText('Select Room');
      fireEvent.change(input, { target: { value: 'general' } });
      const clearBtn = screen.getAllByText('Clear History')[0];
      fireEvent.click(clearBtn);
      expect(screen.getByText(/Are you sure/)).toBeDefined();
      expect(screen.getByText('Confirm Delete')).toBeDefined();
      expect(screen.getByText('Cancel')).toBeDefined();
    });

    it('clears history and shows success on confirm', () => {
      render(<AccountSection />);
      const input = screen.getByLabelText('Select Room');
      fireEvent.change(input, { target: { value: 'general' } });
      fireEvent.click(screen.getAllByText('Clear History')[0]);
      fireEvent.click(screen.getByText('Confirm Delete'));
      expect(screen.getByText(/Room history cleared/)).toBeDefined();
    });

    it('cancel hides the confirmation dialog', () => {
      render(<AccountSection />);
      const input = screen.getByLabelText('Select Room');
      fireEvent.change(input, { target: { value: 'general' } });
      fireEvent.click(screen.getAllByText('Clear History')[0]);
      fireEvent.click(screen.getByText('Cancel'));
      // Confirmation dialog should be gone
      expect(screen.queryByText(/Are you sure/)).toBeNull();
    });

    it('resets confirm state when room input changes', () => {
      render(<AccountSection />);
      const input = screen.getByLabelText('Select Room');
      fireEvent.change(input, { target: { value: 'general' } });
      fireEvent.click(screen.getAllByText('Clear History')[0]);
      expect(screen.getByText(/Are you sure/)).toBeDefined();
      // Changing the input should reset the confirm state
      fireEvent.change(input, { target: { value: 'other-room' } });
      expect(screen.queryByText(/Are you sure/)).toBeNull();
    });
  });

  describe('Clear PM History', () => {
    it('renders the clear PM history section', () => {
      render(<AccountSection />);
      expect(screen.getByText('Clear PM History')).toBeDefined();
      expect(screen.getByLabelText('Select User')).toBeDefined();
    });

    it('clear PM history button is disabled when no user is entered', () => {
      render(<AccountSection />);
      const buttons = screen.getAllByText('Clear History');
      // Second "Clear History" button is for PM
      expect(buttons[1].disabled).toBe(true);
    });

    it('enables when username is typed', () => {
      render(<AccountSection />);
      const input = screen.getByLabelText('Select User');
      fireEvent.change(input, { target: { value: 'alice' } });
      const buttons = screen.getAllByText('Clear History');
      expect(buttons[1].disabled).toBe(false);
    });

    it('shows PM confirmation dialog on first click', () => {
      render(<AccountSection />);
      const input = screen.getByLabelText('Select User');
      fireEvent.change(input, { target: { value: 'alice' } });
      fireEvent.click(screen.getAllByText('Clear History')[1]);
      expect(screen.getByText(/permanently delete all PM messages/)).toBeDefined();
    });

    it('shows success message on PM clear confirm', () => {
      render(<AccountSection />);
      const input = screen.getByLabelText('Select User');
      fireEvent.change(input, { target: { value: 'alice' } });
      fireEvent.click(screen.getAllByText('Clear History')[1]);
      // There will be 2 "Confirm Delete" buttons if room section also has one
      const confirmBtns = screen.getAllByText('Confirm Delete');
      fireEvent.click(confirmBtns[confirmBtns.length - 1]);
      expect(screen.getByText(/PM history cleared/)).toBeDefined();
    });

    it('cancel hides the PM confirmation dialog', () => {
      render(<AccountSection />);
      const input = screen.getByLabelText('Select User');
      fireEvent.change(input, { target: { value: 'alice' } });
      fireEvent.click(screen.getAllByText('Clear History')[1]);
      const cancelBtns = screen.getAllByText('Cancel');
      fireEvent.click(cancelBtns[cancelBtns.length - 1]);
      expect(screen.queryByText(/permanently delete all PM messages/)).toBeNull();
    });
  });
});
