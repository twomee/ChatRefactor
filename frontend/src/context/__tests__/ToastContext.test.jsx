import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { ToastProvider, useToast } from '../ToastContext';

// Helper component that exposes the toast context via the DOM
function ToastConsumer({ onMount }) {
  const ctx = useToast();
  // Pass the context methods out so tests can call them
  onMount(ctx);
  return null;
}

function renderWithProvider(onMount) {
  return render(
    <ToastProvider>
      <ToastConsumer onMount={onMount} />
    </ToastProvider>,
  );
}

describe('ToastContext', () => {
  let ctx;

  beforeEach(() => {
    vi.useFakeTimers();
    renderWithProvider(c => { ctx = c; });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('provides showToast and removeToast functions', () => {
    expect(typeof ctx.showToast).toBe('function');
    expect(typeof ctx.removeToast).toBe('function');
  });

  it('starts with no toasts', () => {
    expect(ctx.toasts).toHaveLength(0);
  });

  it('showToast adds a toast with the correct fields', () => {
    act(() => ctx.showToast('danger', 'Title', 'Message'));
    expect(ctx.toasts).toHaveLength(1);
    expect(ctx.toasts[0]).toMatchObject({ type: 'danger', title: 'Title', message: 'Message' });
    expect(typeof ctx.toasts[0].id).toBe('string');
  });

  it('supports all four toast types', () => {
    for (const type of ['danger', 'warning', 'info', 'success']) {
      act(() => ctx.showToast(type, 'T', 'M'));
    }
    const types = ctx.toasts.map(t => t.type);
    expect(types).toEqual(expect.arrayContaining(['danger', 'warning', 'info', 'success']));
  });

  it('auto-dismisses after the given duration', () => {
    act(() => ctx.showToast('info', 'T', 'M', 2000));
    expect(ctx.toasts).toHaveLength(1);
    act(() => vi.advanceTimersByTime(2000));
    expect(ctx.toasts).toHaveLength(0);
  });

  it('auto-dismisses after default 4000ms when no duration given', () => {
    act(() => ctx.showToast('info', 'T', 'M'));
    expect(ctx.toasts).toHaveLength(1);
    act(() => vi.advanceTimersByTime(3999));
    expect(ctx.toasts).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    expect(ctx.toasts).toHaveLength(0);
  });

  it('removeToast removes only the specified toast', () => {
    act(() => {
      ctx.showToast('info', 'A', '');
      ctx.showToast('info', 'B', '');
    });
    expect(ctx.toasts).toHaveLength(2);
    const idToRemove = ctx.toasts[0].id;
    act(() => ctx.removeToast(idToRemove));
    expect(ctx.toasts).toHaveLength(1);
    expect(ctx.toasts[0].title).toBe('B');
  });

  it('caps the visible stack at 4 (newest wins, keeps last 4 after each call)', () => {
    act(() => {
      // Each call slices prev to keep at most 3 before appending → max 4 total
      for (let i = 0; i < 6; i++) ctx.showToast('info', `T${i}`, '');
    });
    // slice(-3) keeps the last 3 existing, then appends 1 new → max 4
    expect(ctx.toasts.length).toBeLessThanOrEqual(4);
  });
});

describe('useToast outside provider', () => {
  it('throws when used outside ToastProvider', () => {
    // Silence the expected React error boundary output
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    function BadConsumer() {
      useToast();
      return null;
    }
    expect(() => render(<BadConsumer />)).toThrow('useToast must be used inside <ToastProvider>');
    spy.mockRestore();
  });
});
