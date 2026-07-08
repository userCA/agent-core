import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useSessionStore } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import { useCompanionStore } from '../../stores/companion-store';
import { bonesToAvatarConfig, buildAvatarSVG } from '../../components/companion/SvgAvatarComposer';
import './CompactHeader.css';

interface Props {
  onAbort?: () => void;
}

export default function CompactHeader({ onAbort }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const h5ActiveTab = useUIStore((s) => s.h5ActiveTab);
  const setH5ActiveTab = useUIStore((s) => s.setH5ActiveTab);
  const sessionId = useSessionStore((s) => s.sessionId);
  const sessions = useSessionStore((s) => s.sessions);
  const bones = useCompanionStore((s) => s.bones);

  const currentSession = sessions.find((s) => s.session_id === sessionId);
  const isChat = h5ActiveTab === 'chat';
  const title = isChat && currentSession ? currentSession.title : '咪兔';

  // Build pixel avatar from companion bones
  const avatarConfig = bonesToAvatarConfig(bones as Record<string, unknown> | null);
  const petSvg = buildAvatarSVG(avatarConfig);

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
      {/* Left: book-open → history */}
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

      {/* Center: title + online dot */}
      <div className="h5-header-center">
        <h1 className="h5-header-title-center">{title}</h1>
        <span className="h5-header-status">
          <span className="h5-header-dot" />
          在线
        </span>
      </div>

      {/* Right: pet avatar → companion / abort when streaming */}
      {isStreaming ? (
        <button
          className="h5-header-btn h5-header-pet"
          onClick={onAbort}
          aria-label="停止生成"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
          </svg>
        </button>
      ) : (
        <button
          className="h5-header-btn h5-header-pet"
          onClick={() => setH5ActiveTab('companion')}
          aria-label="宠物资料"
          dangerouslySetInnerHTML={{ __html: petSvg || '' }}
        />
      )}
    </header>
  );
}
