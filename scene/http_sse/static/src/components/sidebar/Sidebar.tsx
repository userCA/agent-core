import React, { useEffect, useState, useMemo } from 'react';
import { useSessionStore, type SessionSummary } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import { useChatStore } from '../../stores/chat-store';
import { fetchSessionMessages, deleteSession } from '../../api/client';
import Icon from '../shared/Icon';
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
      switchSession(id);
      resetChat();
      setWelcomeVisible(false);
      const messages = await fetchSessionMessages(id);
      useChatStore.getState().loadMessages(messages);
    } catch {
      // ignore load errors
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
    } catch {
      // ignore delete errors
    }
  };

  const currentPersona = personas.find((p) => p.id === personaId);

  if (collapsed) {
    return (
      <aside className="sidebar sidebar-collapsed">
        <button
          className="sidebar-toggle-btn"
          onClick={toggleSidebar}
          aria-label="展开侧边栏"
          title="展开"
        >
          <Icon name="panel-right" size={16} />
        </button>
      </aside>
    );
  }

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-header">
          <button className="sidebar-new-btn" onClick={handleNewSession}>
            <Icon name="plus" size={14} /> 新建任务
          </button>
          <button
            className="sidebar-toggle-btn"
            onClick={toggleSidebar}
            aria-label="收起侧边栏"
            title="收起"
          >
            <Icon name="panel-left" size={16} />
          </button>
        </div>

        <div className="sidebar-menu">
          <button
            className="sidebar-menu-item"
            onClick={() => setActivePage('experts')}
          >
            <span className="sidebar-menu-icon"><Icon name="briefcase" size={14} /></span>
            <span className="sidebar-menu-label">专家</span>
            <span className="sidebar-menu-value">{currentPersona?.name ?? '通用助手'}</span>
            <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
          </button>

          <button
            className="sidebar-menu-item"
            onClick={() => setActivePage('skills')}
          >
            <span className="sidebar-menu-icon"><Icon name="code" size={14} /></span>
            <span className="sidebar-menu-label">技能</span>
            <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
          </button>

          <button
            className="sidebar-menu-item"
            onClick={() => setActivePage('connectors')}
          >
            <span className="sidebar-menu-icon"><Icon name="tool" size={14} /></span>
            <span className="sidebar-menu-label">连接器</span>
            <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
          </button>

          <button
            className="sidebar-menu-item"
            onClick={() => setActivePage('knowledge')}
          >
            <span className="sidebar-menu-icon"><Icon name="book" size={14} /></span>
            <span className="sidebar-menu-label">知识库</span>
            <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
          </button>

          <button
            className="sidebar-menu-item"
            onClick={() => setAuthModalOpen(true)}
          >
            <span className="sidebar-menu-icon"><Icon name="key" size={14} /></span>
            <span className="sidebar-menu-label">认证设置</span>
            <span className="sidebar-menu-arrow"><Icon name="chevron-right" size={12} /></span>
          </button>
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
            <div className="sidebar-empty">加载中...</div>
          )}

          {!sessionsLoading && sessions.length === 0 && (
            <div className="sidebar-empty">暂无历史会话</div>
          )}

          {!sessionsLoading && sessions.length > 0 && filteredSessions.length === 0 && (
            <div className="sidebar-empty">无匹配会话</div>
          )}

          {filteredSessions.length > 0 && (
            <div className="session-list">
              {filteredSessions.map((s: SessionSummary) => {
                const active = s.session_id === sessionId;
                return (
                  <div
                    key={s.session_id}
                    className={`session-item${active ? ' active' : ''}`}
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
                    <button
                      className="session-delete"
                      onClick={(e) => handleDelete(e, s.session_id)}
                      title="删除会话"
                      aria-label="删除会话"
                    >
                      <Icon name="cancel" size={12} />
                    </button>
                  </div>
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
      </aside>
    </>
  );
}
