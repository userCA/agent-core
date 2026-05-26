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

  const { containerRef, onScroll, scrollToBottom } = useAutoScroll([
    messages, currentText, steps,
  ]);

  return (
    <div className="chat-container" ref={containerRef} onScroll={onScroll}>
      <div className="chat-inner">
        {welcomeVisible && <WelcomeScreen onSelect={onExampleClick} />}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isStreaming && <StreamingMessage />}
      </div>
    </div>
  );
}
