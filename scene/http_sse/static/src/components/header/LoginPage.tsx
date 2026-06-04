import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSessionStore } from '../../stores/session-store';
import { AUTH_KEYS } from '../../config';
import Icon from '../shared/Icon';
import './LoginPage.css';

function generateId(prefix: string): string {
  const entropy = crypto.randomUUID().slice(0, 8);
  const ts = Date.now().toString(36);
  return `${prefix}_${ts}_${entropy}`;
}

export default function LoginPage() {
  const { authHeaders, saveAuth, knownUids, registerUid } = useSessionStore();
  const uidInputRef = useRef<HTMLInputElement>(null);
  const [uid, setUid] = useState(() => authHeaders.uid || '');
  const [loading, setLoading] = useState(false);
  const [touched, setTouched] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advanced, setAdvanced] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const k of AUTH_KEYS) {
      if (k !== 'uid') init[k] = authHeaders[k] || '';
    }
    return init;
  });

  const trimmed = uid.trim();
  const isValid = trimmed.length > 0;
  const isNewUser = isValid && !knownUids.includes(trimmed);
  const isReturning = isValid && knownUids.includes(trimmed);
  const showError = touched && !isValid;

  useEffect(() => {
    uidInputRef.current?.focus();
  }, []);

  const handleLogin = useCallback(async () => {
    setTouched(true);
    if (!trimmed) return;

    setLoading(true);
    await new Promise((r) => setTimeout(r, 300));

    const headers: Record<string, string> = { uid: trimmed };
    for (const k of AUTH_KEYS) {
      if (k === 'uid') continue;
      headers[k] = advanced[k] || generateId(k);
    }
    saveAuth(headers);
    if (!knownUids.includes(trimmed)) {
      registerUid(trimmed);
    }
  }, [trimmed, advanced, saveAuth, knownUids, registerUid]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleLogin();
  };

  const handleBlur = () => setTouched(true);

  const hasHistory = knownUids.length > 0;

  return (
    <div className="login-page">
      <div className="login-ambient" aria-hidden="true" />
      <div className="login-card" role="main" aria-label="登录">
        <div className="login-logo" aria-hidden="true">
          <pre className="login-logo-art">
{`   /\\\\_/\\\\
   ( -.- ) 咪兔
  ( z  z ) 你的AI伙伴`}
          </pre>
          <span className="login-zzz" aria-hidden="true">
            <span className="login-zzz-z" style={{ animationDelay: '0s' }}>z</span>
            <span className="login-zzz-z" style={{ animationDelay: '0.4s' }}>z</span>
            <span className="login-zzz-z" style={{ animationDelay: '0.2s' }}>Z</span>
          </span>
        </div>

        <h2 className="login-title">欢迎回来</h2>
        <p className="login-subtitle">输入你的身份标识以继续对话</p>

        <div className="login-field">
          <label htmlFor="login-uid">用户标识</label>
          <input
            ref={uidInputRef}
            id="login-uid"
            type="text"
            value={uid}
            onChange={(e) => { setUid(e.target.value); if (touched) setTouched(true); }}
            onKeyDown={handleKeyDown}
            onBlur={handleBlur}
            placeholder="输入你的用户名，如 alice"
            autoComplete="username"
            aria-required="true"
            aria-invalid={showError}
            aria-describedby={
              showError ? 'login-uid-error' : isReturning ? 'login-uid-hint' : undefined
            }
          />
          {showError && (
            <span id="login-uid-error" className="login-hint login-hint--error" role="alert">
              请输入用户标识
            </span>
          )}
          {!showError && isNewUser && (
            <span id="login-uid-hint" className="login-hint login-hint--new">
              新用户 &mdash; 将为你创建独立的记忆空间
            </span>
          )}
          {!showError && isReturning && (
            <span id="login-uid-hint" className="login-hint login-hint--returning">
              欢迎回来 &mdash; 将恢复你的历史会话
            </span>
          )}
        </div>

        <button
          type="button"
          className="login-toggle"
          onClick={() => setShowAdvanced(!showAdvanced)}
          aria-expanded={showAdvanced}
        >
          {showAdvanced ? '收起高级选项' : '展开高级选项'}
          <Icon name="chevron-down" size={12} />
        </button>

        {showAdvanced && (
          <div className="login-advanced" role="region" aria-label="高级选项">
            {AUTH_KEYS.filter((k) => k !== 'uid').map((k) => (
              <div className="login-field" key={k}>
                <label htmlFor={`login-adv-${k}`}>{k}</label>
                <input
                  id={`login-adv-${k}`}
                  type="text"
                  value={advanced[k] || ''}
                  onChange={(e) => setAdvanced((p) => ({ ...p, [k]: e.target.value }))}
                  placeholder="留空将自动生成"
                />
              </div>
            ))}
          </div>
        )}

        <button
          type="button"
          className="login-btn btn btn-primary"
          onClick={handleLogin}
          disabled={loading}
          aria-busy={loading}
        >
          {loading ? (
            <>
              <Icon name="spinner" size={16} />
              登录中&hellip;
            </>
          ) : isNewUser ? (
            '创建并开始'
          ) : (
            '开始对话'
          )}
        </button>

        {hasHistory && (
          <div className="login-history">
            <p className="login-history-label">最近使用</p>
            <div className="login-history-list">
              {knownUids.slice(0, 5).map((u) => (
                <button
                  key={u}
                  type="button"
                  className="login-history-item"
                  onClick={() => { setUid(u); setTouched(false); }}
                  aria-label={`使用 ${u} 登录`}
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
