import React, { useState, useEffect, useRef, useCallback } from 'react';
import './FishingGame.css';

interface FishDef {
  name: string; emoji: string; rarity: string;
  rarity_rank: number; food_value: number; sprite: string;
}

interface Props {
  uid: string;
  onDone: (result: { food_value: number; items: string[]; reaction: string; bubble: string }) => void;
}

const TICK_MS = 100;

// Minimal local copy of fish data for sprite rendering
const FISH_SPRITES: Record<string, string> = {
  '小虾米': '~ <><', '鲫鱼': '<><', '小螃蟹': '~ v.v ~',
  '鲤鱼': '><>', '鱿鱼': '~<O>~', '金鱼': '~<><~',
  '三文鱼': '><<<>', '灯笼鱼': '~<O>~', '电鳗': '~zzZ~',
  '锦鲤': '><<<>>', '金龙鱼': '~<O>~', '美人鱼': '><O><',
};

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

  // Init game
  useEffect(() => {
    (async () => {
      const res = await fetch(`/api/minigame/config?uid=${encodeURIComponent(uid)}&game=fishing`);
      const { seed, signature, params } = await res.json();
      const rng = mulberry32(seed);
      const s = stateRef.current;
      s.seed = seed;
      s.signature = signature;
      s.rng = rng;
      s.pond = generatePond(rng, params.rarity_bonus || 0);
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
      <div className="fishing-header">
        <span className="fishing-icon">🎣</span>
        <span className="fishing-timer">{remaining}s</span>
      </div>

      <div className="fishing-pond">
        <div className="fishing-waves">
          <span className="wave">~~~~</span>
          <span className="wave">~~~~</span>
          <span className="wave">~~~~</span>
        </div>
        <div className="fishing-bobber" style={{ left: `${bobberPos}%` }}>
          {phase === 'biting' ? '◎' : '○'}
        </div>
        {fishOnHook && phase === 'biting' && (
          <div className="fishing-fish-shadow">
            {FISH_SPRITES[fishOnHook.name] || '~>~'}
          </div>
        )}
        <div className="fishing-waves">
          <span className="wave">~~~~</span>
          <span className="wave">~~~~</span>
          <span className="wave">~~~~</span>
        </div>
      </div>

      {phase === 'reeling' && (
        <div className="fishing-tension">
          <div className="fishing-tension-bar">
            <div className="fishing-tension-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <span>松线中... 点击收线!</span>
        </div>
      )}

      <div className="fishing-actions">
        {phase === 'biting' && (
          <button className="btn btn-primary fishing-btn" onClick={onReel}>
            收线!
          </button>
        )}
        {phase === 'reeling' && (
          <button className="btn btn-primary fishing-btn" onMouseDown={onPull} onTouchStart={onPull}>
            拉!
          </button>
        )}
        {phase === 'waiting' && (
          <span className="fishing-waiting">等待鱼咬钩...</span>
        )}
        {phase === 'missed' && (
          <span className="fishing-missed">鱼跑了!</span>
        )}
        {phase === 'caught' && fishOnHook && (
          <span className="fishing-caught">钓到了 {fishOnHook.emoji} {fishOnHook.name}!</span>
        )}
      </div>

      {catches.length > 0 && (
        <div className="fishing-catches">
          已钓到: {catches.map((f, i) => (
            <span key={i} className="fishing-catch-item" title={f.name}>{f.emoji}</span>
          ))}
        </div>
      )}

      <button className="fishing-end-btn" onClick={finish} disabled={submitting}>
        {submitting ? '结算中...' : '提前结束'}
      </button>
    </div>
  );
}

// -- local PRNG (matches Python bones._mulberry32) --

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// -- local fish generation (mirrors fish_table.py) --

const LOCAL_FISH: FishDef[] = [
  { name: '小虾米', emoji: '🦐', rarity: 'common', rarity_rank: 0, food_value: 5, sprite: '~ <><' },
  { name: '鲫鱼', emoji: '🐟', rarity: 'common', rarity_rank: 0, food_value: 8, sprite: '<><' },
  { name: '小螃蟹', emoji: '🦀', rarity: 'common', rarity_rank: 0, food_value: 6, sprite: '~ v.v ~' },
  { name: '鲤鱼', emoji: '🐠', rarity: 'uncommon', rarity_rank: 1, food_value: 15, sprite: '><>' },
  { name: '鱿鱼', emoji: '🦑', rarity: 'uncommon', rarity_rank: 1, food_value: 18, sprite: '~<O>~' },
  { name: '金鱼', emoji: '🔶', rarity: 'uncommon', rarity_rank: 1, food_value: 12, sprite: '~<><~' },
  { name: '三文鱼', emoji: '🐡', rarity: 'rare', rarity_rank: 2, food_value: 30, sprite: '><<<>' },
  { name: '灯笼鱼', emoji: '🎃', rarity: 'rare', rarity_rank: 2, food_value: 35, sprite: '~<O>~' },
  { name: '电鳗', emoji: '⚡', rarity: 'epic', rarity_rank: 3, food_value: 60, sprite: '~zzZ~' },
  { name: '锦鲤', emoji: '🎏', rarity: 'epic', rarity_rank: 3, food_value: 50, sprite: '><<<>>' },
  { name: '金龙鱼', emoji: '🐉', rarity: 'legendary', rarity_rank: 4, food_value: 100, sprite: '~<O>~' },
  { name: '美人鱼', emoji: '🧜', rarity: 'legendary', rarity_rank: 4, food_value: 120, sprite: '><O><' },
];

function generatePond(rng: () => number, bonus: number): FishDef[] {
  const pond: FishDef[] = [];
  for (const f of LOCAL_FISH) {
    const weight = f.rarity_rank > 0 ? 1 + bonus : 10;
    for (let i = 0; i < weight; i++) pond.push(f);
  }
  return pond;
}

function rollFish(pond: FishDef[], rng: () => number): FishDef {
  return pond[Math.floor(rng() * pond.length)];
}
