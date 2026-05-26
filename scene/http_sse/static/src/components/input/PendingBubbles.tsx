import React from 'react';
import { useChatStore } from '../../stores/chat-store';

export default function PendingBubbles() {
  const pendingQueue = useChatStore((s) => s.pendingQueue);

  if (pendingQueue.length === 0) return null;

  return (
    <div className="pending-bubbles">
      {pendingQueue.map((text, i) => (
        <div key={i} className="pending-bubble">
          <span className="pending-text">{text.length > 60 ? text.slice(0, 60) + '...' : text}</span>
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
          font-family: var(--font-mono);
          color: var(--mute);
        }
        .pending-remove {
          background: none;
          border: none;
          cursor: pointer;
          font-family: var(--font-mono);
          font-size: 11px;
          color: var(--accent);
          padding: 0;
        }
      `}</style>
    </div>
  );
}
