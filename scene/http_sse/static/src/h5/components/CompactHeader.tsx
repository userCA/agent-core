import React from 'react';
import { motion } from 'motion/react';
import { useChatStore } from '../../stores/chat-store';
import { useSessionStore } from '../../stores/session-store';
import { useThemeStore } from '../../stores/theme-store';
import { useUIStore } from '../../stores/ui-store';
import Icon from '../../components/shared/Icon';
import './CompactHeader.css';

interface Props {
  onAbort: () => void;
}

const TAB_LABELS: Record<string, string> = {
  chat: '咪兔',
  skills: '技能',
  settings: '设置',
  history: '历史记录',
};

export default function CompactHeader({ onAbort }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const { theme, toggleTheme } = useThemeStore();
  const h5ActiveTab = useUIStore((s) => s.h5ActiveTab);
  const setH5ActiveTab = useUIStore((s) => s.setH5ActiveTab);
  const sessionId = useSessionStore((s) => s.sessionId);
  const sessions = useSessionStore((s) => s.sessions);

  const currentSession = sessions.find((s) => s.session_id === sessionId);
  const title = h5ActiveTab === 'chat' && currentSession
    ? currentSession.title
    : TAB_LABELS[h5ActiveTab] ?? '咪兔';

  const isAuxPage = h5ActiveTab === 'settings' || h5ActiveTab === 'history';

  return (
    <header className="h5-header">
      <div className="h5-header-left">
        {isAuxPage && (
          <motion.button
            className="btn"
            onClick={() => setH5ActiveTab('chat')}
            aria-label="返回聊天"
            whileTap={{ scale: 0.92 }}
            transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          >
            <Icon name="chevron-left" size={18} />
          </motion.button>
        )}
        <span className="h5-header-title">{title}</span>
      </div>

      <div className="h5-header-actions">
        {isStreaming && (
          <button className="btn" onClick={onAbort} aria-label="停止">
            <Icon name="cancel" size={16} />
          </button>
        )}
        {!isAuxPage && (
          <>
            <motion.button
              className="btn"
              onClick={() => setH5ActiveTab('history')}
              aria-label="历史记录"
              whileTap={{ scale: 0.92 }}
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            >
              <Icon name="clock" size={16} />
            </motion.button>
            <motion.button
              className="btn"
              onClick={() => setH5ActiveTab('settings')}
              aria-label="设置"
              whileTap={{ scale: 0.92 }}
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            >
              <Icon name="settings" size={16} />
            </motion.button>
          </>
        )}
        <button className="btn" onClick={toggleTheme} aria-label="切换主题">
          <Icon name={theme === 'light' ? 'moon' : 'sun'} size={16} />
        </button>
      </div>
    </header>
  );
}
