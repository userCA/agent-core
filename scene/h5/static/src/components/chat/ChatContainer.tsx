import React from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useChatStore, type ChatMessage } from '../../stores/chat-store';
import { useUIStore } from '../../stores/ui-store';
import { useAutoScroll } from '../../hooks/useAutoScroll';
import Icon from '../shared/Icon';
import MessageBubble from './MessageBubble';
import StreamingMessage from './StreamingMessage';
import WelcomeScreen from './WelcomeScreen';
import './ChatContainer.css';

interface Props {
  onExampleClick?: (text: string) => void;
}

/** Format a date label: "今天", "昨天", or "M月D日" */
function dateLabel(ts: number): string {
  const d = new Date(ts);
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86400000;

  if (ts >= todayStart) return '今天';
  if (ts >= yesterdayStart) return '昨天';

  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

/** Check if two timestamps are on different calendar days */
function isDifferentDay(ts1: number, ts2: number): boolean {
  const d1 = new Date(ts1);
  const d2 = new Date(ts2);
  return d1.getFullYear() !== d2.getFullYear()
    || d1.getMonth() !== d2.getMonth()
    || d1.getDate() !== d2.getDate();
}

function DateDivider({ label }: { label: string }) {
  return (
    <div className="date-divider">
      <div className="date-divider-line" />
      <span className="date-divider-label">{label}</span>
      <div className="date-divider-line" />
    </div>
  );
}

export default function ChatContainer({ onExampleClick }: Props) {
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const currentText = useChatStore((s) => s.currentText);
  const streamBlocks = useChatStore((s) => s.streamBlocks);
  const welcomeVisible = useUIStore((s) => s.welcomeVisible) && messages.length === 0;

  // While StreamingMessage is fading out (after stream ends), hide the last
  // assistant MessageBubble so the same content isn't rendered twice.
  const showStreaming = isStreaming || currentText.length > 0;
  const lastMsg = messages[messages.length - 1];
  const hideLastBubble = showStreaming && lastMsg?.role === 'assistant';
  const displayMessages = hideLastBubble ? messages.slice(0, -1) : messages;

  const { containerRef, onScroll, showButton, forceScrollToBottom } = useAutoScroll([
    messages, currentText, streamBlocks,
  ]);

  // Build message list with date dividers
  const elements: React.ReactNode[] = [];
  let prevTs = 0;

  displayMessages.forEach((msg: ChatMessage) => {
    if (msg.timestamp && prevTs && isDifferentDay(prevTs, msg.timestamp)) {
      elements.push(<DateDivider key={`date-${msg.id}`} label={dateLabel(msg.timestamp)} />);
    } else if (msg.timestamp && !prevTs) {
      // First message: always show date divider
      elements.push(<DateDivider key={`date-first`} label={dateLabel(msg.timestamp)} />);
    }
    prevTs = msg.timestamp;
    elements.push(<MessageBubble key={msg.id} message={msg} />);
  });

  return (
    <div className="chat-container" ref={containerRef} onScroll={onScroll}>
      <div className="chat-inner" role="log" aria-live="polite" aria-atomic="false" aria-relevant="additions">
        {welcomeVisible && <WelcomeScreen onSelect={onExampleClick} />}
        {elements}
        {showStreaming && <StreamingMessage />}
      </div>
      <AnimatePresence>
        {showButton && (
          <motion.button
            className="scroll-to-bottom"
            onClick={forceScrollToBottom}
            aria-label="滚动到底部"
            initial={{ opacity: 0, y: 8, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.9 }}
            transition={{ type: 'spring', duration: 0.4, bounce: 0.2 }}
          >
            <Icon name="chevron-down" size={18} />
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
