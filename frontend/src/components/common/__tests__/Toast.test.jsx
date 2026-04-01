import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToastProvider, useToast } from '../../../context/ToastContext';
import Toast from '../Toast';

function Wrapper({ children }) {
  return (
    <ToastProvider>
      <Toast />
      {children}
    </ToastProvider>
  );
}

function TriggerButton({ type = 'info', title = 'Test', message = 'Body', duration }) {
  const { showToast } = useToast();
  return (
    <button onClick={() => showToast(type, title, message, duration)}>
      Show Toast
    </button>
  );
}

function renderSetup(props = {}) {
  return render(
    <Wrapper>
      <TriggerButton {...props} />
    </Wrapper>,
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe('Toast component', () => {
  it('renders nothing when there are no toasts', () => {
    renderSetup();
    expect(screen.queryByTestId('toast-card')).not.toBeInTheDocument();
  });

  it('shows a toast card when showToast is called', async () => {
    const user = userEvent.setup();
    renderSetup({ title: 'Hello', message: 'World' });

    await user.click(screen.getByText('Show Toast'));

    expect(screen.getByTestId('toast-card')).toBeInTheDocument();
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('World')).toBeInTheDocument();
  });

  it('applies the correct CSS class for each toast type', async () => {
    for (const type of ['danger', 'warning', 'info', 'success']) {
      const user = userEvent.setup();
      const { unmount } = render(
        <Wrapper>
          <TriggerButton type={type} title={`${type} toast`} />
        </Wrapper>,
      );
      await user.click(screen.getByText('Show Toast'));
      const card = screen.getByTestId('toast-card');
      expect(card).toHaveClass(`toast-card--${type}`);
      unmount();
    }
  });

  it('dismisses toast when close button is clicked (applies removing class)', async () => {
    // Render directly with a consumer that calls showToast via fireEvent — avoids
    // fake-timer + userEvent deadlock.
    function DirectTrigger() {
      const { showToast } = useToast();
      return <button id="trigger" onClick={() => showToast('info', 'Dismiss me', '', 60000)}>Show</button>;
    }
    render(<Wrapper><DirectTrigger /></Wrapper>);

    // Show the toast (synchronous state update inside act)
    act(() => { fireEvent.click(document.getElementById('trigger')); });
    expect(screen.getByTestId('toast-card')).toBeInTheDocument();

    // Click dismiss — this triggers setRemoving(true) synchronously
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' })); });

    // The card should get the removing class immediately
    const card = screen.queryByTestId('toast-card');
    expect(card === null || card.classList.contains('toast-card--removing')).toBe(true);
  });

  it('auto-dismisses after the specified duration', () => {
    vi.useFakeTimers();
    function DirectTrigger() {
      const { showToast } = useToast();
      return <button id="trigger" onClick={() => showToast('info', 'Auto', '', 2000)}>Show</button>;
    }
    render(<Wrapper><DirectTrigger /></Wrapper>);

    act(() => { fireEvent.click(document.getElementById('trigger')); });
    expect(screen.getByTestId('toast-card')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(2000));
    expect(screen.queryByTestId('toast-card')).not.toBeInTheDocument();
  });

  it('renders multiple toasts simultaneously', async () => {
    function MultiTrigger() {
      const { showToast } = useToast();
      return (
        <>
          <button onClick={() => showToast('info', 'First', '')}>First</button>
          <button onClick={() => showToast('danger', 'Second', '')}>Second</button>
        </>
      );
    }
    const user = userEvent.setup();
    render(<Wrapper><MultiTrigger /></Wrapper>);

    await user.click(screen.getByText('First'));
    await user.click(screen.getByText('Second'));

    const cards = screen.getAllByTestId('toast-card');
    expect(cards).toHaveLength(2);
  });

  it('has accessible role="alert" on toast cards', async () => {
    const user = userEvent.setup();
    renderSetup({ title: 'Accessible' });

    await user.click(screen.getByText('Show Toast'));
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
