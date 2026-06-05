import React, { useState, useEffect, useRef } from 'react';
import { BREED_SPRITES, DEFAULT_BREED } from './breed-sprites';
import type { BreedId, CompanionMood } from './breed-sprites';

export type { CompanionMood, BreedId };

const TICK_MS = 500;

// Idle sequence: 0=rest, 1-2=fidget, -1=blink
const IDLE_SEQ = [0, 0, 0, 0, 1, 0, 0, 0, -1, 0, 0, 2, 0, 0, 0];

// Keep generic SPRITES for backward compat — maps to orange_tabby
const SPRITES = BREED_SPRITES[DEFAULT_BREED];

export type CompanionStage = 'kitten' | 'adult' | 'soulmate';

interface Props {
  mood: CompanionMood;
  breed?: BreedId;
  eyeOverride?: string | null;
  stage?: CompanionStage;
  shiny?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

/** Replace eye characters in sprite lines */
function applyEye(lines: string[], eye: string): string[] {
  if (!eye || eye === '') return lines;
  return lines.map(line =>
    line.replace(/\( . . \)/, `( ${eye} ${eye} )`)
         .replace(/\( .● \)/, `( ${eye}● )`)
         .replace(/\( ●. \)/, `( ●${eye} )`)
  );
}

/** Soulmate breed marks — permanent visual changes at max bond */
const SOULMATE_MARKS: Partial<Record<BreedId, (line: string) => string>> = {
  orange_tabby:   (l) => l.replace('ω', '▽'),
  siamese:        (l) => l.replace('▽', 'ω'),
  black_cat:      (l) => l.replace('◉   ◉', '◉✦ ◉'),
  tuxedo:         (l) => l.replace('◇   ◇', '◇＊◇'),
  scottish_fold:  (l) => l.replace('__/\\__', '~/\\~'),
};

export default function CompanionSprite({ mood, breed, eyeOverride, stage, shiny, className, style }: Props) {
  const breedSprites = (breed && BREED_SPRITES[breed]) ? BREED_SPRITES[breed] : BREED_SPRITES[DEFAULT_BREED];
  const frames = breedSprites[mood];
  const [seqIdx, setSeqIdx] = useState(0);
  const [frame, setFrame] = useState(0);
  const [sparkle, setSparkle] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    timerRef.current = setInterval(() => {
      setSeqIdx((prev) => {
        const next = (prev + 1) % IDLE_SEQ.length;
        const s = IDLE_SEQ[next];
        setFrame(s === -1 ? 0 : s);
        return next;
      });
      // Shiny sparkle: 5% chance each tick
      if (shiny) setSparkle(Math.random() < 0.05);
    }, TICK_MS);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [shiny]);

  // Reset seq on mood change
  useEffect(() => {
    setSeqIdx(0);
    setFrame(0);
  }, [mood]);

  const lines = frames[frame];
  if (!lines) return null;

  const seqStep = IDLE_SEQ[seqIdx];
  const eye = seqStep === -1 ? '-' : (eyeOverride || 'o');
  let display = applyEye([...lines], eye);

  // Soulmate marks
  if (stage === 'soulmate' && breed) {
    const mark = SOULMATE_MARKS[breed];
    if (mark) display = display.map(mark);
  }

  // Shiny particle — prepend sparkle line
  if (shiny && sparkle) {
    display = ['  ＊  ＊  ＊', ...display];
  }

  const kittenScale = stage === 'kitten' ? { transform: 'scale(0.8)', transformOrigin: 'left bottom' } : {};

  return (
    <pre className={className} aria-hidden="true" style={{ ...kittenScale, ...style }}>
      {display.join('\n')}
    </pre>
  );
}

export { SPRITES };
