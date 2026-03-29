// src/components/settings/TwoFactorSetup.jsx
import { useState, useEffect } from 'react';
import * as authApi from '../../services/authApi';

/**
 * TwoFactorSetup — Allows a user to enable or disable TOTP-based 2FA.
 *
 * States:
 * 1. Loading — checking current 2FA status
 * 2. Disabled — shows "Enable 2FA" button
 * 3. Setup — shows secret + otpauth URI + verification input
 * 4. Enabled — shows "Disable 2FA" button with code input
 */
export default function TwoFactorSetup() {
  const [status, setStatus] = useState(null); // null = loading
  const [setupData, setSetupData] = useState(null); // { secret, otpauth_uri }
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchStatus();
  }, []);

  async function fetchStatus() {
    try {
      const res = await authApi.get2FAStatus();
      setStatus(res.data.is_2fa_enabled);
    } catch {
      setError('Could not load 2FA status');
      setStatus(false);
    }
  }

  async function handleSetup() {
    setError('');
    setSuccess('');
    setLoading(true);
    try {
      const res = await authApi.setup2FA();
      setSetupData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Setup failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifySetup(e) {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);
    try {
      await authApi.verifySetup2FA(code);
      setSuccess('2FA enabled successfully!');
      setSetupData(null);
      setCode('');
      setStatus(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Verification failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleDisable(e) {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);
    try {
      await authApi.disable2FA(code);
      setSuccess('2FA disabled.');
      setCode('');
      setStatus(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not disable 2FA');
    } finally {
      setLoading(false);
    }
  }

  function handleCancelSetup() {
    setSetupData(null);
    setCode('');
    setError('');
  }

  if (status === null) {
    return <div className="tfa-panel"><p style={{ color: 'var(--text-muted)' }}>Loading 2FA status...</p></div>;
  }

  return (
    <div className="tfa-panel">
      <h4 style={{ margin: '0 0 12px', fontSize: '0.9rem', fontWeight: 600 }}>
        Two-Factor Authentication
      </h4>

      {error && <p className="tfa-msg tfa-error">{error}</p>}
      {success && <p className="tfa-msg tfa-success">{success}</p>}

      {/* ── 2FA is disabled and no setup in progress ─────────────── */}
      {!status && !setupData && (
        <div>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: 12 }}>
            Add an extra layer of security by requiring a code from your authenticator app on each login.
          </p>
          <button
            className="btn-accent btn-sm"
            onClick={handleSetup}
            disabled={loading}
          >
            {loading ? 'Setting up...' : 'Enable 2FA'}
          </button>
        </div>
      )}

      {/* ── Setup in progress: show secret + verification ────────── */}
      {!status && setupData && (
        <div>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: 8 }}>
            Scan the URI below with your authenticator app, or enter the secret key manually.
          </p>
          <div style={{
            background: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 'var(--radius)',
            padding: '10px 12px',
            marginBottom: 12,
            wordBreak: 'break-all',
            fontSize: '0.75rem',
            color: 'var(--text)',
          }}>
            <strong>Secret:</strong> {setupData.secret}
          </div>
          <div style={{
            background: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 'var(--radius)',
            padding: '10px 12px',
            marginBottom: 12,
            wordBreak: 'break-all',
            fontSize: '0.7rem',
            color: 'var(--text-muted)',
          }}>
            <strong>URI:</strong> {setupData.otpauth_uri}
          </div>
          <form onSubmit={handleVerifySetup} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              placeholder="6-digit code"
              value={code}
              onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              maxLength={6}
              style={{ width: 120, textAlign: 'center', letterSpacing: '0.2em' }}
              data-testid="tfa-setup-code"
            />
            <button
              type="submit"
              className="btn-accent btn-sm"
              disabled={code.length !== 6 || loading}
            >
              {loading ? 'Verifying...' : 'Verify & Enable'}
            </button>
            <button
              type="button"
              className="btn-ghost btn-sm"
              onClick={handleCancelSetup}
            >
              Cancel
            </button>
          </form>
        </div>
      )}

      {/* ── 2FA is enabled: show disable option ──────────────────── */}
      {status && (
        <div>
          <p style={{ fontSize: '0.8125rem', color: 'var(--success)', marginBottom: 12 }}>
            2FA is currently enabled.
          </p>
          <form onSubmit={handleDisable} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              placeholder="Enter code to disable"
              value={code}
              onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              maxLength={6}
              style={{ width: 160, textAlign: 'center', letterSpacing: '0.2em' }}
              data-testid="tfa-disable-code"
            />
            <button
              type="submit"
              className="btn-danger btn-sm"
              disabled={code.length !== 6 || loading}
            >
              {loading ? 'Disabling...' : 'Disable 2FA'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
