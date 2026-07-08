import { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useCompanionStore } from '../../stores/companion-store';
import CompanionSprite from './CompanionSprite';
import type { BreedId } from './breed-sprites';

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
    <span className="header-companion">
      <span className="header-companion-shell">
        <CompanionSprite
          mood={mood}
          breed={bones?.breed as BreedId | undefined}
          eyeOverride={emotion?.eye_override ?? null}
          shiny={bones?.shiny ?? false}
          variant="header"
          className="header-companion-art"
        />
        <AnimatePresence>
          {bubble && (
            <motion.span
              key="bubble"
              className="companion-bubble-speech"
              aria-live="polite"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              transformTemplate={(_, generated) => `translateX(-24%) ${generated}`}
            >
              {bubble.text}
            </motion.span>
          )}
        </AnimatePresence>
      </span>
    </span>
  );
}
