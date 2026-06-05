import React, { useEffect, useRef } from 'react';
import { useCompanionStore } from '../../stores/companion-store';
import CompanionSprite from './CompanionSprite';
import type { BreedId } from './breed-sprites';

/**
 * HeaderCompanion — thin renderer for the chat header.
 *
 * Mood / emotion / bubble come from backend via useCompanionStore.
 * No local mood logic — the backend FSM drives all state.
 */
export default function HeaderCompanion() {
  const mood = useCompanionStore((s) => s.mood);
  const bones = useCompanionStore((s) => s.bones);
  const emotion = useCompanionStore((s) => s.emotion);
  const bubble = useCompanionStore((s) => s.bubble);
  const setBubble = useCompanionStore((s) => s.setBubble);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-dismiss bubble after ttl_ms
  useEffect(() => {
    if (!bubble) return;
    timerRef.current = setTimeout(() => setBubble(null), bubble.ttl_ms);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [bubble, setBubble]);

  return (
    <span className="header-companion" style={{ display: 'inline-flex', alignItems: 'flex-end', gap: 4 }}>
      <CompanionSprite
        mood={mood}
        breed={bones?.breed as BreedId | undefined}
        eyeOverride={emotion?.eye_override ?? null}
        shiny={bones?.shiny ?? false}
        className="header-companion-art"
      />
      {bubble && (
        <span className="companion-bubble-speech" aria-live="polite">
          {bubble.text}
        </span>
      )}
    </span>
  );
}
