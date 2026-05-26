import React, { useState, useEffect } from 'react';
import { useSessionStore } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import { AUTH_KEYS } from '../../config';
import './AuthModal.css';

export default function AuthModal() {
  const { authHeaders, saveAuth } = useSessionStore();
  const setAuthModalOpen = useUIStore((s) => s.setAuthModalOpen);
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const k of AUTH_KEYS) init[k] = authHeaders[k] || '';
    return init;
  });

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
    <div className="auth-backdrop" onClick={handleBackdrop}>
      <div className="auth-modal">
        <h3>[key] auth headers</h3>
        {AUTH_KEYS.map((k) => (
          <label key={k} className="auth-field">
            <span>{k}</span>
            <input
              type="text"
              value={values[k] || ''}
              onChange={(e) => set(k, e.target.value)}
              placeholder={`Enter ${k}`}
            />
          </label>
        ))}
        <div className="auth-actions">
          <button className="btn btn-primary" onClick={handleSave}>save</button>
          <button className="btn" onClick={() => setAuthModalOpen(false)}>cancel</button>
        </div>
      </div>
    </div>
  );
}
