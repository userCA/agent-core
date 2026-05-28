import React, { useCallback, useRef, useEffect } from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useUIStore } from '../../stores/ui-store';
import './ChatInput.css';

interface Props {
  onSend: (text: string) => void;
}

export default function ChatInput({ onSend }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const pendingQueue = useChatStore((s) => s.pendingQueue);
  const inputValue = useUIStore((s) => s.inputValue);
  const setInputValue = useUIStore((s) => s.setInputValue);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text) return;
    onSend(text);
    // input cleared by useSSE
  }, [inputValue, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // auto-resize textarea
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }, [inputValue]);

  return (
    <div className="chat-input-area">
      {pendingQueue.length > 0 && (
        <div className="pending-hint" style={{ fontSize: 11, color: 'var(--ash)', marginBottom: 4, fontFamily: 'var(--font-mono)' }}>
          pending {pendingQueue.length} message(s)
        </div>
      )}
      <div className="input-row">
        <textarea
          ref={inputRef}
          className="chat-textarea"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isStreaming ? 'queue a message...' : 'type a message'}
          rows={1}
          aria-label="消息输入框，按 Enter 发送，Shift+Enter 换行"
        />
        <button
          className="btn btn-primary send-btn"
          onClick={handleSend}
          disabled={!inputValue.trim() || isStreaming}
          aria-label="发送消息"
        >
          {isStreaming ? '...' : 'send'}
        </button>
      </div>
    </div>
  );
}
