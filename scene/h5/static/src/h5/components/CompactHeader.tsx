import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useUIStore } from '../../stores/ui-store';
import './CompactHeader.css';

interface Props {
  onAbort?: () => void;
  onCompanionOpen?: () => void;
  onNewChat?: () => void;
}

export default function CompactHeader({ onAbort, onCompanionOpen, onNewChat }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const hasMessages = useChatStore((s) => s.messages.length > 0);
  const h5ActiveTab = useUIStore((s) => s.h5ActiveTab);
  const setH5ActiveTab = useUIStore((s) => s.setH5ActiveTab);

  const title = '咪兔';

  const isAuxPage = h5ActiveTab === 'settings' || h5ActiveTab === 'history' || h5ActiveTab === 'companion';

  if (isAuxPage) {
    return (
      <header className="h5-header h5-header--aux">
        <button
          className="h5-header-btn"
          onClick={() => setH5ActiveTab('chat')}
          aria-label="返回聊天"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
        <span className="h5-header-title-center">{title}</span>
        <span className="h5-header-spacer" />
      </header>
    );
  }

  return (
    <header className="h5-header">
      {/* Left: history only */}
      <button
        className="h5-header-btn"
        onClick={() => setH5ActiveTab('history')}
        aria-label="聊天记录"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
        </svg>
      </button>

      {/* Center: title (click to open companion) + online dot */}
      <button
        className="h5-header-center h5-header-title-btn"
        onClick={onCompanionOpen ?? (() => setH5ActiveTab('companion'))}
        aria-label="宠物资料"
        title="查看咪兔资料"
      >
        <h1 className="h5-header-title-center">{title}</h1>
        <span className="h5-header-status">
          <span className="h5-header-dot" />
          在线
        </span>
      </button>

      {/* Right: new-chat / abort when streaming */}
      <div className="h5-header-right">
        {isStreaming ? (
          <button
            className="h5-header-btn"
            onClick={onAbort}
            aria-label="停止生成"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
            </svg>
          </button>
        ) : (
          hasMessages && (
            <button
              className="h5-header-btn"
              onClick={onNewChat}
              aria-label="新建会话"
              title="新建会话"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 20h9"/>
                <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>
              </svg>
            </button>
          )
        )}
      </div>
    </header>
  );
}
