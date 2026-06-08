import React, { useCallback } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useToastStore } from '../../stores/toast-store';
import './Toast.css';

function ToastIcon({ type }: { type: string }) {
  if (type === 'success') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    );
  }
  if (type === 'error') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="15" y1="9" x2="9" y2="15" />
        <line x1="9" y1="9" x2="15" y2="15" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

export default function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  const removeToast = useToastStore((s) => s.removeToast);

  const handleClose = useCallback((id: string) => {
    removeToast(id);
  }, [removeToast]);

  return (
    <div className="toast-container" role="region" aria-live="polite" aria-label="通知">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            className={`toast-item ${t.type}`}
            role="status"
            initial={{ opacity: 0, x: 48, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 48, scale: 0.95 }}
            transition={{ type: 'spring', duration: 0.4, bounce: 0.2 }}
          >
            <span className="toast-icon">
              <ToastIcon type={t.type} />
            </span>
            <span className="toast-message">{t.message}</span>
            <button
              className="toast-close"
              onClick={() => handleClose(t.id)}
              aria-label="关闭通知"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
