// src/components/settings/ProfileSection.jsx
import { useState, useEffect } from 'react';
import * as authApi from '../../services/authApi';

/**
 * ProfileSection -- Profile management forms for the Settings page.
 * Contains two forms: Change Email and Change Password.
 */
export default function ProfileSection() {
  // ── Email form state ────────────────────────────────────────────────
  const [currentEmail, setCurrentEmail] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [emailPassword, setEmailPassword] = useState('');
  const [emailSuccess, setEmailSuccess] = useState('');
  const [emailError, setEmailError] = useState('');
  const [emailLoading, setEmailLoading] = useState(false);

  // ── Password form state ─────────────────────────────────────────────
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);

  // Fetch current profile on mount
  useEffect(() => {
    async function fetchProfile() {
      try {
        const profile = await authApi.getProfile();
        setCurrentEmail(profile.email || '');
      } catch {
        // Profile endpoint may not return email — silently ignore
      }
    }
    fetchProfile();
  }, []);

  // ── Email submit ────────────────────────────────────────────────────
  async function handleEmailSubmit(e) {
    e.preventDefault();
    setEmailError('');
    setEmailSuccess('');

    if (!newEmail.trim()) {
      setEmailError('Please enter a new email address.');
      return;
    }

    setEmailLoading(true);
    try {
      await authApi.updateEmail(newEmail.trim(), emailPassword);
      setEmailSuccess('Email updated successfully.');
      setCurrentEmail(newEmail.trim());
      setNewEmail('');
      setEmailPassword('');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setEmailError(Array.isArray(detail) ? detail[0]?.msg || 'Validation error.' : detail || 'Failed to update email.');
    } finally {
      setEmailLoading(false);
    }
  }

  // ── Password submit ─────────────────────────────────────────────────
  async function handlePasswordSubmit(e) {
    e.preventDefault();
    setPasswordError('');
    setPasswordSuccess('');

    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match.');
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError('New password must be at least 8 characters.');
      return;
    }

    setPasswordLoading(true);
    try {
      await authApi.updatePassword(currentPassword, newPassword);
      setPasswordSuccess('Password updated successfully.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setPasswordError(Array.isArray(detail) ? detail[0]?.msg || 'Validation error.' : detail || 'Failed to update password.');
    } finally {
      setPasswordLoading(false);
    }
  }

  return (
    <div className="profile-section">
      {/* ── Change Email ─────────────────────────────────────────────── */}
      <form onSubmit={handleEmailSubmit} className="settings-form">
        <h3 className="settings-form-heading">Change Email</h3>

        {currentEmail && (
          <p className="settings-current-value">
            Current email: <strong>{currentEmail}</strong>
          </p>
        )}

        {emailError && <p className="settings-error">{emailError}</p>}
        {emailSuccess && <p className="settings-success">{emailSuccess}</p>}

        <div className="settings-form-group">
          <label htmlFor="new-email">New Email</label>
          <input
            id="new-email"
            type="email"
            className="settings-input"
            placeholder="new@example.com"
            value={newEmail}
            onChange={e => setNewEmail(e.target.value)}
            required
          />
        </div>

        <div className="settings-form-group">
          <label htmlFor="email-password">Current Password</label>
          <input
            id="email-password"
            type="password"
            className="settings-input"
            placeholder="Enter current password"
            value={emailPassword}
            onChange={e => setEmailPassword(e.target.value)}
            required
          />
        </div>

        <button type="submit" className="settings-btn btn-accent" disabled={emailLoading}>
          {emailLoading ? 'Updating...' : 'Update Email'}
        </button>
      </form>

      {/* ── Change Password ──────────────────────────────────────────── */}
      <form onSubmit={handlePasswordSubmit} className="settings-form">
        <h3 className="settings-form-heading">Change Password</h3>

        {passwordError && <p className="settings-error">{passwordError}</p>}
        {passwordSuccess && <p className="settings-success">{passwordSuccess}</p>}

        <div className="settings-form-group">
          <label htmlFor="current-password">Current Password</label>
          <input
            id="current-password"
            type="password"
            className="settings-input"
            placeholder="Enter current password"
            value={currentPassword}
            onChange={e => setCurrentPassword(e.target.value)}
            required
          />
        </div>

        <div className="settings-form-group">
          <label htmlFor="new-password">New Password</label>
          <input
            id="new-password"
            type="password"
            className="settings-input"
            placeholder="Enter new password"
            value={newPassword}
            onChange={e => setNewPassword(e.target.value)}
            required
            minLength={6}
          />
        </div>

        <div className="settings-form-group">
          <label htmlFor="confirm-password">Confirm New Password</label>
          <input
            id="confirm-password"
            type="password"
            className="settings-input"
            placeholder="Confirm new password"
            value={confirmPassword}
            onChange={e => setConfirmPassword(e.target.value)}
            required
            minLength={6}
          />
        </div>

        <button type="submit" className="settings-btn btn-accent" disabled={passwordLoading}>
          {passwordLoading ? 'Updating...' : 'Update Password'}
        </button>
      </form>
    </div>
  );
}
