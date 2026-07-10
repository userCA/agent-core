import React, { useState, useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useSessionStore } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import { AUTH_KEYS } from '../../config';
import './AuthModal.css';

export default function AuthModal() {
  const { authHeaders, saveAuth } = useSessionStore();
  const authModalOpen = useUIStore((s) => s.authModalOpen);
  const setAuthModalOpen = useUIStore((s) => s.setAuthModalOpen);
  const modalRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const k of AUTH_KEYS) init[k] = authHeaders[k] || '';
    return init;
  });

  useEffect(() => {
    if (!authModalOpen) return;
    // Remember previously focused element
    previousFocusRef.current = document.activeElement as HTMLElement;
    // Move focus into the modal (first input)
    const firstInput = modalRef.current?.querySelector('input');
    firstInput?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setAuthModalOpen(false);
      }
      if (e.key === 'Tab') {
        // Simple focus trap
        const focusable = modalRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusable || focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      // Restore focus when closing
      previousFocusRef.current?.focus();
    };
  }, [authModalOpen, setAuthModalOpen]);

  const handleSave = () => {
    saveAuth(values);
    setAuthModalOpen(false);
  };

  const handleBackdrop = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).classList.contains('auth-backdrop')) {
      setAuthModalOpen(false);
    }
  };

  const set = (k: string, v: string) => setValues((p) => ({ ...p, [k]: v }));

  return (
    <AnimatePresence>
      {authModalOpen && (
        <motion.div
          className="auth-backdrop"
          onClick={handleBackdrop}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <motion.div
            ref={modalRef}
            className="auth-modal"
            role="dialog"
            aria-modal="true"
            aria-label="认证信息"
            initial={{ opacity: 0, scale: 0.95, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ type: 'spring', duration: 0.35, bounce: 0.2 }}
          >
            <h3>认证设置</h3>
            {AUTH_KEYS.map((k) => (
              <label key={k} className="auth-field">
                <span>{k}</span>
                <input
                  type="password"
                  value={values[k] || ''}
                  onChange={(e) => set(k, e.target.value)}
                  placeholder={`请输入 ${k}`}
                />
              </label>
            ))}
            <div className="auth-actions">
              <button className="btn btn-primary" onClick={handleSave}>保存</button>
              <button className="btn" onClick={() => setAuthModalOpen(false)}>取消</button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
