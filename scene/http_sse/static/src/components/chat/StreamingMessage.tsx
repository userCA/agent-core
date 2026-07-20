import React, { useEffect, useRef, useCallback } from 'react';
import { useChatStore, type MessageBlock } from '../../stores/chat-store';
import { useTypewriter } from '../../hooks/useTypewriter';
import { getDisplayableText } from '../../utils/think';

import BlocksRenderer from './BlocksRenderer';
import AudioPlayer from '../tools/AudioPlayer';
import HitlCard from '../hitl/HitlCard';
import './StreamingMessage.css';

function StatusBar({ blocks }: { blocks: MessageBlock[] }) {
  const running = blocks.find(b => b.status === 'running');
  const label = running
    ? running.type === 'delegation'
      ? '正在协调专家...'
      : running.type === 'tool' ? `正在调用 ${running.label || '工具'}...` : '思考中...'
    : '处理中...';
  return (
    <div className="status-bar">
      <span className="orbit-dots"><i /><i /><i /><i /><i /><i /></span>
      <span className="status-text">{label}</span>
    </div>
  );
}

export default function StreamingMessage() {
  const {
    currentText, streamBlocks,
    audios, hitlRequest,
    isStreaming, setHitlRequest,
  } = useChatStore();

  const contentRef = useRef<HTMLDivElement>(null);

  // Stream-only raw text renderer: avoids Markdown-parse flash & perf cost.
  // Final markdown is rendered by MessageBubble once streaming ends.
  const handleFlush = useCallback((displayed: string) => {
    if (!contentRef.current) return;
    if (!displayed) {
      contentRef.current.innerHTML = '';
      return;
    }
    // Trim leading newlines and collapse multiple consecutive newlines
    // to match markdown paragraph-break behavior (avoids blank lines).
    let trimmed = displayed.replace(/^\n+/, '');
    trimmed = trimmed.replace(/\n{2,}/g, '\n\n');
    const el = contentRef.current;
    el.innerHTML = '';
    const lines = trimmed.split('\n');
    lines.forEach((line, i) => {
      el.appendChild(document.createTextNode(line));
      if (i < lines.length - 1) {
        el.appendChild(document.createElement('br'));
      }
    });
  }, []);

  const typewriter = useTypewriter({
    speed: 18,
    onFlush: handleFlush,
  });

  // Only enqueue characters outside <think> blocks — prevents think-tag flash.
  // When displayable text shrinks (think tag completed, partial leak cleaned),
  // reset the typewriter to clear any leaked garbage and start fresh.
  const prevDisplayLen = useRef(0);
  useEffect(() => {
    const displayable = getDisplayableText(currentText);
    if (displayable.length < prevDisplayLen.current) {
      // Think tag boundary: displayable text shrank. Reset and replay clean text.
      typewriter.reset();
      prevDisplayLen.current = 0;
      if (contentRef.current) contentRef.current.innerHTML = '';
      if (displayable.length > 0) {
        typewriter.enqueue(displayable);
        prevDisplayLen.current = displayable.length;
      }
      return;
    }
    if (displayable.length > prevDisplayLen.current) {
      const delta = displayable.slice(prevDisplayLen.current);
      typewriter.enqueue(delta);
      prevDisplayLen.current = displayable.length;
    }
  }, [currentText, typewriter]);

  // Reset on new stream
  const wasStreaming = useRef(false);
  useEffect(() => {
    if (!isStreaming && wasStreaming.current) {
      typewriter.reset();
      prevDisplayLen.current = 0;
    }
    wasStreaming.current = isStreaming;
  }, [isStreaming, typewriter]);

  const hasContent = currentText.length > 0 || streamBlocks.length > 0;

  if (!hasContent && !hitlRequest && !streamBlocks.length) {
    return (
      <div className="msg-wrapper msg-assistant">
        <span className="msg-label">助手</span>
        <div className="bubble bubble-assistant streaming-bubble">
          <div className="thinking-indicator">
            <span className="orbit-dots"><i /><i /><i /><i /><i /><i /></span>
            <span className="status-text">思考中...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="msg-wrapper msg-assistant">
      <span className="msg-label">助手</span>
      <div className={`bubble bubble-assistant streaming-bubble${!isStreaming ? ' fade-out' : ''}`}>
        <div className="msg-content">
          <div ref={contentRef} className={`final-content streaming${streamBlocks.length > 0 ? ' hidden' : ''}`} />
          {streamBlocks.length > 0 ? (
            <BlocksRenderer blocks={streamBlocks} />
          ) : isStreaming ? (
            <div className="steps-panel">
              <div className="step-section active">
                <div className="section-summary">
                  <span className="section-label">
                    <span className="orbit-dots"><i /><i /><i /><i /><i /><i /></span>
                    思考中...
                  </span>
                </div>
              </div>
            </div>
          ) : null}
          {streamBlocks.length > 0 && isStreaming && (
            <StatusBar blocks={streamBlocks} />
          )}
        </div>

        {audios.map((a, i) => <AudioPlayer key={`a-${i}`} audio={a} />)}

        {hitlRequest && (
          <HitlCard
            toolCallId={hitlRequest.toolCallId}
            prompt={hitlRequest.prompt}
            inputSchema={hitlRequest.inputSchema}
            onSubmitted={() => setHitlRequest(null)}
          />
        )}
      </div>
    </div>
  );
}
