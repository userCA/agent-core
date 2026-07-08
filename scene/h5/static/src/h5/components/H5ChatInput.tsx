import React, { useCallback, useRef } from 'react';
import { useUIStore } from '../../stores/ui-store';
import './H5ChatInput.css';

interface Props {
  onSend: (text: string) => void;
}

export default function H5ChatInput({ onSend }: Props) {
  const inputValue = useUIStore((s) => s.inputValue);
  const setInputValue = useUIStore((s) => s.setInputValue);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text) return;
    onSend(text);
    setInputValue('');
    // Reset textarea height after send
    if (textareaRef.current) {
      textareaRef.current.style.height = '44px';
    }
  }, [inputValue, onSend, setInputValue]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /** Auto-resize textarea to fit content, max 120px */
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const el = e.target;
    el.style.height = '44px';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  };

  return (
    <div className="h5-input-dock">
      <div className="h5-input-row">
        {/* Plus button — placeholder for future tool drawer */}
        <button
          type="button"
          className="h5-input-btn h5-input-plus"
          aria-label="工具"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14m-7-7v14" />
          </svg>
        </button>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          className="h5-input-textarea"
          rows={1}
          placeholder="写点什么…"
          value={inputValue}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
        />

        {/* Send button */}
        <button
          type="button"
          className="h5-input-btn h5-input-send"
          onClick={handleSend}
          disabled={!inputValue.trim()}
          aria-label="发送消息"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m5 12l7-7l7 7m-7 7V5" />
          </svg>
        </button>
      </div>
    </div>
  );
}
