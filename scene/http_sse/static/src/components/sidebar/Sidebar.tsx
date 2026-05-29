import React, { useEffect, useState } from 'react';
import { useSessionStore, type SessionSummary } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import { useChatStore } from '../../stores/chat-store';
import { fetchSessionMessages } from '../../api/client';
import Icon from '../shared/Icon';
import ConnectorPanel from '../settings/ConnectorPanel';
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
  const createSession = useSessionStore((s) => s.createSession);
  const switchSession = useSessionStore((s) => s.switchSession);
  const personas = useSessionStore((s) => s.personas);
  const personaId = useSessionStore((s) => s.personaId);
  const loadPersonas = useSessionStore((s) => s.loadPersonas);
  const setPersonaId = useSessionStore((s) => s.setPersonaId);
  const setAuthModalOpen = useUIStore((s) => s.setAuthModalOpen);
  const connectorPanelOpen = useUIStore((s) => s.connectorPanelOpen);
  const setConnectorPanelOpen = useUIStore((s) => s.setConnectorPanelOpen);
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
  const [showPersonaPicker, setShowPersonaPicker] = useState(false);

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
            onClick={() => setShowPersonaPicker((v) => !v)}
            aria-expanded={showPersonaPicker}
          >
            <span className="sidebar-menu-icon"><Icon name="briefcase" size={14} /></span>
            <span className="sidebar-menu-label">角色</span>
            <span className="sidebar-menu-value">{currentPersona?.name ?? '通用助手'}</span>
            <span className="sidebar-menu-arrow">
              {showPersonaPicker ? <Icon name="chevron-up" size={12} /> : <Icon name="chevron-down" size={12} />}
            </span>
          </button>
          {showPersonaPicker && (
            <div className="sidebar-submenu">
              {personas.map((p) => (
                <button
                  key={p.id}
                  className={`sidebar-submenu-item${p.id === personaId ? ' active' : ''}`}
                  onClick={() => { setPersonaId(p.id); setShowPersonaPicker(false); }}
                  title={p.description}
                >
                  {p.name}
                </button>
              ))}
            </div>
          )}

          <button
            className="sidebar-menu-item"
            onClick={() => setConnectorPanelOpen(true)}
          >
            <span className="sidebar-menu-icon"><Icon name="tool" size={14} /></span>
            <span className="sidebar-menu-label">连接器</span>
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

        <div className="sidebar-content">
          {sessionsLoading && sessions.length === 0 && (
            <div className="sidebar-empty">加载中...</div>
          )}

          {sessions.length === 0 && !sessionsLoading && (
            <div className="sidebar-empty">暂无历史会话</div>
          )}

          {sessions.length > 0 && (
            <div className="session-list">
              {sessions.map((s: SessionSummary) => {
                const active = s.session_id === sessionId;
                return (
                  <button
                    key={s.session_id}
                    className={`session-item${active ? ' active' : ''}`}
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
                );
              })}
            </div>
          )}
        </div>
      </aside>
      {connectorPanelOpen && <ConnectorPanel onClose={() => setConnectorPanelOpen(false)} />}
    </>
  );
}
