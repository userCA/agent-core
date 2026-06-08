import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useThemeStore } from '../../stores/theme-store';
import Icon from '../../components/shared/Icon';
import './CompactHeader.css';

interface Props {
  onAbort: () => void;
}

export default function CompactHeader({ onAbort }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const { theme, toggleTheme } = useThemeStore();

  return (
    <header className="h5-header">
      <span className="sr-only">咪兔</span>
      <div className="h5-header-actions">
        {isStreaming && (
          <button className="btn" onClick={onAbort} aria-label="停止">
            <Icon name="cancel" size={16} />
          </button>
        )}
        <button className="btn" onClick={toggleTheme} aria-label="切换主题">
          <Icon name={theme === 'light' ? 'moon' : 'sun'} size={16} />
        </button>
      </div>
    </header>
  );
}
