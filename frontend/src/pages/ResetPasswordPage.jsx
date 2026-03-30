// src/pages/ResetPasswordPage.jsx
import { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import * as authApi from '../services/authApi';
import Logo from '../components/common/Logo';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (newPassword.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    if (!token) {
      setError('Invalid or missing reset token.');
      return;
    }

    setLoading(true);
    try {
      await authApi.resetPassword(token, newPassword);
      setSuccess(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to reset password. The link may have expired.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <div className="login-header">
          <Logo />
          <p className="login-subtitle">Reset Your Password</p>
        </div>

        {success ? (
          <div className="login-form" style={{ textAlign: 'center' }}>
            <p className="login-error success">
              Your password has been reset successfully.
            </p>
            <Link to="/login" className="btn-primary" style={{ display: 'inline-block', textDecoration: 'none', textAlign: 'center', padding: '10px 20px' }}>
              Back to Login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="login-form">
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', textAlign: 'center' }}>
              Enter your new password below.
            </p>
            <input
              type="password"
              placeholder="New password"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              required
              autoFocus
              minLength={6}
              data-testid="reset-new-password"
            />
            <input
              type="password"
              placeholder="Confirm new password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              required
              minLength={6}
              data-testid="reset-confirm-password"
            />
            {error && (
              <p className="login-error error">{error}</p>
            )}
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Resetting...' : 'Reset Password'}
            </button>
            <Link
              to="/login"
              className="btn-ghost"
              style={{ textAlign: 'center', textDecoration: 'none', display: 'block' }}
            >
              Back to Login
            </Link>
          </form>
        )}
      </div>
    </div>
  );
}
