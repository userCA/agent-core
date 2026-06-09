import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
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
      <motion.div
        className="h5-login-inner"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 28, delay: 0.1 }}
      >
        <motion.div
          className="h5-login-art"
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', stiffness: 300, damping: 20, delay: 0.2 }}
        >
          <LoginCompanion uid={uid} isNewUser={isNewUser} isReturning={isReturning} hasInput={isValid} loading={loading} />
        </motion.div>

        <motion.h1
          className="h5-login-brand"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 28, delay: 0.3 }}
        >
          咪兔
        </motion.h1>
        <motion.p
          className="h5-login-tagline"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 28, delay: 0.35 }}
        >
          你的 AI 伙伴
        </motion.p>

        <motion.div
          className="h5-login-form"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 28, delay: 0.4 }}
        >
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
        </motion.div>

        {knownUids.length > 0 && (
          <motion.div
            className="h5-login-recent"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            <p className="h5-login-recent-title">最近使用</p>
            <div className="h5-login-recent-list">
              {knownUids.map((u, i) => (
                <motion.button
                  key={u}
                  className="h5-login-recent-item"
                  onClick={() => handleLogin(u)}
                  disabled={loading}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.55 + i * 0.05 }}
                  whileTap={{ scale: 0.96 }}
                >
                  {u}
                </motion.button>
              ))}
            </div>
          </motion.div>
        )}
      </motion.div>
    </div>
  );
}
