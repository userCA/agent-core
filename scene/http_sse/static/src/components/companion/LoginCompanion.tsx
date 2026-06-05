import React, { useEffect, useRef } from 'react';
import CompanionSprite from './CompanionSprite';
import { useCompanionStore } from '../../stores/companion-store';
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
  const mood = useCompanionStore((s) => s.mood);
  const bones = useCompanionStore((s) => s.bones);
  const revealed = useCompanionStore((s) => s.revealed);
  const setMood = useCompanionStore((s) => s.setMood);
  const reveal = useCompanionStore((s) => s.reveal);
  const reset = useCompanionStore((s) => s.reset);

  const prevLoading = useRef(false);
  const trimmed = uid.trim();

  // Reset only when uid clears entirely (user starts fresh)
  useEffect(() => {
    if (!trimmed) reset();
  }, [trimmed, reset]);

  // Reveal on login click (loading transitions from false → true)
  useEffect(() => {
    if (loading && !prevLoading.current && trimmed && !revealed) {
      reveal(trimmed);
    }
    prevLoading.current = loading;
  }, [loading, trimmed, revealed, reveal]);

  // Determine target mood
  const targetMood: CompanionMood = revealed
    ? 'happy'
    : loading
      ? 'working'
      : !hasInput
        ? 'sleeping'
        : isNewUser
          ? 'awake'
          : isReturning
            ? 'happy'
            : 'awake';

  useEffect(() => {
    setMood(targetMood);
  }, [targetMood, setMood]);

  const sleeping = mood === 'sleeping';
  const rarity = bones?.rarity;
  const accentColor = rarity ? RARITY_COLORS[rarity] : undefined;
  const stars = rarity ? RARITY_STARS[rarity] : '';

  return (
    <div className="login-companion" aria-hidden="true">
      <CompanionSprite mood={mood} className="companion-sprite-art" />
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
            {isNewUser ? '你的专属咪兔' : '一直在等你'}
          </span>
        </span>
      )}
    </div>
  );
}
