import React from 'react';
import { motion } from 'motion/react';
import { useSessionStore } from '../../stores/session-store';
import { useThemeStore } from '../../stores/theme-store';
import { useUIStore } from '../../stores/ui-store';
import { useToastStore } from '../../stores/toast-store';
import Icon from '../../components/shared/Icon';
import './SettingsPage.css';

const listVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.05 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
};

const headerVariants = {
  hidden: { opacity: 0, y: -20 },
  show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 300, damping: 30 } },
};

interface RowProps {
  icon: string;
  label: string;
  value?: string;
  onClick: () => void;
  danger?: boolean;
}

const SettingRow = ({ icon, label, value, onClick, danger }: RowProps) => (
  <motion.button
    className={`h5-settings-row ${danger ? 'h5-settings-row--danger' : ''}`}
    onClick={onClick}
    variants={itemVariants}
    whileTap={{ scale: 0.98 }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      <div
        className="h5-settings-row__icon"
        style={{
          background: danger ? 'var(--danger-bg-subtle)' : 'var(--surface-card)',
        }}
      >
        <Icon
          name={icon}
          size={16}
          style={{ color: 'var(--mute)' }}
        />
      </div>
      <span className="h5-settings-row__label">{label}</span>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
      {value && (
        <span className="h5-settings-row__value">{value}</span>
      )}
      {!danger && (
        <Icon name="chevron-right" size={16} style={{ color: 'var(--ash)' }} />
      )}
    </div>
  </motion.button>
);

export default function SettingsPage() {
  const { theme, toggleTheme } = useThemeStore();
  const setAuthModalOpen = useUIStore((s) => s.setAuthModalOpen);
  const personas = useSessionStore((s) => s.personas);
  const personaId = useSessionStore((s) => s.personaId);
  const setPersonaId = useSessionStore((s) => s.setPersonaId);
  const clearAuth = useSessionStore((s) => s.clearAuth);
  const addToast = useToastStore((s) => s.addToast);
  const sessionId = useSessionStore((s) => s.sessionId);
  const sessions = useSessionStore((s) => s.sessions);

  const currentSession = sessions.find((s) => s.session_id === sessionId);
  const currentPersona = personas.find((p) => p.id === personaId);

  const handleLogout = () => {
    clearAuth();
    addToast('已退出登录', 'info');
  };

  return (
    <div className="h5-settings-page">
      {/* Profile Card */}
      <motion.div
        className="h5-settings-card h5-settings-card--profile"
        variants={headerVariants}
        initial="hidden"
        animate="show"
      >
        <div className="h5-settings-avatar">
          <svg width="48" height="48" viewBox="0 0 100 100" fill="none">
            {/* Cat face circle */}
            <circle cx="50" cy="52" r="34" fill="var(--pastel-blue-text)" opacity="0.15" />
            {/* Left ear */}
            <path d="M22 38 L28 20 L42 32 Z" fill="var(--pastel-blue-text)" opacity="0.25" />
            <path d="M24 36 L29 23 L40 33 Z" fill="var(--pastel-blue-text)" opacity="0.15" />
            {/* Right ear */}
            <path d="M78 38 L72 20 L58 32 Z" fill="var(--pastel-blue-text)" opacity="0.25" />
            <path d="M76 36 L71 23 L60 33 Z" fill="var(--pastel-blue-text)" opacity="0.15" />
            {/* Head */}
            <ellipse cx="50" cy="55" rx="30" ry="26" fill="var(--pastel-blue-text)" opacity="0.2" />
            {/* Left eye */}
            <ellipse cx="40" cy="52" rx="4" ry="5" fill="var(--pastel-blue-text)" />
            <circle cx="41" cy="50.5" r="1.5" fill="white" opacity="0.8" />
            {/* Right eye */}
            <ellipse cx="60" cy="52" rx="4" ry="5" fill="var(--pastel-blue-text)" />
            <circle cx="61" cy="50.5" r="1.5" fill="white" opacity="0.8" />
            {/* Nose */}
            <ellipse cx="50" cy="60" rx="3" ry="2" fill="var(--pastel-blue-text)" opacity="0.6" />
            {/* Mouth */}
            <path d="M46 64 Q50 67 54 64" stroke="var(--pastel-blue-text)" strokeWidth="1.8" strokeLinecap="round" fill="none" />
            {/* Whiskers left */}
            <line x1="18" y1="55" x2="32" y2="57" stroke="var(--pastel-blue-text)" strokeWidth="1.2" strokeLinecap="round" opacity="0.4" />
            <line x1="18" y1="60" x2="32" y2="59" stroke="var(--pastel-blue-text)" strokeWidth="1.2" strokeLinecap="round" opacity="0.4" />
            {/* Whiskers right */}
            <line x1="82" y1="55" x2="68" y2="57" stroke="var(--pastel-blue-text)" strokeWidth="1.2" strokeLinecap="round" opacity="0.4" />
            <line x1="82" y1="60" x2="68" y2="59" stroke="var(--pastel-blue-text)" strokeWidth="1.2" strokeLinecap="round" opacity="0.4" />
            {/* Paws at bottom */}
            <ellipse cx="38" cy="80" rx="5" ry="3" fill="var(--pastel-blue-text)" opacity="0.15" />
            <ellipse cx="62" cy="80" rx="5" ry="3" fill="var(--pastel-blue-text)" opacity="0.15" />
          </svg>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div className="h5-settings-username">
            {currentPersona?.name ?? '访客'}
          </div>
          {currentSession && (
            <div className="h5-settings-session-title">
              {currentSession.title}
            </div>
          )}
        </div>
      </motion.div>

      {/* General Card */}
      <motion.div
        className="h5-settings-card"
        variants={listVariants}
        initial="hidden"
        animate="show"
      >
        <div className="h5-settings-card__title">通用</div>
        <div className="h5-settings-card__body">
          <SettingRow
            icon="key"
            label="认证设置"
            onClick={() => setAuthModalOpen(true)}
          />
        </div>
      </motion.div>

      {/* Personas Card */}
      {personas.length > 0 && (
        <motion.div
          className="h5-settings-card"
          variants={listVariants}
          initial="hidden"
          animate="show"
        >
          <div className="h5-settings-card__title">专家</div>
          <div className="h5-settings-card__body">
            {personas.map((p, idx) => (
              <motion.button
                key={p.id}
                className={`h5-settings-row ${personaId === p.id ? 'h5-settings-row--active' : ''}`}
                onClick={() => {
                  setPersonaId(p.id);
                  addToast(`已切换到「${p.name}」`, 'success');
                }}
                variants={itemVariants}
                whileTap={{ scale: 0.98 }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div
                    className="h5-settings-row__icon"
                    style={{
                      background: personaId === p.id ? 'rgba(255,255,255,0.5)' : 'var(--surface-card)',
                    }}
                  >
                    <Icon
                      name="briefcase"
                      size={16}
                      style={{ color: personaId === p.id ? 'var(--pastel-blue-text)' : 'var(--mute)' }}
                    />
                  </div>
                  <span className="h5-settings-row__label">{p.name}</span>
                </div>
                {personaId === p.id && (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: 'spring' as const, stiffness: 500, damping: 25 }}
                  >
                    <Icon name="check" size={16} className="h5-settings-check" />
                  </motion.div>
                )}
              </motion.button>
            ))}
          </div>
        </motion.div>
      )}

      {/* Account Card */}
      <motion.div
        className="h5-settings-card"
        variants={listVariants}
        initial="hidden"
        animate="show"
      >
        <div className="h5-settings-card__title">账户</div>
        <div className="h5-settings-card__body">
          <SettingRow
            icon="cancel"
            label="退出登录"
            onClick={handleLogout}
            danger
          />
        </div>
      </motion.div>

      {/* Footer */}
      <div className="h5-settings-footer">
        咪兔
      </div>
    </div>
  );
}
