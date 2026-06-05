import { useEffect, useLayoutEffect, useRef } from 'react';
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
  const shellRef = useRef<HTMLSpanElement | null>(null);
  const bubbleRef = useRef<HTMLSpanElement | null>(null);

  // Auto-dismiss bubble after ttl_ms
  useEffect(() => {
    if (!bubble) return;
    timerRef.current = setTimeout(() => setBubble(null), bubble.ttl_ms);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [bubble, setBubble]);

  useLayoutEffect(() => {
    const shell = shellRef.current;
    const host = shell?.closest('.header-left') as HTMLElement | null;
    if (!shell || !host) return;

    const updateChipAnchor = () => {
      const hostRect = host.getBoundingClientRect();
      const shellRect = shell.getBoundingClientRect();
      const bubbleRect = bubbleRef.current?.getBoundingClientRect() ?? null;
      const anchorRight = Math.max(shellRect.right, bubbleRect?.right ?? 0);
      const nextLeft = Math.min(
        Math.max(anchorRight - hostRect.left + 10, shellRect.right - hostRect.left + 10),
        Math.max(hostRect.width - 96, 72),
      );

      host.style.setProperty('--minigame-chip-left', `${Math.round(nextLeft)}px`);
    };

    updateChipAnchor();
    const observer = new ResizeObserver(updateChipAnchor);
    observer.observe(shell);
    observer.observe(host);
    if (bubbleRef.current) observer.observe(bubbleRef.current);
    window.addEventListener('resize', updateChipAnchor);

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', updateChipAnchor);
      host.style.removeProperty('--minigame-chip-left');
    };
  }, [bubble?.text]);

  return (
    <span className="header-companion">
      <span className="header-companion-shell" ref={shellRef}>
        <CompanionSprite
          mood={mood}
          breed={bones?.breed as BreedId | undefined}
          eyeOverride={emotion?.eye_override ?? null}
          shiny={bones?.shiny ?? false}
          variant="header"
          className="header-companion-art"
        />
        {bubble && (
          <span className="companion-bubble-speech" aria-live="polite" ref={bubbleRef}>
            {bubble.text}
          </span>
        )}
      </span>
    </span>
  );
}
