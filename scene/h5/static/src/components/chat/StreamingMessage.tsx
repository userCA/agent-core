import React, { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useTypewriter } from '../../hooks/useTypewriter';
import { getDisplayableText } from '../../utils/think';

import TraceCard from './TraceCard';
import AudioPlayer from '../tools/AudioPlayer';
import HitlCard from '../hitl/HitlCard';
import './StreamingMessage.css';

/** Moon SVG avatar matching the prototype */
const MoonAvatar = () => (
  <div className="msg-avatar">
    <svg className="msg-avatar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454z"/>
      <path d="M12 8v4"/>
      <path d="M12 16h.01"/>
    </svg>
  </div>
);

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
      <div className="msg-row msg-row-assistant">
        <MoonAvatar />
        <div className="msg-col msg-col-assistant">
          <div className="bubble bubble-assistant streaming-bubble">
            <div className="typing-dots">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="msg-row msg-row-assistant">
      <MoonAvatar />
      <div className="msg-col msg-col-assistant">
        {/* Trace card rendered standalone (outside bubble) for distinct visual treatment */}
        {streamBlocks.length > 0 && (
          <div className={`bubble bubble-assistant bubble-trace-only${!isStreaming ? ' fade-out' : ''}`}>
            <div className="msg-content">
              <TraceCard blocks={streamBlocks} />
            </div>
          </div>
        )}

        <div className={`bubble bubble-assistant streaming-bubble${!isStreaming ? ' fade-out' : ''}`}>
          {streamBlocks.length > 0 ? (
            <div className="final-content streaming hidden" />
          ) : (
            <div ref={contentRef} className="final-content streaming" />
          )}

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
    </div>
  );
}
