import { describe, it, expect } from 'vitest';
import { formatSize } from '../formatting';

describe('formatSize', () => {
  it('returns empty string for falsy values', () => {
    expect(formatSize(0)).toBe('');
    expect(formatSize(null)).toBe('');
    expect(formatSize(undefined)).toBe('');
  });

  it('formats bytes (< 1 KB)', () => {
    expect(formatSize(1)).toBe('1 B');
    expect(formatSize(512)).toBe('512 B');
    expect(formatSize(1023)).toBe('1023 B');
  });

  it('formats kilobytes (1 KB to < 1 MB)', () => {
    expect(formatSize(1024)).toBe('1.0 KB');
    expect(formatSize(1536)).toBe('1.5 KB');
    expect(formatSize(1024 * 500)).toBe('500.0 KB');
    expect(formatSize(1024 * 1024 - 1)).toBe('1024.0 KB');
  });

  it('formats megabytes (>= 1 MB)', () => {
    expect(formatSize(1024 * 1024)).toBe('1.0 MB');
    expect(formatSize(1024 * 1024 * 5.5)).toBe('5.5 MB');
    expect(formatSize(1024 * 1024 * 100)).toBe('100.0 MB');
  });
});
