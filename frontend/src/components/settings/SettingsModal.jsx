// src/components/settings/SettingsModal.jsx
import { useEffect, useRef } from 'react';
import TwoFactorSetup from './TwoFactorSetup';

/**
 * SettingsModal — Slide-over panel for user account settings.
 * Currently contains the TwoFactorSetup component. Extensible for
 * future settings (profile, theme, notifications, etc.)
 */
export default function SettingsModal({ open, onClose }) {
  const backdropRef = useRef(null);

  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    function handleKey(e) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={backdropRef}
      className="settings-backdrop"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
      onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) onClose(); }}
      tabIndex={-1}
    >
      <div className="settings-panel glass-panel" role="dialog" aria-label="Settings">
        <div className="settings-header">
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Settings</h3>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Close settings">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div className="settings-body">
          <TwoFactorSetup />
        </div>
      </div>
    </div>
  );
}
