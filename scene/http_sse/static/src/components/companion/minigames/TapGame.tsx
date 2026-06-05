import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchMinigameConfig, submitMinigameResult } from './game-api';
import type { MiniGameProps } from './types';

const TICK_MS = 120;

export default function TapGame({ uid, onDone, label = '# tap', onSwitchGame }: MiniGameProps) {
  const [position, setPosition] = useState(0);
  const [combo, setCombo] = useState(0);
  const [score, setScore] = useState(0);
  const [timer, setTimer] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [flash, setFlash] = useState<'hit' | 'miss' | 'idle'>('idle');

  const stateRef = useRef({
    seed: 0,
    signature: '',
    timer: 0,
    combo: 0,
    score: 0,
    position: 0,
    direction: 1,
    actions: [] as Array<{ t: number; type: string }>,
    maxDuration: 40,
  });

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchMinigameConfig(uid, 'tap');
        stateRef.current.seed = data.seed;
        stateRef.current.signature = data.signature;
        stateRef.current.maxDuration = Math.min(50, data.params.max_duration_s || 40);
      } catch {
        stateRef.current.maxDuration = 40;
      }
    })();
  }, [uid]);

  useEffect(() => {
    const ival = setInterval(() => {
      if (submitting) return;
      const s = stateRef.current;
      s.timer += TICK_MS / 1000;
      s.position += s.direction * 6;
      if (s.position >= 100) {
        s.position = 100;
        s.direction = -1;
      } else if (s.position <= 0) {
        s.position = 0;
        s.direction = 1;
      }
      setTimer(s.timer);
      setPosition(s.position);
      if (s.timer >= s.maxDuration) {
        void finish();
      }
    }, TICK_MS);
    return () => clearInterval(ival);
  }, [submitting]);

  const onTap = useCallback(() => {
    const s = stateRef.current;
    s.actions.push({ t: s.timer, type: 'tap' });
    const inWindow = s.position >= 42 && s.position <= 58;
    if (inWindow) {
      s.combo += 1;
      s.score += 2 + Math.min(3, Math.floor(s.combo / 2));
      setCombo(s.combo);
      setScore(s.score);
      setFlash('hit');
    } else {
      s.combo = 0;
      setCombo(0);
      setFlash('miss');
    }
    setTimeout(() => setFlash('idle'), 220);
  }, []);

  async function finish() {
    if (submitting) return;
    setSubmitting(true);
    const s = stateRef.current;
    const items = s.score > 0 ? [`节拍碎光 x${s.score}`] : [];
    try {
      const data = await submitMinigameResult(
        uid,
        'tap',
        s.seed,
        s.signature,
        { food_value: s.score, items },
        s.actions
      );
      onDone({
        food_value: s.score,
        items,
        reaction: data.reaction || 'happy',
        bubble: data.bubble || '拍点子真上头！',
      });
    } catch {
      onDone({
        food_value: s.score,
        items,
        reaction: 'nibble',
        bubble: s.score > 0 ? '节奏抓住了。' : '今天拍点没对上。',
      });
    }
  }

  const remaining = Math.max(0, stateRef.current.maxDuration - Math.floor(timer));
  const markerPos = Math.max(0, Math.min(10, Math.round(position / 10)));
  const lane = Array.from({ length: 11 }, (_, idx) => {
    if (idx === markerPos && idx >= 4 && idx <= 6) return '◎';
    if (idx === markerPos) return '|';
    if (idx >= 4 && idx <= 6) return '=';
    return '.';
  }).join('');
  const logText =
    flash === 'hit' ? `踩中了，连击 ${combo}` :
    flash === 'miss' ? '慢了一拍，再来' :
    '指针进中间亮区时点击';

  return (
    <div className={`minigame-inline-game tap-game ${flash !== 'idle' ? `is-${flash}` : ''}`}>
      <button
        type="button"
        className={`minigame-inline-chip ${onSwitchGame ? 'is-switcher' : ''}`}
        onClick={onSwitchGame}
        aria-label="切换小游戏"
      >
        {label}
      </button>
      <span className="minigame-inline-state">看准亮区</span>
      <span className="tap-lane">[{lane}]</span>
      <span className="minigame-inline-log">{logText}</span>
      <button className="btn btn-primary fishing-btn" onClick={onTap}>拍一下</button>
      <span className="minigame-inline-reward">得分 {score} / 连击 {combo}</span>
      <span className="minigame-inline-timer">剩 {remaining}s</span>
      <button className="fishing-close-btn" onClick={() => void finish()} disabled={submitting} aria-label="结束节拍小游戏">
        结束
      </button>
    </div>
  );
}
