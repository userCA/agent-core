import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useSessionStore } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import { useToastStore } from '../../stores/toast-store';
import { AUTH_KEYS } from '../../config';
import './AuthPanel.css';

export default function AuthPanel() {
  const { authHeaders, saveAuth } = useSessionStore();
  const authModalOpen = useUIStore((s) => s.authModalOpen);
  const setAuthModalOpen = useUIStore((s) => s.setAuthModalOpen);
  const addToast = useToastStore((s) => s.addToast);

  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const k of AUTH_KEYS) init[k] = authHeaders[k] || '';
    return init;
  });

  const handleSave = () => {
    saveAuth(values);
    setAuthModalOpen(false);
    addToast('已保存', 'success');
  };

  return (
    <AnimatePresence>
      {authModalOpen && (
        <motion.div
          className="h5-auth-backdrop"
          onClick={() => setAuthModalOpen(false)}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <motion.div
            className="h5-auth-panel"
            onClick={(e) => e.stopPropagation()}
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', stiffness: 400, damping: 35 }}
          >
            <div className="h5-auth-header">
              <h2 className="h5-auth-title">认证设置</h2>
              <motion.button
                className="btn"
                onClick={handleSave}
                whileTap={{ scale: 0.96 }}
                transition={{ type: 'spring', stiffness: 500, damping: 30 }}
              >
                保存
              </motion.button>
            </div>
            <div className="h5-auth-body">
              {AUTH_KEYS.map((key) => (
                <label key={key} className="h5-auth-field">
                  <span className="h5-auth-label">{key}</span>
                  <input
                    type={key === 'pacmtoken' ? 'password' : 'text'}
                    value={values[key] || ''}
                    onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
                    placeholder={key}
                  />
                </label>
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
