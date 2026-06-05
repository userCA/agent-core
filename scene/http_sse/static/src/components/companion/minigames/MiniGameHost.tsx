import React, { useState, useEffect } from 'react';
import { useSessionStore } from '../../../stores/session-store';
import { useChatStore } from '../../../stores/chat-store';
import FishingGame from './FishingGame';

export default function MiniGameHost() {
  const uid = useSessionStore((s) => s.authHeaders.uid || '');
  const isStreaming = useChatStore((s) => s.isStreaming);
  const [active, setActive] = useState(false);
  const [streamStart, setStreamStart] = useState(0);
  const [result, setResult] = useState<{
    food_value: number; items: string[]; reaction: string; bubble: string;
  } | null>(null);

  useEffect(() => {
    if (isStreaming && !streamStart) {
      setStreamStart(Date.now());
    }
    if (!isStreaming) {
      setStreamStart(0);
    }
  }, [isStreaming]);

  const elapsed = streamStart ? (Date.now() - streamStart) / 1000 : 0;

  // Auto-expand after 15s streaming
  useEffect(() => {
    const ival = setInterval(() => {
      if (streamStart && (Date.now() - streamStart) / 1000 > 15 && !active && !result) {
        setActive(true);
      }
    }, 1000);
    return () => clearInterval(ival);
  }, [streamStart, active, result]);

  if (!uid) return null;

  const handleDone = (r: { food_value: number; items: string[]; reaction: string; bubble: string }) => {
    setResult(r);
    setActive(false);
    setTimeout(() => setResult(null), 6000);
  };

  return (
    <>
      {/* Activation button during streaming */}
      {isStreaming && !active && elapsed > 3 && elapsed <= 15 && (
        <button className="minigame-teaser" onClick={() => setActive(true)}>
          🎣 钓鱼等一会儿
        </button>
      )}

      {/* Game overlay */}
      {active && (
        <FishingGame uid={uid} onDone={handleDone} />
      )}

      {/* Result bubble */}
      {result && (
        <div className="minigame-result">
          {result.bubble}
        </div>
      )}
    </>
  );
}
