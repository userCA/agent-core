import React from 'react';
import { useCompanionStore } from '../../stores/companion-store';
import CompanionSprite from './CompanionSprite';
import type { BreedId } from './breed-sprites';

/**
 * HeaderCompanion — thin renderer for the chat header.
 *
 * Mood / emotion come from backend via useCompanionStore.emotion.
 * No local mood logic — the backend FSM drives the state.
 */
export default function HeaderCompanion() {
  const mood = useCompanionStore((s) => s.mood);
  const bones = useCompanionStore((s) => s.bones);
  const emotion = useCompanionStore((s) => s.emotion);

  return (
    <CompanionSprite
      mood={mood}
      breed={bones?.breed as BreedId | undefined}
      eyeOverride={emotion?.eye_override ?? null}
      className="header-companion-art"
    />
  );
}
