import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useThemeStore } from '../../stores/theme-store';
import Icon, { ICON_SIZES } from '../shared/Icon';
import './Header.css';

interface Props {
  onAbort: () => void;
}

export default function Header({ onAbort }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const { theme, toggleTheme } = useThemeStore();

  return (
    <header className="app-header">
      <div className="logo">
        <pre className="logo-art">{`  /\\_/\\   咪兔
 ( o.o )  你的AI伙伴
 ( > < )
`}</pre>
      </div>
      <div className="header-actions">
        <button
          className="btn"
          onClick={toggleTheme}
          aria-label={theme === 'light' ? '切换到暗色模式' : '切换到亮色模式'}
          title={theme === 'light' ? '暗色模式' : '亮色模式'}
        >
          <Icon name={theme === 'light' ? 'moon' : 'sun'} size={ICON_SIZES.md} />
        </button>
        <span className="status-badge">
          <span className={`status-dot ${isStreaming ? 'pulse' : ''}`} />
          {isStreaming ? (
            <>
              <Icon name="running" size={ICON_SIZES.sm} /> 运行中
            </>
          ) : (
            <>
              <Icon name="ready" size={ICON_SIZES.sm} /> 就绪
            </>
          )}
        </span>
        {isStreaming && (
          <button className="btn btn-danger" onClick={onAbort} aria-label="取消生成">
            <Icon name="cancel" size={ICON_SIZES.sm} /> 取消
          </button>
        )}
      </div>
    </header>
  );
}
