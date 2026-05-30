import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useUIStore } from '../../stores/ui-store';
import { useAutoScroll } from '../../hooks/useAutoScroll';
import MessageBubble from './MessageBubble';
import StreamingMessage from './StreamingMessage';
import WelcomeScreen from './WelcomeScreen';
import './ChatContainer.css';

interface Props {
  onExampleClick?: (text: string) => void;
}

export default function ChatContainer({ onExampleClick }: Props) {
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const currentText = useChatStore((s) => s.currentText);
  const steps = useChatStore((s) => s.steps);
  const welcomeVisible = useUIStore((s) => s.welcomeVisible) && messages.length === 0;

  // While StreamingMessage is fading out (after stream ends), hide the last
  // assistant MessageBubble so the same content isn't rendered twice.
  const showStreaming = isStreaming || currentText.length > 0;
  const lastMsg = messages[messages.length - 1];
  const hideLastBubble = showStreaming && lastMsg?.role === 'assistant';
  const displayMessages = hideLastBubble ? messages.slice(0, -1) : messages;

  const { containerRef, onScroll, scrollToBottom } = useAutoScroll([
    messages, currentText, steps.length,
  ]);

  return (
    <div className="chat-container" ref={containerRef} onScroll={onScroll}>
      <div className="chat-inner" role="log" aria-live="polite" aria-atomic="false" aria-relevant="additions">
        {welcomeVisible && <WelcomeScreen onSelect={onExampleClick} />}
        {displayMessages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {showStreaming && <StreamingMessage />}
      </div>
    </div>
  );
}
