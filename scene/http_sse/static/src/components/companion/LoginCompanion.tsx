import React from 'react';
import CompanionSprite from './CompanionSprite';
import { useCompanionStore } from '../../stores/companion-store';
import type { CompanionMood } from './CompanionSprite';
import './LoginCompanion.css';

interface Props {
  isNewUser: boolean;
  isReturning: boolean;
  hasInput: boolean;
  loading: boolean;
}

export default function LoginCompanion({ isNewUser, isReturning, hasInput, loading }: Props) {
  const mood = useCompanionStore((s) => s.mood);
  const setMood = useCompanionStore((s) => s.setMood);

  const sleeping = mood === 'sleeping';

  // Determine target mood from props
  const targetMood: CompanionMood = loading
    ? 'working'
    : !hasInput
      ? 'sleeping'
      : isNewUser
        ? 'awake'
        : isReturning
          ? 'happy'
          : 'awake';

  // Update store mood when target changes
  React.useEffect(() => {
    setMood(targetMood);
  }, [targetMood, setMood]);

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
    </div>
  );
}
