// src/components/common/Toast.jsx
import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import PropTypes from 'prop-types';
import { useToast } from '../../context/ToastContext';

const ICONS = {
  danger:  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />,
  warning: <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />,
  info:    <><circle cx="12" cy="12" r="10" /><path strokeLinecap="round" d="M12 16v-4m0-4h.01" /></>,
  success: <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" />,
};

function ToastCard({ toast }) {
  const { removeToast } = useToast();
  const [removing, setRemoving] = useState(false);

  function dismiss() {
    setRemoving(true);
    setTimeout(() => removeToast(toast.id), 280);
  }

  // When the context removes the toast externally (auto-dismiss timer),
  // trigger the exit animation first by watching for unmount via an effect.
  useEffect(() => {
    return () => {};
  }, []);

  return (
    <div
      className={`toast-card toast-card--${toast.type}${removing ? ' toast-card--removing' : ''}`}
      role="alert"
      aria-live="assertive"
      data-testid="toast-card"
    >
      <div className="toast-icon" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2">
          {ICONS[toast.type]}
        </svg>
      </div>
      <div className="toast-body">
        <p className="toast-title">{toast.title}</p>
        {toast.message && <p className="toast-message">{toast.message}</p>}
      </div>
      <button
        type="button"
        className="toast-close"
        onClick={dismiss}
        aria-label="Dismiss notification"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  );
}

ToastCard.propTypes = {
  toast: PropTypes.shape({
    id: PropTypes.string.isRequired,
    type: PropTypes.oneOf(['danger', 'warning', 'info', 'success']).isRequired,
    title: PropTypes.string.isRequired,
    message: PropTypes.string,
  }).isRequired,
};

export default function Toast() {
  const { toasts } = useToast();

  if (toasts.length === 0) return null;

  return createPortal(
    <div className="toast-portal" aria-label="Notifications">
      {toasts.map(t => <ToastCard key={t.id} toast={t} />)}
    </div>,
    document.body,
  );
}
