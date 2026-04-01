// src/context/ToastContext.jsx
import { createContext, useContext, useState, useCallback, useMemo } from 'react';
import PropTypes from 'prop-types';

const ToastContext = createContext(null);

/**
 * @typedef {{ id: string, type: 'danger'|'warning'|'info'|'success', title: string, message: string }} Toast
 */

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  /**
   * Show a toast notification.
   * @param {'danger'|'warning'|'info'|'success'} type
   * @param {string} title
   * @param {string} message
   * @param {number} [duration=4000] ms before auto-dismiss
   */
  const showToast = useCallback((type, title, message, duration = 4000) => {
    const id = crypto.randomUUID();
    setToasts(prev => [...prev.slice(-3), { id, type, title, message }]);
    setTimeout(() => removeToast(id), duration);
  }, [removeToast]);

  const value = useMemo(() => ({ toasts, showToast, removeToast }), [toasts, showToast, removeToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
    </ToastContext.Provider>
  );
}

ToastProvider.propTypes = { children: PropTypes.node.isRequired };

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
}
