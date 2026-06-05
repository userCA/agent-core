import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchMinigameConfig, submitMinigameResult } from './game-api';
import type { MiniGameProps } from './types';

const TICK_MS = 160;
const SLOTS = 9;

export default function CatchGame({ uid, onDone, label = '* catch', onSwitchGame }: MiniGameProps) {
  const [cursor, setCursor] = useState(0);
  const [target, setTarget] = useState(4);
  const [score, setScore] = useState(0);
  const [streak, setStreak] = useState(0);
  const [timer, setTimer] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [flash, setFlash] = useState<'hit' | 'miss' | 'idle'>('idle');

  const stateRef = useRef({
    seed: 0,
    signature: '',
    timer: 0,
    cursor: 0,
    target: 4,
    score: 0,
    streak: 0,
    actions: [] as Array<{ t: number; type: string }>,
    maxDuration: 45,
    tick: 0,
  });

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchMinigameConfig(uid, 'catch');
        stateRef.current.seed = data.seed;
        stateRef.current.signature = data.signature;
        stateRef.current.maxDuration = Math.min(60, data.params.max_duration_s || 45);
        stateRef.current.target = 2 + (data.seed % (SLOTS - 4));
        setTarget(stateRef.current.target);
      } catch {
        stateRef.current.maxDuration = 45;
      }
    })();
  }, [uid]);

  useEffect(() => {
    const ival = setInterval(() => {
      if (submitting) return;
      const s = stateRef.current;
      s.tick += 1;
      s.timer += TICK_MS / 1000;
      s.cursor = (s.cursor + 1) % SLOTS;
      if (s.tick % 8 === 0) {
        s.target = (s.target + 2 + (s.seed % 3)) % SLOTS;
      }
      setTimer(s.timer);
      setCursor(s.cursor);
      setTarget(s.target);
      if (s.timer >= s.maxDuration) {
        void finish();
      }
    }, TICK_MS);
    return () => clearInterval(ival);
  }, [submitting]);

  const onCatch = useCallback(() => {
    const s = stateRef.current;
    const distance = Math.abs(s.cursor - s.target);
    s.actions.push({ t: s.timer, type: 'catch' });
    if (distance <= 1) {
      s.score += 1;
      s.streak += 1;
      setScore(s.score);
      setStreak(s.streak);
      setFlash('hit');
    } else {
      s.streak = 0;
      setStreak(0);
      setFlash('miss');
    }
    setTimeout(() => setFlash('idle'), 260);
  }, []);

  async function finish() {
    if (submitting) return;
    setSubmitting(true);
    const s = stateRef.current;
    const totalFood = s.score * 3 + Math.min(6, s.streak);
    const items = Array.from({ length: s.score }, (_, idx) => `掉落碎鱼-${idx + 1}`);
    try {
      const data = await submitMinigameResult(
        uid,
        'catch',
        s.seed,
        s.signature,
        { food_value: totalFood, items },
        s.actions
      );
      onDone({
        food_value: totalFood,
        items,
        reaction: data.reaction || 'excited',
        bubble: data.bubble || '抓到了好多零嘴！',
      });
    } catch {
      onDone({
        food_value: totalFood,
        items,
        reaction: 'nibble',
        bubble: s.score > 0 ? '抓到了几块小零食。' : '一块都没接住...',
      });
    }
  }

  const remaining = Math.max(0, stateRef.current.maxDuration - Math.floor(timer));
  const lane = Array.from({ length: SLOTS }, (_, idx) => {
    if (idx === cursor && idx === target) return '◎';
    if (idx === cursor) return '●';
    if (idx === target) return '×';
    return '.';
  }).join('');
  const logText =
    flash === 'hit' ? `接住了，连中 ${streak} 次` :
    flash === 'miss' ? '没接住，继续试试' :
    '光点对齐叉号时点击';

  return (
    <div className={`minigame-inline-game catch-game ${flash !== 'idle' ? `is-${flash}` : ''}`}>
      <button
        type="button"
        className={`minigame-inline-chip ${onSwitchGame ? 'is-switcher' : ''}`}
        onClick={onSwitchGame}
        aria-label="切换小游戏"
      >
        {label}
      </button>
      <span className="minigame-inline-state">对准再接</span>
      <span className="catch-lane">[{lane}]</span>
      <span className="minigame-inline-log">{logText}</span>
      <button className="btn btn-primary fishing-btn" onClick={onCatch}>接住</button>
      <span className="minigame-inline-reward">得分 {score * 3}</span>
      <span className="minigame-inline-timer">剩 {remaining}s</span>
      <button className="fishing-close-btn" onClick={() => void finish()} disabled={submitting} aria-label="结束接物小游戏">
        结束
      </button>
    </div>
  );
}
