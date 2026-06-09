import React from 'react';
import { motion } from 'motion/react';
import { useSessionStore } from '../../stores/session-store';
import { useThemeStore } from '../../stores/theme-store';
import { useUIStore } from '../../stores/ui-store';
import { useToastStore } from '../../stores/toast-store';
import Icon from '../../components/shared/Icon';

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
    onClick={onClick}
    variants={itemVariants}
    whileTap={{ scale: 0.98 }}
    style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '18px 20px',
      background: 'var(--canvas)',
      border: 'none',
      borderBottom: '1px solid var(--hairline)',
      color: danger ? 'var(--danger)' : 'var(--ink)',
      fontSize: '17px',
      fontFamily: 'var(--font-sans)',
      cursor: 'pointer',
      width: '100%',
      textAlign: 'left',
      WebkitTapHighlightColor: 'transparent',
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
      <div
        style={{
          width: '36px',
          height: '36px',
          borderRadius: '10px',
          background: danger ? 'var(--danger-bg-subtle)' : 'var(--pastel-blue-bg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <Icon
          name={icon}
          size={20}
          style={{ color: danger ? 'var(--danger)' : 'var(--pastel-blue-text)' }}
        />
      </div>
      <span style={{ fontWeight: 500 }}>{label}</span>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
      {value && (
        <span style={{ color: 'var(--mute)', fontSize: '15px' }}>{value}</span>
      )}
      {!danger && (
        <Icon name="chevron-right" size={18} style={{ color: 'var(--ash)' }} />
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
    <div
      style={{
        width: '100%',
        minWidth: '100%',
        minHeight: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--surface-soft)',
        paddingBottom: '80px',
      }}
    >
      {/* Profile Header */}
      <motion.div
        variants={headerVariants}
        initial="hidden"
        animate="show"
        style={{
          width: '100%',
          padding: '32px 20px 24px',
          background: 'var(--canvas)',
          borderBottom: '1px solid var(--hairline)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
        }}
      >
        <div
          style={{
            width: '72px',
            height: '72px',
            borderRadius: '50%',
            background: 'var(--pastel-blue-bg)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name="user" size={36} style={{ color: 'var(--pastel-blue-text)' }} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div
            style={{
              fontSize: '20px',
              fontWeight: 600,
              color: 'var(--ink)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {currentPersona?.name ?? '访客'}
          </div>
          {currentSession && (
            <div
              style={{
                fontSize: '13px',
                color: 'var(--mute)',
                fontFamily: 'var(--font-mono)',
                marginTop: '4px',
              }}
            >
              {currentSession.title}
            </div>
          )}
        </div>
      </motion.div>

      {/* General Section */}
      <div style={{ padding: '20px 16px 8px', width: '100%' }}>
        <span
          style={{
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--mute)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          通用
        </span>
      </div>
      <motion.div
        variants={listVariants}
        initial="hidden"
        animate="show"
        style={{
          width: '100%',
          background: 'var(--canvas)',
          borderTop: '1px solid var(--hairline)',
          borderBottom: '1px solid var(--hairline)',
        }}
      >
        <SettingRow
          icon="palette"
          label="主题"
          value={theme === 'light' ? '亮色' : '暗色'}
          onClick={toggleTheme}
        />
        <SettingRow
          icon="key"
          label="认证设置"
          onClick={() => setAuthModalOpen(true)}
        />
      </motion.div>

      {/* Personas Section */}
      {personas.length > 0 && (
        <>
          <div style={{ padding: '24px 16px 8px', width: '100%' }}>
            <span
              style={{
                fontSize: '13px',
                fontWeight: 600,
                color: 'var(--mute)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              专家
            </span>
          </div>
          <motion.div
            variants={listVariants}
            initial="hidden"
            animate="show"
            style={{
              width: '100%',
              background: 'var(--canvas)',
              borderTop: '1px solid var(--hairline)',
              borderBottom: '1px solid var(--hairline)',
            }}
          >
            {personas.map((p, idx) => (
              <motion.button
                key={p.id}
                onClick={() => {
                  setPersonaId(p.id);
                  addToast(`已切换到「${p.name}」`, 'success');
                }}
                variants={itemVariants}
                whileTap={{ scale: 0.98 }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '18px 20px',
                  background: personaId === p.id ? 'var(--pastel-blue-bg)' : 'var(--canvas)',
                  border: 'none',
                  borderBottom: idx < personas.length - 1 ? '1px solid var(--hairline)' : 'none',
                  color: personaId === p.id ? 'var(--pastel-blue-text)' : 'var(--ink)',
                  fontSize: '17px',
                  fontFamily: 'var(--font-sans)',
                  cursor: 'pointer',
                  width: '100%',
                  textAlign: 'left',
                  WebkitTapHighlightColor: 'transparent',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                  <div
                    style={{
                      width: '36px',
                      height: '36px',
                      borderRadius: '10px',
                      background: personaId === p.id ? 'rgba(255,255,255,0.5)' : 'var(--surface-soft)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <Icon
                      name="briefcase"
                      size={20}
                      style={{ color: personaId === p.id ? 'var(--pastel-blue-text)' : 'var(--mute)' }}
                    />
                  </div>
                  <span style={{ fontWeight: 500 }}>{p.name}</span>
                </div>
                {personaId === p.id && (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: 'spring' as const, stiffness: 500, damping: 25 }}
                  >
                    <Icon name="check" size={20} style={{ color: 'var(--accent)' }} />
                  </motion.div>
                )}
              </motion.button>
            ))}
          </motion.div>
        </>
      )}

      {/* Account Section */}
      <div style={{ padding: '24px 16px 8px', width: '100%' }}>
        <span
          style={{
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--mute)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          账户
        </span>
      </div>
      <motion.div
        variants={listVariants}
        initial="hidden"
        animate="show"
        style={{
          width: '100%',
          background: 'var(--canvas)',
          borderTop: '1px solid var(--hairline)',
          borderBottom: '1px solid var(--hairline)',
        }}
      >
        <SettingRow
          icon="cancel"
          label="退出登录"
          onClick={handleLogout}
          danger
        />
      </motion.div>

      {/* Footer */}
      <div
        style={{
          width: '100%',
          textAlign: 'center',
          padding: '40px 20px',
          color: 'var(--ash)',
          fontSize: '12px',
          fontFamily: 'var(--font-mono)',
          marginTop: 'auto',
        }}
      >
        咪兔
      </div>
    </div>
  );
}
