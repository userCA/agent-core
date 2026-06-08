import React from 'react';
import { useSessionStore } from '../../stores/session-store';
import { useThemeStore } from '../../stores/theme-store';
import { useUIStore } from '../../stores/ui-store';
import { useToastStore } from '../../stores/toast-store';
import Icon from '../../components/shared/Icon';
import './SettingsPage.css';

export default function SettingsPage() {
  const { theme, toggleTheme } = useThemeStore();
  const setAuthModalOpen = useUIStore((s) => s.setAuthModalOpen);
  const personas = useSessionStore((s) => s.personas);
  const personaId = useSessionStore((s) => s.personaId);
  const setPersonaId = useSessionStore((s) => s.setPersonaId);
  const clearAuth = useSessionStore((s) => s.clearAuth);
  const addToast = useToastStore((s) => s.addToast);

  const handleLogout = () => {
    clearAuth();
    addToast('已退出登录', 'info');
  };

  return (
    <div className="h5-settings">
      <h2 className="h5-settings-title">设置</h2>

      <section className="h5-settings-section">
        <button className="h5-settings-row" onClick={toggleTheme}>
          <span>主题</span>
          <span className="h5-settings-value">
            {theme === 'light' ? '亮色' : '暗色'}
            <Icon name={theme === 'light' ? 'sun' : 'moon'} size={16} />
          </span>
        </button>

        <button className="h5-settings-row" onClick={() => setAuthModalOpen(true)}>
          <span>认证设置</span>
          <Icon name="chevron-right" size={14} />
        </button>
      </section>

      <section className="h5-settings-section">
        <h3 className="h5-settings-section-title">专家</h3>
        {personas.map((p) => (
          <button
            key={p.id}
            className={`h5-settings-row ${personaId === p.id ? 'h5-settings-row--active' : ''}`}
            onClick={() => {
              setPersonaId(p.id);
              addToast(`已切换到「${p.name}」`, 'success');
            }}
          >
            <span>{p.name}</span>
            {personaId === p.id && <span className="h5-settings-check"><Icon name="check" size={14} /></span>}
          </button>
        ))}
      </section>

      <section className="h5-settings-section">
        <button className="h5-settings-row h5-settings-row--danger" onClick={handleLogout}>
          退出登录
        </button>
      </section>

      <p className="h5-settings-version">咪兔</p>
    </div>
  );
}
