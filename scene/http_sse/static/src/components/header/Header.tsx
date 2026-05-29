import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useSessionStore } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import Icon, { ICON_SIZES } from '../shared/Icon';
import ConnectorPanel from '../settings/ConnectorPanel';
import './Header.css';

interface Props {
  onAbort: () => void;
}

export default function Header({ onAbort }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const hasAuth = useSessionStore((s) => s.hasAuth);
  const setAuthModalOpen = useUIStore((s) => s.setAuthModalOpen);
  const connectorPanelOpen = useUIStore((s) => s.connectorPanelOpen);
  const setConnectorPanelOpen = useUIStore((s) => s.setConnectorPanelOpen);
  const reset = useChatStore((s) => s.reset);
  const clearSession = useSessionStore((s) => s.clearSession);
  const setWelcomeVisible = useUIStore((s) => s.setWelcomeVisible);
  const setInputValue = useUIStore((s) => s.setInputValue);

  const handleNewSession = () => {
    clearSession();
    reset();
    setInputValue('');
    setWelcomeVisible(true);
  };

  return (
    <>
      <header className="app-header">
        <div className="logo">
          <pre className="logo-art">{`  /\\_/\\   咪兔
 ( o.o )  你的AI伙伴
 ( > < )
`}</pre>
        </div>
        <div className="header-actions">
          <span className="status-badge">
            <span className={`status-dot ${isStreaming ? 'pulse' : ''}`} />
            {isStreaming ? (
              <>
                <Icon name="running" size={ICON_SIZES.sm} /> running
              </>
            ) : (
              <>
                <Icon name="ready" size={ICON_SIZES.sm} /> ready
              </>
            )}
          </span>
          {isStreaming && (
            <button className="btn btn-danger" onClick={onAbort} aria-label="取消生成">
              <Icon name="cancel" size={ICON_SIZES.sm} /> cancel
            </button>
          )}
          <button className="btn" onClick={() => setAuthModalOpen(true)} aria-label="设置认证信息">
            <Icon name="key" size={ICON_SIZES.sm} /> {hasAuth ? 'authed' : 'auth'}
          </button>
          <button className="btn" onClick={handleNewSession} aria-label="新建会话">
            <Icon name="plus" size={ICON_SIZES.sm} /> new
          </button>
        </div>
      </header>
      {connectorPanelOpen && <ConnectorPanel onClose={() => setConnectorPanelOpen(false)} />}
    </>
  );
}
