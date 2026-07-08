import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import Icon from '../shared/Icon';
import TooltipWrap from '../shared/TooltipWrap';
import './PendingBubbles.css';

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
    </div>
  );
}
