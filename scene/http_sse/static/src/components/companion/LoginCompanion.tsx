/**
 * LoginCompanion — login page companion with hybrid mood.
 *
 * Login page has NO backend SSE connection (no agent session yet).
 * Mood for visual feedback (zzz ↔ awake ↔ working) is derived
 * from local UI props. This is the ONLY component allowed to do this.
 *
 * After reveal (login click), bones are fetched from
 * GET /api/companion/{uid} and displayed with rarity info.
 *
 * On the chat page, mood is driven by backend EmotionFSM via
 * useCompanionStore.emotion.frontend_mood — see HeaderCompanion.
 */
import React, { useEffect, useRef, useMemo } from 'react';
import CompanionSprite from './CompanionSprite';
import { useCompanionStore } from '../../stores/companion-store';
import { BREED_LABELS } from './breed-sprites';
import type { BreedId } from './breed-sprites';
import type { CompanionMood } from './CompanionSprite';

const RARITY_COLORS: Record<string, string> = {
  common: '#8e8e93', uncommon: '#30d158', rare: '#409cff',
  epic: '#bf5af2', legendary: '#ff9f0a',
};
const RARITY_STARS: Record<string, string> = {
  common: '★', uncommon: '★★', rare: '★★★', epic: '★★★★', legendary: '★★★★★',
};
import './LoginCompanion.css';

interface Props {
  uid: string;
  isNewUser: boolean;
  isReturning: boolean;
  hasInput: boolean;
  loading: boolean;
}

export default function LoginCompanion({ uid, isNewUser, isReturning, hasInput, loading }: Props) {
  const bones = useCompanionStore((s) => s.bones);
  const revealed = useCompanionStore((s) => s.revealed);
  const reveal = useCompanionStore((s) => s.reveal);
  const reset = useCompanionStore((s) => s.reset);

  const prevLoading = useRef(false);
  const trimmed = uid.trim();

  // Reset when uid clears
  useEffect(() => {
    if (!trimmed) reset();
  }, [trimmed, reset]);

  // Reveal bones on login click
  useEffect(() => {
    if (loading && !prevLoading.current && trimmed && !revealed) {
      reveal(trimmed);
    }
    prevLoading.current = loading;
  }, [loading, trimmed, revealed, reveal]);

  // --- login-only mood: derived from local UI props ---
  // (chat page uses backend EmotionFSM — this is the sole exception)
  const mood: CompanionMood = useMemo(() => {
    if (revealed) return 'happy';
    if (loading) return 'working';
    if (!hasInput) return 'sleeping';
    if (isReturning) return 'happy';
    if (isNewUser) return 'awake';
    return 'awake';
  }, [revealed, loading, hasInput, isReturning, isNewUser]);

  const sleeping = mood === 'sleeping';
  const rarity = bones?.rarity;
  const accentColor = rarity ? RARITY_COLORS[rarity] : undefined;
  const stars = rarity ? RARITY_STARS[rarity] : '';

  const breedLabel = bones?.breed ? BREED_LABELS[bones.breed as BreedId] : '';

  return (
    <div className="login-companion" aria-hidden="true">
      <CompanionSprite
        mood={mood}
        breed={bones?.breed as BreedId | undefined}
        className="companion-sprite-art"
      />
      {sleeping && (
        <span className="companion-zzz" aria-hidden="true">
          <span className="companion-zzz-z" style={{ animationDelay: '0s' }}>z</span>
          <span className="companion-zzz-z" style={{ animationDelay: '0.4s' }}>z</span>
          <span className="companion-zzz-z" style={{ animationDelay: '0.2s' }}>Z</span>
        </span>
      )}
      {revealed && bones && (
        <span
          className="companion-rarity"
          style={{ color: accentColor }}
          aria-hidden="true"
        >
          <span className="companion-rarity-stars">{stars}</span>
          <span className="companion-rarity-label">
            {bones.name
              ? `${bones.name} · ${breedLabel}`
              : `${breedLabel ? `${breedLabel} ` : ''}${isNewUser ? '你的专属咪兔' : '一直在等你'}`
            }
          </span>
        </span>
      )}
    </div>
  );
}
