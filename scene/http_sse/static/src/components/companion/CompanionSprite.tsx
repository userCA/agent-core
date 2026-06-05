import React, { useState, useEffect, useRef } from 'react';

export type CompanionMood = 'sleeping' | 'awake' | 'happy' | 'working' | 'concerned';

const TICK_MS = 500;

// Idle sequence: 0=rest, 1-2=fidget, -1=blink
const IDLE_SEQ = [0, 0, 0, 0, 1, 0, 0, 0, -1, 0, 0, 2, 0, 0, 0];

const SPRITES: Record<CompanionMood, string[][]> = {
  sleeping: [
    [
      '  /\\_/\\  ',
      ' ( -.- ) ',
      ' ( z  z )',
      '  \\____/  ',
    ],
    [
      '  /\\~/\\  ',
      ' ( -.- ) ',
      ' ( z  z )',
      '  \\____/  ',
    ],
    [
      '  /\\_/\\  ',
      ' ( -.o ) ',
      ' ( z   z)',
      '  \\____/  ',
    ],
  ],
  awake: [
    [
      '  /\\_/\\  ',
      ' ( o.o ) ',
      ' (  ><  )',
      '  \\____/  ',
    ],
    [
      '  /\\~/\\  ',
      ' ( o.o ) ',
      ' (  ><  )',
      '  \\____/  ',
    ],
    [
      '  /\\_/\\  ',
      ' ( o.O ) ',
      ' (  ><  )',
      '  \\____/  ',
    ],
  ],
  happy: [
    [
      '  /\\_/\\  ',
      ' ( ^.^ ) ',
      ' (  ><  )',
      '  \\____/  ',
    ],
    [
      '  /\\~/\\  ',
      ' ( ^.^ ) ',
      ' (  ><  )',
      '  \\____/  ',
    ],
    [
      '  /\\_/\\  ',
      ' ( ^o^ ) ',
      ' (  ><  )',
      '  \\_~_/  ',
    ],
  ],
  working: [
    [
      '  /\\_/\\  ',
      ' ( •.• ) ',
      ' (  --  )',
      '  \\____/  ',
    ],
    [
      '  /\\~/\\  ',
      ' ( •.• ) ',
      ' (  --  )',
      '  \\____/  ',
    ],
    [
      '  /\\_/\\  ',
      ' ( •.O ) ',
      ' (  --  )',
      '  \\____/  ',
    ],
  ],
  concerned: [
    [
      '  /\\_/\\  ',
      ' ( o.o )?',
      ' (  ~~  )',
      '  \\____/  ',
    ],
    [
      '  /\\~/\\  ',
      ' ( o.o )?',
      ' (  ~~  )',
      '  \\____/  ',
    ],
    [
      '  /\\_/\\  ',
      ' ( O.O )?',
      ' (  ~~  )',
      '  \\____/  ',
    ],
  ],
};

interface Props {
  mood: CompanionMood;
  className?: string;
}

export default function CompanionSprite({ mood, className }: Props) {
  const frames = SPRITES[mood];
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

  return (
    <pre className={className} aria-hidden="true">
      {lines.join('\n')}
    </pre>
  );
}

export { SPRITES };
