import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import Icon, { ICON_SIZES } from '../shared/Icon';
import './Header.css';

interface Props {
  onAbort: () => void;
}

export default function Header({ onAbort }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);

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
      </div>
    </header>
  );
}
