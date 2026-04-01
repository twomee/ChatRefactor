// src/pages/LoginPage.jsx
import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import * as authApi from '../services/authApi';
import Logo from '../components/common/Logo';
import { validateField, humanizeError, getPasswordStrength } from '../utils/loginHelpers';

// ── Inline SVG icons (no npm package) ─────────────────────────────────────
function EyeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  );
}

function Spinner() {
  return <span className="btn-spinner" aria-hidden="true" />;
}

function PasswordStrength({ password }) {
  const strength = getPasswordStrength(password);
  if (!strength) return null;
  return (
    <div className="password-strength" data-testid="password-strength">
      <div className="strength-bars">
        {[1, 2, 3].map(n => (
          <div key={n} className={`strength-bar ${n <= strength.bars ? strength.level : ''}`} />
        ))}
      </div>
      <span className={`strength-label ${strength.level}`}>{strength.label}</span>
    </div>
  );
}

export default function LoginPage() {
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  // ── UX state ─────────────────────────────────────────────────────────────
  const [fieldErrors, setFieldErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [isShaking, setIsShaking] = useState(false);

  // ── 2FA state ─────────────────────────────────────────────────────────────
  const [needs2FA, setNeeds2FA] = useState(false);
  const [tempToken, setTempToken] = useState('');
  const [totpCode, setTotpCode] = useState('');

  // ── Forgot password state ─────────────────────────────────────────────────
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotMessage, setForgotMessage] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);

  const usernameRef = useRef(null);

  // Auto-focus username when switching tabs
  useEffect(() => {
    usernameRef.current?.focus();
  }, [mode]);

  // Auto-clear shake after animation completes
  useEffect(() => {
    if (!isShaking) return;
    const t = setTimeout(() => setIsShaking(false), 500);
    return () => clearTimeout(t);
  }, [isShaking]);

  // ── Validation ────────────────────────────────────────────────────────────
  function handleBlur(e) {
    const { name, value } = e.target;
    const err = validateField(name, value, mode);
    setFieldErrors(prev => ({ ...prev, [name]: err }));
  }

  function validateAll() {
    const errs = {};
    const uErr = validateField('username', username, mode);
    if (uErr) errs.username = uErr;
    if (mode === 'register') {
      const eErr = validateField('email', email, mode);
      if (eErr) errs.email = eErr;
    }
    const pErr = validateField('password', password, mode);
    if (pErr) errs.password = pErr;
    return errs;
  }

  function handleTabSwitch(newMode) {
    setMode(newMode);
    setFieldErrors({});
    setShowPassword(false);
  }

  // ── Main submit ───────────────────────────────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault();
    setFieldErrors({});

    const errs = validateAll();
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      setIsShaking(true);
      return;
    }

    setIsLoading(true);
    try {
      if (mode === 'register') {
        await authApi.register(username, password, email);
        setFieldErrors({ form: 'Registered! Now log in.' });
        setMode('login');
      } else {
        const res = await authApi.login(username, password);
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
      setIsShaking(true);
      setFieldErrors(prev => ({ ...prev, form: humanizeError(detail) }));
    } finally {
      setIsLoading(false);
    }
  }

  function handleTotpChange(e) {
    setTotpCode(e.target.value.replaceAll(/\D/g, '').slice(0, 6));
  }

  async function handle2FASubmit(e) {
    e.preventDefault();
    setFieldErrors({});
    setIsLoading(true);
    try {
      const res = await authApi.verifyLogin2FA(tempToken, totpCode);
      login(res.data.access_token, {
        username: res.data.username,
        is_global_admin: res.data.is_global_admin,
      });
      navigate('/chat');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setIsShaking(true);
      setFieldErrors({ form: humanizeError(detail) });
    } finally {
      setIsLoading(false);
    }
  }

  function handleBack2FA() {
    setNeeds2FA(false);
    setTempToken('');
    setTotpCode('');
    setFieldErrors({});
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
    setFieldErrors({});
  }

  // ── Forgot password view ──────────────────────────────────────────────────
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

  // ── 2FA code input view ───────────────────────────────────────────────────
  if (needs2FA) {
    return (
      <div className="login-wrapper">
        <div className={`login-card ${isShaking ? 'shake' : ''}`}>
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
              className="totp-single-input"
              data-testid="totp-input"
            />
            {fieldErrors.form && (
              <p className="login-error error">{fieldErrors.form}</p>
            )}
            <button
              type="submit"
              className="btn-primary"
              disabled={totpCode.length !== 6 || isLoading}
            >
              {isLoading ? <><Spinner /> Verifying…</> : 'Verify'}
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

  // ── Normal login/register view ────────────────────────────────────────────
  return (
    <div className="login-wrapper">
      <div className={`login-card ${isShaking ? 'shake' : ''}`}>
        <div className="login-header">
          <Logo />
          <p className="login-subtitle">
            {mode === 'login' ? 'Welcome back' : 'Create your account'}
          </p>
        </div>

        <div className="login-tabs">
          <button
            className={`login-tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => handleTabSwitch('login')}
          >
            Sign In
          </button>
          <button
            className={`login-tab ${mode === 'register' ? 'active' : ''}`}
            onClick={() => handleTabSwitch('register')}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          {/* Username */}
          <div className="field-group">
            <input
              ref={usernameRef}
              name="username"
              placeholder="Username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              onBlur={handleBlur}
              className={fieldErrors.username ? 'input-error' : ''}
              required
            />
            {fieldErrors.username && <p className="field-error">{fieldErrors.username}</p>}
          </div>

          {/* Email — animated collapse, shown only in register mode */}
          <div className={`field-collapse ${mode === 'register' ? 'expanded' : ''}`}>
            <div className="field-collapse-inner">
              <div className="field-group">
                <input
                  name="email"
                  type="email"
                  placeholder="Email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  onBlur={handleBlur}
                  className={fieldErrors.email ? 'input-error' : ''}
                  required={mode === 'register'}
                />
                {fieldErrors.email && <p className="field-error">{fieldErrors.email}</p>}
              </div>
            </div>
          </div>

          {/* Password with visibility toggle + strength meter */}
          <div className="field-group">
            <div className="input-with-icon">
              <input
                name="password"
                type={showPassword ? 'text' : 'password'}
                placeholder="Password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onBlur={handleBlur}
                className={fieldErrors.password ? 'input-error' : ''}
                required
              />
              <button
                type="button"
                className="input-icon-btn"
                tabIndex={-1}
                onClick={() => setShowPassword(v => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
            {fieldErrors.password && <p className="field-error">{fieldErrors.password}</p>}
            {mode === 'register' && password.length > 0 && (
              <PasswordStrength password={password} />
            )}
          </div>

          {/* Form-level feedback (errors and success messages) */}
          {fieldErrors.form && (
            <p className={`login-error ${fieldErrors.form === 'Registered! Now log in.' ? 'success' : 'error'}`}>
              {fieldErrors.form}
            </p>
          )}

          <button type="submit" className="btn-primary" disabled={isLoading}>
            {isLoading
              ? <><Spinner /> {mode === 'login' ? 'Signing in…' : 'Creating account…'}</>
              : (mode === 'login' ? 'Sign In' : 'Create Account')
            }
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
