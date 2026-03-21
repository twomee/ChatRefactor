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
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    try {
      if (mode === 'register') {
        await authApi.register(username, password);
        setMode('login');
        setError('Registered! Now log in.');
      } else {
        const res = await authApi.login(username, password);
        login(res.data.access_token, {
          username: res.data.username,
          is_global_admin: res.data.is_global_admin,
        });
        navigate('/chat');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong');
    }
  }

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
        </form>
      </div>
    </div>
  );
}
