import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import Icon from '../shared/Icon';
import TooltipWrap from '../shared/TooltipWrap';

export default function PendingBubbles() {
  const pendingQueue = useChatStore((s) => s.pendingQueue);
  const removePending = useChatStore((s) => s.removePending);

  if (pendingQueue.length === 0) return null;

  return (
    <div className="pending-bubbles">
      {pendingQueue.map((text, i) => (
        <div key={i} className="pending-bubble">
          <span className="pending-text">{text.length > 60 ? text.slice(0, 60) + '...' : text}</span>
          <TooltipWrap label="移除">
            <button
              className="pending-remove"
              onClick={() => removePending(i)}
              aria-label="移除待发送消息"
            >
              <Icon name="cancel" size={12} />
            </button>
          </TooltipWrap>
        </div>
      ))}
      <style>{`
        .pending-bubbles {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
          padding: 0 24px 8px;
        }
        .pending-bubble {
          display: flex;
          align-items: center;
          gap: 6px;
          background: var(--surface-soft);
          border: 1px solid var(--hairline);
          border-radius: var(--radius-sm);
          padding: 4px 8px;
          font-size: 11px;
          font-family: var(--font-sans);
          color: var(--mute);
          animation: popIn 0.2s cubic-bezier(0.22, 1, 0.36, 1);
        }
        @keyframes popIn {
          from { opacity: 0; transform: scale(0.9); }
          to   { opacity: 1; transform: scale(1); }
        }
        .pending-remove {
          display: flex;
          align-items: center;
          justify-content: center;
          background: none;
          border: none;
          cursor: pointer;
          padding: 2px;
          border-radius: var(--radius-sm);
          color: var(--ash);
          transition: background 0.15s ease, color 0.15s ease;
        }
        .pending-remove:hover {
          background: var(--surface-card);
          color: var(--danger);
        }
        .pending-remove:focus-visible {
          outline: 2px solid var(--accent);
          outline-offset: 2px;
        }
      `}</style>
    </div>
  );
}
