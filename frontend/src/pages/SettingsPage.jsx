// src/pages/SettingsPage.jsx
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Logo from '../components/common/Logo';
import ProfileSection from '../components/settings/ProfileSection';
import TwoFactorSetup from '../components/settings/TwoFactorSetup';

export default function SettingsPage() {
  const navigate = useNavigate();

  // Add page-active class on mount so the one-shot aurora animation plays,
  // and remove it on unmount so the login page returns to the static gradient.
  useEffect(() => {
    document.body.classList.add('page-active');
    return () => document.body.classList.remove('page-active');
  }, []);

  return (
    <div className="settings-layout">
      <header className="settings-page-header glass-panel">
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <Logo />
          <h1 className="settings-title">Settings</h1>
        </div>
        <button onClick={() => navigate('/chat')} className="btn-ghost" data-testid="back-to-chat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"/>
            <polyline points="12 19 5 12 12 5"/>
          </svg>
          Back to Chat
        </button>
      </header>

      <div className="settings-content">
        <div className="settings-grid">
          <div className="settings-section glass-panel">
            <h2 className="settings-section-title">Profile</h2>
            <ProfileSection />
          </div>

          <div className="settings-section glass-panel">
            <h2 className="settings-section-title">Security</h2>
            <TwoFactorSetup />
          </div>
        </div>
      </div>
    </div>
  );
}
