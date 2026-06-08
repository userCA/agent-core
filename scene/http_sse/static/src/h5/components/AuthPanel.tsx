import React, { useState } from 'react';
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

  if (!authModalOpen) return null;

  const handleSave = () => {
    saveAuth(values);
    setAuthModalOpen(false);
    addToast('已保存', 'success');
  };

  return (
    <div className="h5-auth-backdrop" onClick={() => setAuthModalOpen(false)}>
      <div className="h5-auth-panel" onClick={(e) => e.stopPropagation()}>
        <div className="h5-auth-header">
          <h2 className="h5-auth-title">认证设置</h2>
          <button className="btn" onClick={handleSave}>保存</button>
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
      </div>
    </div>
  );
}
