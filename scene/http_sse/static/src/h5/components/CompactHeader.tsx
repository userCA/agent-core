import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
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
  companion: '宠物资料',
};

interface MenuItem {
  icon: string;
  label: string;
  action: () => void;
  danger?: boolean;
}

export default function CompactHeader({ onAbort }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const { theme, toggleTheme } = useThemeStore();
  const h5ActiveTab = useUIStore((s) => s.h5ActiveTab);
  const setH5ActiveTab = useUIStore((s) => s.setH5ActiveTab);
  const sessionId = useSessionStore((s) => s.sessionId);
  const sessions = useSessionStore((s) => s.sessions);
  const createSession = useSessionStore((s) => s.createSession);
  const setWelcomeVisible = useUIStore((s) => s.setWelcomeVisible);
  const setInputValue = useUIStore((s) => s.setInputValue);
  const resetChat = useChatStore((s) => s.reset);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const currentSession = sessions.find((s) => s.session_id === sessionId);
  const title = h5ActiveTab === 'chat' && currentSession
    ? currentSession.title
    : TAB_LABELS[h5ActiveTab] ?? '咪兔';

  const isAuxPage = isH5ActivePage(h5ActiveTab);

  const menuItems: MenuItem[] = [
    {
      icon: 'user',
      label: '宠物资料',
      action: () => {
        setH5ActiveTab('companion');
        setMenuOpen(false);
      },
    },
    {
      icon: 'clock',
      label: '会话历史',
      action: () => {
        setH5ActiveTab('history');
        setMenuOpen(false);
      },
    },
    {
      icon: 'settings',
      label: '设置',
      action: () => {
        setH5ActiveTab('settings');
        setMenuOpen(false);
      },
    },
  ];

  // Close menu on outside click or escape
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleEscape);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [menuOpen]);

  const handleMenuToggle = () => {
    setMenuOpen((prev) => !prev);
  };

  return (
    <>
      <header className="h5-header">
        <div className="h5-header-left">
          {isAuxPage ? (
            <motion.button
              className="btn"
              onClick={() => setH5ActiveTab('chat')}
              aria-label="返回聊天"
              whileTap={{ scale: 0.92 }}
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            >
              <Icon name="chevron-left" size={18} />
            </motion.button>
          ) : (
            <motion.button
              className="btn h5-menu-btn"
              onClick={handleMenuToggle}
              aria-label="打开菜单"
              whileTap={{ scale: 0.92 }}
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            >
              <Icon name="menu" size={18} />
            </motion.button>
          )}
          <span className="h5-header-title">{title}</span>
        </div>

        <div className="h5-header-actions">
          {isStreaming && (
            <motion.button
              className="btn"
              onClick={onAbort}
              aria-label="停止"
              whileTap={{ scale: 0.92 }}
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            >
              <Icon name="cancel" size={16} />
            </motion.button>
          )}
          {h5ActiveTab === 'chat' && sessionId && (
            <motion.button
              className="btn"
              onClick={() => {
                createSession();
                resetChat();
                setInputValue('');
                setWelcomeVisible(true);
              }}
              aria-label="新建会话"
              whileTap={{ scale: 0.92 }}
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            >
              <Icon name="plus" size={16} />
            </motion.button>
          )}
          <motion.button
            className="btn"
            onClick={toggleTheme}
            aria-label="切换主题"
            whileTap={{ scale: 0.92 }}
            transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          >
            <Icon name={theme === 'light' ? 'moon' : 'sun'} size={16} />
          </motion.button>
        </div>
      </header>

      {/* Side Menu Overlay */}
      <AnimatePresence>
        {menuOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              className="h5-menu-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setMenuOpen(false)}
            />
            {/* Menu Panel */}
            <motion.div
              ref={menuRef}
              className="h5-menu-panel"
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', stiffness: 400, damping: 32 }}
            >
              <div className="h5-menu-header">
                <span className="h5-menu-title">菜单</span>
                <motion.button
                  className="btn h5-menu-close"
                  onClick={() => setMenuOpen(false)}
                  whileTap={{ scale: 0.92 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                >
                  <Icon name="close" size={18} />
                </motion.button>
              </div>
              <nav className="h5-menu-list">
                {menuItems.map((item, index) => (
                  <motion.button
                    key={item.label}
                    className="h5-menu-item"
                    onClick={item.action}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{
                      delay: 0.02 + index * 0.03,
                      type: 'spring',
                      stiffness: 400,
                      damping: 32,
                    }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <span className="h5-menu-item-icon">
                      <Icon name={item.icon} size={20} />
                    </span>
                    <span className="h5-menu-item-label">{item.label}</span>
                  </motion.button>
                ))}
              </nav>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

function isH5ActivePage(tab: string): boolean {
  return tab === 'settings' || tab === 'history' || tab === 'companion';
}
