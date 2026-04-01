// utils/loginHelpers.js — Pure helpers for login/register form logic

/**
 * Validates a single form field and returns an error string or null.
 * @param {string} name - Field name: 'username' | 'email' | 'password'
 * @param {string} value - Current field value
 * @param {string} mode - Form mode: 'login' | 'register'
 * @returns {string|null} Error message or null if valid
 */
export function validateField(name, value, mode) {
  switch (name) {
    case 'username':
      if (!value.trim()) return 'Username is required';
      if (value.trim().length < 3) return 'Must be at least 3 characters';
      return null;
    case 'email':
      if (!value.trim()) return 'Email is required';
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return 'Enter a valid email address';
      return null;
    case 'password':
      if (!value) return 'Password is required';
      if (mode === 'register' && value.length < 6) return 'Must be at least 6 characters';
      return null;
    default:
      return null;
  }
}

/**
 * Maps raw backend error detail to a human-readable message.
 * Passes through readable strings unchanged; only maps ugly DB/framework errors.
 * @param {string|Array|undefined} detail - Backend error detail
 * @returns {string} Human-readable error message
 */
export function humanizeError(detail) {
  if (!detail) return 'Something went wrong';
  if (typeof detail === 'string') {
    if (
      detail.toLowerCase().includes('unique constraint') ||
      detail.toLowerCase().includes('already registered')
    ) {
      return 'That username is already taken. Try another.';
    }
    return detail;
  }
  if (Array.isArray(detail)) return detail.map(e => e.msg).join(', ');
  return 'Something went wrong';
}

/**
 * Calculates password strength based on length and character variety.
 * @param {string} pwd - Password to evaluate
 * @returns {{level: string, label: string, bars: number}|null}
 */
export function getPasswordStrength(pwd) {
  if (!pwd) return null;
  let score = 0;
  if (pwd.length >= 8) score++;
  if (pwd.length >= 12) score++;
  if (/[A-Z]/.test(pwd)) score++;
  if (/[0-9]/.test(pwd)) score++;
  if (/[^A-Za-z0-9]/.test(pwd)) score++;
  if (score <= 1) return { level: 'weak', label: 'Weak', bars: 1 };
  if (score <= 3) return { level: 'fair', label: 'Fair', bars: 2 };
  return { level: 'strong', label: 'Strong', bars: 3 };
}
