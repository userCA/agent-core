import React, { useState, useEffect } from 'react';
import { useSessionStore } from '../../stores/session-store';
import { AUTH_KEYS, AUTH_STORAGE_KEY } from '../../config';
import LoginCompanion from '../../components/companion/LoginCompanion';
import './LoginPage.css';

function generateId(): string {
  const t = Date.now().toString(36);
  const r = Math.random().toString(36).slice(2, 6);
  return `user-${t}-${r}`;
}

export default function LoginPage() {
  const saveAuth = useSessionStore((s) => s.saveAuth);
  const knownUids = useSessionStore((s) => s.knownUids);
  const [uid, setUid] = useState(() => {
    try {
      const saved = localStorage.getItem(AUTH_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.uid || '';
      }
    } catch {}
    return '';
  });
  const [loading, setLoading] = useState(false);

  const trimmed = uid.trim();
  const isValid = trimmed.length > 0;
  const isNewUser = isValid && !knownUids.includes(trimmed);
  const isReturning = isValid && knownUids.includes(trimmed);

  const handleLogin = async (loginUid?: string) => {
    const finalUid = (loginUid || uid || generateId()).trim();
    if (!finalUid) return;
    setLoading(true);
    try {
      const headers: Record<string, string> = { uid: finalUid };
      await saveAuth(headers);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h5-login">
      <div className="h5-login-inner">
        <div className="h5-login-art">
          <LoginCompanion uid={uid} isNewUser={isNewUser} isReturning={isReturning} hasInput={isValid} loading={loading} />
        </div>

        <h1 className="h5-login-brand">咪兔</h1>
        <p className="h5-login-tagline">你的 AI 伙伴</p>

        <div className="h5-login-form">
          <input
            className="h5-login-input"
            type="text"
            value={uid}
            onChange={(e) => setUid(e.target.value)}
            placeholder="输入用户 ID（留空自动生成）"
            disabled={loading}
          />
          <button
            className="h5-login-btn"
            onClick={() => handleLogin()}
            disabled={loading}
          >
            {loading ? '连接中...' : '开始对话'}
          </button>
        </div>

        {knownUids.length > 0 && (
          <div className="h5-login-recent">
            <p className="h5-login-recent-title">最近使用</p>
            <div className="h5-login-recent-list">
              {knownUids.map((u) => (
                <button
                  key={u}
                  className="h5-login-recent-item"
                  onClick={() => handleLogin(u)}
                  disabled={loading}
                >
                  {u}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
