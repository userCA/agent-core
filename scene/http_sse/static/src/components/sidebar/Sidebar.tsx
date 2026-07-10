import React, { useEffect, useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useSessionStore, type SessionSummary } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import { useChatStore } from '../../stores/chat-store';
import { useToastStore } from '../../stores/toast-store';
import { fetchSessionMessages, deleteSession } from '../../api/client';
import Icon from '../shared/Icon';
import TooltipWrap from '../shared/TooltipWrap';
import Loading from '../shared/Loading';
import EmptyState from '../shared/EmptyState';
import './Sidebar.css';

function formatTime(ts: string): string {
  const d = new Date(ts);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  if (isToday) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) {
    return '昨天';
  }
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export default function Sidebar() {
  const sessions = useSessionStore((s) => s.sessions);
  const sessionsLoading = useSessionStore((s) => s.sessionsLoading);
  const sessionId = useSessionStore((s) => s.sessionId);
  const loadSessions = useSessionStore((s) => s.loadSessions);
  const removeSession = useSessionStore((s) => s.removeSession);
  const createSession = useSessionStore((s) => s.createSession);
  const switchSession = useSessionStore((s) => s.switchSession);
  const personas = useSessionStore((s) => s.personas);
  const personaId = useSessionStore((s) => s.personaId);
  const loadPersonas = useSessionStore((s) => s.loadPersonas);
  const setPersonaId = useSessionStore((s) => s.setPersonaId);
  const setAuthModalOpen = useUIStore((s) => s.setAuthModalOpen);
  const setActivePage = useUIStore((s) => s.setActivePage);
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const resetChat = useChatStore((s) => s.reset);
  const setWelcomeVisible = useUIStore((s) => s.setWelcomeVisible);
  const setInputValue = useUIStore((s) => s.setInputValue);

  useEffect(() => {
    loadSessions();
    loadPersonas();
  }, [loadSessions, loadPersonas]);

  const handleNewSession = () => {
    createSession();
    resetChat();
    setInputValue('');
    setWelcomeVisible(true);
  };

  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const q = searchQuery.toLowerCase();
    return sessions.filter((s) =>
      (s.title || '未命名会话').toLowerCase().includes(q)
    );
  }, [sessions, searchQuery]);

  const handleSwitch = async (id: string) => {
    if (id === sessionId) return;
    setLoadingId(id);
    try {
      // Clear streaming state before loading history to prevent
      // stale currentText/streamBlocks from interfering with display.
      const cs = useChatStore.getState();
      cs.reset();
      switchSession(id);
      setWelcomeVisible(false);
      const messages = await fetchSessionMessages(id);
      cs.loadMessages(messages);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '加载会话失败';
      useToastStore.getState().addToast(msg, 'error');
    } finally {
      setLoadingId(null);
    }
  };

  const handleDelete = async (_e: React.MouseEvent, id: string) => {
    try {
      await deleteSession(id);
      removeSession(id);
      if (id === sessionId) {
        resetChat();
        setWelcomeVisible(true);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '删除会话失败';
      useToastStore.getState().addToast(msg, 'error');
    }
  };

  const currentPersona = personas.find((p) => p.id === personaId);

  return (
    <motion.aside
      className={`sidebar${collapsed ? ' sidebar-collapsed' : ''}`}
    >
      <AnimatePresence>
        {!collapsed && (
          <motion.div
            key="sidebar-content"
            className="sidebar-expanded-inner"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
          >
            <div className="sidebar-header">
            <button className="sidebar-new-btn" onClick={handleNewSession}>
              <Icon name="plus" size={14} /> 新建任务
            </button>
            <TooltipWrap label="收起">
              <button
                className="sidebar-toggle-btn"
                onClick={toggleSidebar}
                aria-label="收起侧边栏"
              >
                <Icon name="panel-left" size={16} />
              </button>
            </TooltipWrap>
          </div>

          <div className="sidebar-menu">
            <motion.button
              className="sidebar-menu-item"
              onClick={() => setActivePage('companion')}
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.97 }}
            >
              <span className="sidebar-menu-icon"><Icon name="cat" size={14} /></span>
              <span className="sidebar-menu-label">宠物资料</span>
              <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
            </motion.button>

            <motion.button
              className="sidebar-menu-item"
              onClick={() => setActivePage('experts')}
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.97 }}
            >
              <span className="sidebar-menu-icon"><Icon name="briefcase" size={14} /></span>
              <span className="sidebar-menu-label">专家</span>
              <span className="sidebar-menu-value">{currentPersona?.name ?? '通用助手'}</span>
              <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
            </motion.button>

            <motion.button
              className="sidebar-menu-item"
              onClick={() => setActivePage('skills')}
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.97 }}
            >
              <span className="sidebar-menu-icon"><Icon name="code" size={14} /></span>
              <span className="sidebar-menu-label">技能</span>
              <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
            </motion.button>

            <motion.button
              className="sidebar-menu-item"
              onClick={() => setActivePage('connectors')}
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.97 }}
            >
              <span className="sidebar-menu-icon"><Icon name="tool" size={14} /></span>
              <span className="sidebar-menu-label">连接器</span>
              <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
            </motion.button>

            <motion.button
              className="sidebar-menu-item"
              onClick={() => setActivePage('knowledge')}
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.97 }}
            >
              <span className="sidebar-menu-icon"><Icon name="book" size={14} /></span>
              <span className="sidebar-menu-label">知识库</span>
              <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
            </motion.button>

            <motion.button
              className="sidebar-menu-item"
              onClick={() => setActivePage('channels')}
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.97 }}
            >
              <span className="sidebar-menu-icon"><Icon name="send" size={14} /></span>
              <span className="sidebar-menu-label">渠道管理</span>
              <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
            </motion.button>

            <motion.button
              className="sidebar-menu-item"
              onClick={() => setAuthModalOpen(true)}
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.97 }}
            >
              <span className="sidebar-menu-icon"><Icon name="key" size={14} /></span>
              <span className="sidebar-menu-label">认证设置</span>
              <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
            </motion.button>

            <motion.button
              className="sidebar-menu-item sidebar-menu-item--danger"
              onClick={() => useSessionStore.getState().clearAuth()}
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.97 }}
            >
              <span className="sidebar-menu-icon"><Icon name="cancel" size={14} /></span>
              <span className="sidebar-menu-label">退出登录</span>
              <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
            </motion.button>
          </div>

          <div className="sidebar-divider" />

          <div className="sidebar-search">
            <Icon name="search" size={14} />
            <input
              type="text"
              className="sidebar-search-input"
              placeholder="搜索会话..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="搜索会话"
            />
            {searchQuery && (
              <button
                className="sidebar-search-clear"
                onClick={() => setSearchQuery('')}
                aria-label="清除搜索"
              >
                <Icon name="cancel" size={12} />
              </button>
            )}
          </div>

          <div className="sidebar-content">
            {sessionsLoading && sessions.length === 0 && (
              <Loading size="sm" text="加载中..." />
            )}

            {!sessionsLoading && sessions.length === 0 && (
              <EmptyState icon="message" title="暂无历史会话" />
            )}

            {!sessionsLoading && sessions.length > 0 && filteredSessions.length === 0 && (
              <EmptyState icon="search" title="无匹配会话" />
            )}

            {filteredSessions.length > 0 && (
              <div className="session-list">
                {filteredSessions.map((s: SessionSummary, i: number) => {
                  const active = s.session_id === sessionId;
                  return (
                    <motion.div
                      key={s.session_id}
                      className={`session-item${active ? ' active' : ''}`}
                      initial={{ opacity: 0, x: -12 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: Math.min(i * 0.03, 0.3), duration: 0.25, ease: 'easeOut' }}
                    >
                      <button
                        className="session-item-main"
                        onClick={() => handleSwitch(s.session_id)}
                        aria-current={active ? 'true' : undefined}
                      >
                        <span className="session-icon">
                          {loadingId === s.session_id ? (
                            <Icon name="spinner" size={12} className="session-spinner" />
                          ) : (
                            <Icon name="message" size={12} />
                          )}
                        </span>
                        <span className="session-title">{s.title || '未命名会话'}</span>
                        <span className="session-meta">{formatTime(s.created_at)}</span>
                      </button>
                      <TooltipWrap label="删除会话">
                        <button
                          className="session-delete"
                          onClick={(e) => handleDelete(e, s.session_id)}
                          aria-label="删除会话"
                        >
                          <Icon name="cancel" size={12} />
                        </button>
                      </TooltipWrap>
                    </motion.div>
                  );
                })}
              </div>
            )}
            {sessionId && (
              <a
                className="sidebar-export-link"
                href={`/session/export?session_id=${encodeURIComponent(sessionId)}`}
                download
              >
                导出当前会话
              </a>
            )}
          </div>
          </motion.div>
        )}
      </AnimatePresence>
      {collapsed && (
        <TooltipWrap label="展开">
          <button
            className="sidebar-toggle-btn"
            onClick={toggleSidebar}
            aria-label="展开侧边栏"
          >
            <Icon name="panel-right" size={16} />
          </button>
        </TooltipWrap>
      )}
    </motion.aside>
  );
}
