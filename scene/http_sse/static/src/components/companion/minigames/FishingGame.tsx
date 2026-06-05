/**
 * FishingGame — thin game client.
 *
 * Boundary rules:
 * - Fish data: fetched from backend /api/minigame/config (single source of truth).
 * - Game logic: seeded PRNG runs locally; backend replays for verification.
 * - PRNG: mirrors Python bones._mulberry32 — duplication is intentional
 *   (seed-based replay requires identical PRNG on both sides).
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import './FishingGame.css';

interface FishDef {
  name: string; emoji: string; rarity: string;
  rarity_rank: number; food_value: number; sprite: string;
  appear_weight: number;
}

interface Props {
  uid: string;
  onDone: (result: { food_value: number; items: string[]; reaction: string; bubble: string }) => void;
}

const TICK_MS = 100;

export default function FishingGame({ uid, onDone }: Props) {
  const [phase, setPhase] = useState('waiting');
  const [bobberPos, setBobberPos] = useState(50);
  const [tension, setTension] = useState(0);
  const [catches, setCatches] = useState<FishDef[]>([]);
  const [biteTimer, setBiteTimer] = useState(0);
  const [timer, setTimer] = useState(0);
  const [fishOnHook, setFishOnHook] = useState<FishDef | null>(null);
  const [biteWindow, setBiteWindow] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  const stateRef = useRef({
    seed: 0, signature: '', rng: null as (() => number) | null,
    pond: [] as FishDef[], biteTimer: 0, biteWindow: 0,
    fishOnHook: null as FishDef | null, tension: 0, catches: [] as FishDef[],
    timer: 0, phase: 'waiting', bobberPos: 50,
    actions: [] as { t: number; type: string }[],
  });

  // Init game — fish_table comes from backend (single source of truth)
  useEffect(() => {
    (async () => {
      const res = await fetch(`/api/minigame/config?uid=${encodeURIComponent(uid)}&game=fishing`);
      const { seed, signature, params } = await res.json();
      const rng = mulberry32(seed);
      const s = stateRef.current;
      s.seed = seed;
      s.signature = signature;
      s.rng = rng;
      // Build pond from backend fish_table (no local copy)
      const fishTable: FishDef[] = params.fish_table || [];
      s.pond = buildPond(fishTable, rng, params.rarity_bonus || 0);
      s.bobberPos = Math.floor(rng() * 80 + 10);
      s.biteTimer = rng() * 6 + 2;
      setBobberPos(s.bobberPos);
      setBiteTimer(s.biteTimer);
    })();
  }, [uid]);

  // Tick loop and state sync
  useEffect(() => {
    const ival = setInterval(() => {
      const s = stateRef.current;
      if (submitting) return;
      s.timer += TICK_MS / 1000;
      setTimer(s.timer);

      if (s.phase === 'waiting' && s.timer >= s.biteTimer) {
        s.phase = 'biting';
        s.fishOnHook = rollFish(s.pond, s.rng!);
        s.biteWindow = s.rng!() * 0.9 + 0.6;
        setPhase('biting');
        setFishOnHook(s.fishOnHook);
        setBiteWindow(s.biteWindow);
      }

      if ((s.phase === 'missed' || s.phase === 'caught') && s.timer >= s.biteTimer + (s.phase === 'caught' ? 2 : 3)) {
        s.phase = 'waiting';
        s.biteTimer = s.timer + s.rng!() * 4.5 + 1.5;
        s.fishOnHook = null;
        setPhase('waiting');
        setFishOnHook(null);
        setBiteTimer(s.biteTimer);
      }

      if (s.timer >= 90 && !submitting) {
        finish();
      }
    }, TICK_MS);
    return () => clearInterval(ival);
  }, [submitting]);

  const onReel = useCallback(() => {
    const s = stateRef.current;
    if (s.phase !== 'biting') return;
    s.actions.push({ t: s.timer, type: 'reel' });
    if (s.timer <= s.biteTimer + s.biteWindow) {
      s.phase = 'reeling';
      s.tension = 0.3;
      setPhase('reeling');
      setTension(0.3);
    } else {
      s.phase = 'missed';
      s.fishOnHook = null;
      setPhase('missed');
      setFishOnHook(null);
    }
  }, []);

  const onPull = useCallback(() => {
    const s = stateRef.current;
    if (s.phase !== 'reeling') return;
    s.tension = Math.min(1, s.tension + 0.05);
    setTension(s.tension);
    if (s.tension >= 1) {
      s.phase = 'caught';
      s.catches.push(s.fishOnHook!);
      s.actions.push({ t: s.timer, type: 'pull' });
      setPhase('caught');
      setCatches([...s.catches]);
    }
  }, []);

  // Tension decay when not pulling
  useEffect(() => {
    const ival = setInterval(() => {
      const s = stateRef.current;
      if (s.phase === 'reeling') {
        s.tension = Math.max(0, s.tension - 0.02);
        setTension(s.tension);
        if (s.tension <= 0) {
          s.phase = 'missed';
          s.fishOnHook = null;
          setPhase('missed');
          setFishOnHook(null);
        }
      }
    }, TICK_MS);
    return () => clearInterval(ival);
  }, []);

  async function finish() {
    setSubmitting(true);
    const s = stateRef.current;
    try {
      const totalFood = s.catches.reduce((a, f) => a + f.food_value, 0);
      const result = { food_value: totalFood, items: s.catches.map(f => f.name) };
      const res = await fetch('/api/minigame/feed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uid, game: 'fishing', seed: s.seed, signature: s.signature,
          actions: s.actions, result,
        }),
      });
      const data = await res.json();
      onDone({ ...result, reaction: data.reaction || 'yummy', bubble: data.bubble || '好吃！' });
    } catch {
      onDone({ food_value: 0, items: [], reaction: 'nibble', bubble: '鱼跑了...' });
    }
  }

  const remaining = Math.max(0, 90 - Math.floor(timer));
  const progressPct = Math.min(100, (tension * 100));

  return (
    <div className="fishing-game">
      {/* Single-row compact layout */}
      <span className="fishing-timer">{remaining}s</span>

      <span className="fishing-pond-h">
        <span className="fishing-waves-h">~~~~</span>
        <span className={`fishing-bobber-h ${phase === 'biting' ? 'biting' : ''}`}>
          {phase === 'biting' ? '◎' : '○'}
        </span>
        {fishOnHook && phase === 'biting' && (
          <span className="fishing-fish-shadow-h">{fishOnHook.sprite}</span>
        )}
        <span className="fishing-waves-h">~~~~</span>
      </span>

      {phase === 'reeling' && (
        <span className="fishing-tension-h">
          <span className="fishing-tension-bar-h">
            <span className="fishing-tension-fill-h" style={{ width: `${progressPct}%` }} />
          </span>
        </span>
      )}

      {phase === 'biting' && (
        <button className="btn btn-primary fishing-btn" onClick={onReel}>收线</button>
      )}
      {phase === 'reeling' && (
        <button className="btn btn-primary fishing-btn" onMouseDown={onPull} onTouchStart={onPull}>拉</button>
      )}
      {phase === 'waiting' && (
        <span className="fishing-waiting-h">等待咬钩...</span>
      )}
      {phase === 'missed' && (
        <span className="fishing-missed-h">跑了!</span>
      )}
      {phase === 'caught' && fishOnHook && (
        <span className="fishing-caught-h">{fishOnHook.emoji} {fishOnHook.name}!</span>
      )}

      {catches.length > 0 && (
        <span className="fishing-catches-h">
          {catches.map((f, i) => (
            <span key={i} className="fishing-catch-item" title={f.name}>{f.emoji}</span>
          ))}
        </span>
      )}

      <button className="fishing-close-btn" onClick={finish} disabled={submitting} aria-label="关闭钓鱼">
        ✕
      </button>
    </div>
  );
}

// -- PRNG — intentionally mirrors Python bones._mulberry32 -----------------
// Duplication is by design: seed-based replay verification requires the
// frontend and backend to produce identical random sequences from the same seed.

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// -- fish util — uses API-provided fish_table (single source of truth) ----

function buildPond(fishTable: FishDef[], rng: () => number, bonus: number): FishDef[] {
  const pond: FishDef[] = [];
  for (const f of fishTable) {
    const base = f.appear_weight || (f.rarity_rank > 0 ? 1 : 10);
    const weight = f.rarity_rank > 0 ? base + bonus : base;
    for (let i = 0; i < weight; i++) pond.push(f);
  }
  return pond;
}

function rollFish(pond: FishDef[], rng: () => number): FishDef {
  return pond[Math.floor(rng() * pond.length)];
}
