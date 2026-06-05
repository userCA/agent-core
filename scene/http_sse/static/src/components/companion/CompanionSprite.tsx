import React, { useState, useEffect, useRef } from 'react';
import { BREED_SPRITES, DEFAULT_BREED } from './breed-sprites';
import type { BreedId, CompanionMood } from './breed-sprites';

export type { CompanionMood, BreedId };

const TICK_MS = 500;

// Idle sequence: 0=rest, 1-2=fidget, -1=blink
const IDLE_SEQ = [0, 0, 0, 0, 1, 0, 0, 0, -1, 0, 0, 2, 0, 0, 0];

// Keep generic SPRITES for backward compat — maps to orange_tabby
const SPRITES = BREED_SPRITES[DEFAULT_BREED];

interface Props {
  mood: CompanionMood;
  breed?: BreedId;
  eyeOverride?: string | null;
  className?: string;
}

/** Replace eye characters in sprite lines: ( X X ) → ( eye eye ) */
function applyEye(lines: string[], eye: string): string[] {
  if (!eye || eye === '') return lines;
  return lines.map(line =>
    line.replace(/\( . . \)/, `( ${eye} ${eye} )`)
         .replace(/\( .● \)/, `( ${eye}● )`)   // calico heterochromia
         .replace(/\( ●. \)/, `( ●${eye} )`)
  );
}

export default function CompanionSprite({ mood, breed, eyeOverride, className }: Props) {
  const breedSprites = (breed && BREED_SPRITES[breed]) ? BREED_SPRITES[breed] : BREED_SPRITES[DEFAULT_BREED];
  const frames = breedSprites[mood];
  const [seqIdx, setSeqIdx] = useState(0);
  const [frame, setFrame] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    timerRef.current = setInterval(() => {
      setSeqIdx((prev) => {
        const next = (prev + 1) % IDLE_SEQ.length;
        const s = IDLE_SEQ[next];
        setFrame(s === -1 ? 0 : s);
        return next;
      });
    }, TICK_MS);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  // Reset seq on mood change
  useEffect(() => {
    setSeqIdx(0);
    setFrame(0);
  }, [mood]);

  const lines = frames[frame];
  if (!lines) return null;

  // Apply eye override — blink uses '-' eye, eyeOverride overrides default
  const seqStep = IDLE_SEQ[seqIdx];
  const eye = seqStep === -1 ? '-' : (eyeOverride || 'o');
  const display = applyEye([...lines], eye);

  return (
    <pre className={className} aria-hidden="true">
      {display.join('\n')}
    </pre>
  );
}

export { SPRITES };
