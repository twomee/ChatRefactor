// src/pages/LoginPage.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import * as authApi from '../services/authApi';
import Logo from '../components/common/Logo';

export default function LoginPage() {
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  // ── 2FA state ───────────────────────────────────────────────────────
  const [needs2FA, setNeeds2FA] = useState(false);
  const [tempToken, setTempToken] = useState('');
  const [totpCode, setTotpCode] = useState('');

  // ── Forgot password state ──────────────────────────────────────────
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotMessage, setForgotMessage] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    try {
      if (mode === 'register') {
        await authApi.register(username, password, email);
        setMode('login');
        setError('Registered! Now log in.');
      } else {
        const res = await authApi.login(username, password);
        // Check if 2FA is required
        if (res.data.requires_2fa) {
          setNeeds2FA(true);
          setTempToken(res.data.temp_token);
          setTotpCode('');
          return;
        }
        login(res.data.access_token, {
          username: res.data.username,
          is_global_admin: res.data.is_global_admin,
          user_id: res.data.user_id,
        });
        navigate('/chat');
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map(e => e.msg).join(', '));
      } else {
        setError(detail || 'Something went wrong');
      }
    }
  }

  function handleTotpChange(e) {
    setTotpCode(e.target.value.replaceAll(/\D/g, '').slice(0, 6));
  }

  async function handle2FASubmit(e) {
    e.preventDefault();
    setError('');
    try {
      const res = await authApi.verifyLogin2FA(tempToken, totpCode);
      login(res.data.access_token, {
        username: res.data.username,
        is_global_admin: res.data.is_global_admin,
      });
      navigate('/chat');
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map(e => e.msg).join(', '));
      } else {
        setError(detail || 'Invalid code');
      }
    }
  }

  function handleBack2FA() {
    setNeeds2FA(false);
    setTempToken('');
    setTotpCode('');
    setError('');
  }

  async function handleForgotPassword(e) {
    e.preventDefault();
    setForgotMessage('');
    setForgotLoading(true);
    try {
      await authApi.forgotPassword(forgotEmail);
      setForgotMessage('If an account exists with that email, a reset link has been sent.');
      setForgotEmail('');
    } catch {
      // Always show the same message to prevent email enumeration
      setForgotMessage('If an account exists with that email, a reset link has been sent.');
    } finally {
      setForgotLoading(false);
    }
  }

  function handleBackFromForgot() {
    setShowForgotPassword(false);
    setForgotEmail('');
    setForgotMessage('');
    setError('');
  }

  // ── Forgot password view ───────────────────────────────────────────
  if (showForgotPassword) {
    return (
      <div className="login-wrapper">
        <div className="login-card">
          <div className="login-header">
            <Logo />
            <p className="login-subtitle">Reset Your Password</p>
          </div>

          <form onSubmit={handleForgotPassword} className="login-form">
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', textAlign: 'center' }}>
              Enter your email address and we will send you a link to reset your password.
            </p>
            <input
              type="email"
              placeholder="Email address"
              value={forgotEmail}
              onChange={e => setForgotEmail(e.target.value)}
              required
              autoFocus
              data-testid="forgot-email-input"
            />
            {forgotMessage && (
              <p className="login-error success">{forgotMessage}</p>
            )}
            <button
              type="submit"
              className="btn-primary"
              disabled={forgotLoading || !forgotEmail.trim()}
            >
              {forgotLoading ? 'Sending...' : 'Send Reset Link'}
            </button>
            <button
              type="button"
              className="btn-ghost"
              onClick={handleBackFromForgot}
              style={{ textAlign: 'center' }}
            >
              Back to Login
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ── 2FA code input view ──────────────────────────────────────────────
  if (needs2FA) {
    return (
      <div className="login-wrapper">
        <div className="login-card">
          <div className="login-header">
            <Logo />
            <p className="login-subtitle">Two-Factor Authentication</p>
          </div>

          <form onSubmit={handle2FASubmit} className="login-form">
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', textAlign: 'center' }}>
              Enter the 6-digit code from your authenticator app.
            </p>
            <input
              type="text"
              placeholder="000000"
              value={totpCode}
              onChange={handleTotpChange}
              required
              autoFocus
              maxLength={6}
              style={{ textAlign: 'center', letterSpacing: '0.3em', fontSize: '1.25rem' }}
              data-testid="totp-input"
            />
            {error && (
              <p className="login-error error">{error}</p>
            )}
            <button
              type="submit"
              className="btn-primary"
              disabled={totpCode.length !== 6}
            >
              Verify
            </button>
            <button
              type="button"
              className="btn-ghost"
              onClick={handleBack2FA}
              style={{ textAlign: 'center' }}
            >
              Back to Login
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ── Normal login/register view ───────────────────────────────────────
  return (
    <div className="login-wrapper">
      <div className="login-card">
        <div className="login-header">
          <Logo />
          <p className="login-subtitle">Connect and chat in real time</p>
        </div>

        <div className="login-tabs">
          <button
            className={`login-tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => setMode('login')}
          >
            Sign In
          </button>
          <button
            className={`login-tab ${mode === 'register' ? 'active' : ''}`}
            onClick={() => setMode('register')}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <input
            placeholder="Username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required
            autoFocus
          />
          {mode === 'register' && (
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
          )}
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
          />
          {error && (
            <p className={`login-error ${mode === 'login' && !error.includes('Registered') ? 'error' : 'success'}`}>
              {error}
            </p>
          )}
          <button type="submit" className="btn-primary">
            {mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>
          {mode === 'login' && (
            <button
              type="button"
              className="btn-ghost forgot-password-link"
              onClick={() => setShowForgotPassword(true)}
              style={{ textAlign: 'center', fontSize: '0.8125rem' }}
            >
              Forgot password?
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
