import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useSessionStore } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import Icon from '../shared/Icon';
import './Header.css';

interface Props {
  onAbort: () => void;
}

export default function Header({ onAbort }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const hasAuth = useSessionStore((s) => s.hasAuth);
  const setAuthModalOpen = useUIStore((s) => s.setAuthModalOpen);
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
              <Icon name="running" size={11} /> running
            </>
          ) : (
            <>
              <Icon name="ready" size={11} /> ready
            </>
          )}
        </span>
        {isStreaming && (
          <button className="btn btn-danger" onClick={onAbort}>
            <Icon name="cancel" size={11} /> cancel
          </button>
        )}
        <button className="btn" onClick={() => setAuthModalOpen(true)}>
          <Icon name="key" size={11} /> {hasAuth ? 'authed' : 'auth'}
        </button>
        <button className="btn" onClick={handleNewSession}>
          <Icon name="plus" size={11} /> new
        </button>
      </div>
    </header>
  );
}
