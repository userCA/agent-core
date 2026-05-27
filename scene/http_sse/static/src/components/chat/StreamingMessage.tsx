import React, { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useTypewriter } from '../../hooks/useTypewriter';
import { getDisplayableText } from '../../utils/think';

import StepsPanel from '../tools/StepsPanel';
import WidgetFrame from '../tools/WidgetFrame';
import AudioPlayer from '../tools/AudioPlayer';
import HitlCard from '../hitl/HitlCard';
import './StreamingMessage.css';

export default function StreamingMessage() {
  const {
    currentText, steps,
    widgets, audios, hitlRequest,
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
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(trimmed));
    contentRef.current.innerHTML = div.innerHTML.replace(/\n/g, '<br>');
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

  const hasContent = currentText.length > 0 || steps.length > 0;

  if (!hasContent && !hitlRequest && steps.length === 0) {
    return (
      <div className="msg-wrapper msg-assistant">
        <span className="msg-label">assistant</span>
        <div className="bubble bubble-assistant streaming-bubble">
          <div className="thinking-indicator">
            <span className="thinking-dot" />
            <span className="thinking-dot" />
            <span className="thinking-dot" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="msg-wrapper msg-assistant">
      <span className="msg-label">assistant</span>
      <div className="bubble bubble-assistant streaming-bubble">
        <div className="msg-content">
          <StepsPanel />
          <div
            ref={contentRef}
            className={`final-content markdown-body${isStreaming ? ' streaming' : ''}`}
            aria-live="polite"
            aria-atomic="false"
            aria-label="AI 正在生成回复"
          />
        </div>

        {widgets.map((w, i) => <WidgetFrame key={`w-${i}`} widget={w} />)}
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
