import { describe, it, expect } from 'vitest';
import { validateField, humanizeError, getPasswordStrength } from '../loginHelpers';

describe('validateField', () => {
  it('returns error for empty username', () => {
    expect(validateField('username', '', 'login')).toBe('Username is required');
    expect(validateField('username', '  ', 'login')).toBe('Username is required');
  });

  it('returns error for username shorter than 3 chars', () => {
    expect(validateField('username', 'ab', 'login')).toBe('Must be at least 3 characters');
  });

  it('returns null for valid username', () => {
    expect(validateField('username', 'alice', 'login')).toBeNull();
    expect(validateField('username', 'alice_123', 'register')).toBeNull();
  });

  it('returns error for empty email', () => {
    expect(validateField('email', '', 'register')).toBe('Email is required');
    expect(validateField('email', '   ', 'register')).toBe('Email is required');
  });

  it('returns error for invalid email', () => {
    expect(validateField('email', 'notanemail', 'register')).toBe('Enter a valid email address');
    expect(validateField('email', 'missing@tld', 'register')).toBe('Enter a valid email address');
  });

  it('returns null for valid email', () => {
    expect(validateField('email', 'user@example.com', 'register')).toBeNull();
    expect(validateField('email', 'a+b@sub.domain.io', 'register')).toBeNull();
  });

  it('returns error for empty password', () => {
    expect(validateField('password', '', 'login')).toBe('Password is required');
    expect(validateField('password', '', 'register')).toBe('Password is required');
  });

  it('returns error for short password in register mode only', () => {
    expect(validateField('password', 'abc', 'register')).toBe('Must be at least 6 characters');
    expect(validateField('password', 'abc', 'login')).toBeNull();
  });

  it('returns null for valid password in register mode', () => {
    expect(validateField('password', 'secure1', 'register')).toBeNull();
  });

  it('returns null for unknown field names', () => {
    expect(validateField('unknown', 'any', 'login')).toBeNull();
  });
});

describe('humanizeError', () => {
  it('returns fallback for undefined or null', () => {
    expect(humanizeError(undefined)).toBe('Something went wrong');
    expect(humanizeError(null)).toBe('Something went wrong');
  });

  it('maps UNIQUE constraint to friendly message', () => {
    expect(humanizeError('UNIQUE constraint failed: user.username')).toBe(
      'That username is already taken. Try another.',
    );
  });

  it('maps already registered to friendly message (case-insensitive)', () => {
    expect(humanizeError('User already registered')).toBe(
      'That username is already taken. Try another.',
    );
  });

  it('passes through readable backend strings unchanged', () => {
    expect(humanizeError('Invalid credentials')).toBe('Invalid credentials');
    expect(humanizeError('Account is disabled')).toBe('Account is disabled');
  });

  it('joins array detail messages with comma separator', () => {
    const detail = [{ msg: 'field required' }, { msg: 'value too short' }];
    expect(humanizeError(detail)).toBe('field required, value too short');
  });

  it('returns fallback for non-string non-array non-null input', () => {
    expect(humanizeError(42)).toBe('Something went wrong');
    expect(humanizeError({})).toBe('Something went wrong');
  });
});

describe('getPasswordStrength', () => {
  it('returns null for empty or falsy password', () => {
    expect(getPasswordStrength('')).toBeNull();
    expect(getPasswordStrength(null)).toBeNull();
    expect(getPasswordStrength(undefined)).toBeNull();
  });

  it('returns weak for a very simple short password', () => {
    const result = getPasswordStrength('abc');
    expect(result.level).toBe('weak');
    expect(result.label).toBe('Weak');
    expect(result.bars).toBe(1);
  });

  it('returns fair for a moderate password (8+ chars with digits)', () => {
    const result = getPasswordStrength('password1');
    expect(result.level).toBe('fair');
    expect(result.label).toBe('Fair');
    expect(result.bars).toBe(2);
  });

  it('returns strong for a complex long password', () => {
    // Constructed to hit all 5 scoring criteria: 12+ chars, uppercase, digit, special
    const strong = 'Aa1!' + 'x'.repeat(10);
    const result = getPasswordStrength(strong);
    expect(result.level).toBe('strong');
    expect(result.label).toBe('Strong');
    expect(result.bars).toBe(3);
  });

  it('score increases with length, uppercase, digits, and special chars', () => {
    const weak = getPasswordStrength('abc');
    const fair = getPasswordStrength('abcdefgh1'); // 8+ chars + digit
    const strong = getPasswordStrength('Aa1!' + 'x'.repeat(10)); // 14 chars, all criteria met

    expect(weak.bars).toBeLessThan(fair.bars);
    expect(fair.bars).toBeLessThan(strong.bars);
  });
});
