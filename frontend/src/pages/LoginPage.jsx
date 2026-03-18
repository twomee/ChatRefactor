// src/pages/LoginPage.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import * as authApi from '../services/authApi';

export default function LoginPage() {
  const [mode, setMode] = useState('login');   // 'login' | 'register'
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
    <div style={{ maxWidth: 360, margin: '100px auto', padding: 24, border: '1px solid #ccc', borderRadius: 8 }}>
      <h2>cHATBOX</h2>
      <div style={{ marginBottom: 16 }}>
        <button onClick={() => setMode('login')} disabled={mode === 'login'}>Login</button>
        <button onClick={() => setMode('register')} disabled={mode === 'register'} style={{ marginLeft: 8 }}>Register</button>
      </div>
      <form onSubmit={handleSubmit}>
        <input placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} required style={{ display: 'block', width: '100%', marginBottom: 8 }} />
        <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required style={{ display: 'block', width: '100%', marginBottom: 8 }} />
        {error && <p style={{ color: mode === 'login' ? 'red' : 'green' }}>{error}</p>}
        <button type="submit" style={{ width: '100%' }}>{mode === 'login' ? 'Login' : 'Register'}</button>
      </form>
    </div>
  );
}
