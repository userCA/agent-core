import { useState } from 'react';
import { useSessionStore } from '../../../stores/session-store';
import { useChatStore } from '../../../stores/chat-store';
import FishingGame from './FishingGame';
import CatchGame from './CatchGame';
import TapGame from './TapGame';
import type { MiniGameId, MiniGameResult } from './types';

const GAME_OPTIONS: Array<{ id: MiniGameId; label: string; teaser: string; resultLabel: string }> = [
  { id: 'fishing', label: '~> fish', teaser: '~> fish', resultLabel: '~> fish' },
  { id: 'catch', label: '* catch', teaser: '* catch', resultLabel: '* catch' },
  { id: 'tap', label: '# tap', teaser: '# tap', resultLabel: '# tap' },
];

export default function MiniGameHost() {
  const uid = useSessionStore((s) => s.authHeaders.uid || '');
  const isStreaming = useChatStore((s) => s.isStreaming);
  const [active, setActive] = useState(false);
  const [activeGame, setActiveGame] = useState<MiniGameId>('fishing');
  const [result, setResult] = useState<(MiniGameResult & { game: MiniGameId }) | null>(null);

  if (!uid) return null;

  const handleDone = (r: MiniGameResult) => {
    setResult({ ...r, game: activeGame });
    setActive(false);
    setTimeout(() => setResult(null), 6000);
  };

  const currentOption = GAME_OPTIONS.find((option) => option.id === activeGame) ?? GAME_OPTIONS[0];
  const cycleGame = () => {
    const currentIndex = GAME_OPTIONS.findIndex((option) => option.id === activeGame);
    const nextIndex = (currentIndex + 1) % GAME_OPTIONS.length;
    setActiveGame(GAME_OPTIONS[nextIndex].id);
  };

  const renderGame = () => {
    switch (activeGame) {
      case 'catch':
        return <CatchGame uid={uid} onDone={handleDone} label={currentOption.label} onSwitchGame={cycleGame} />;
      case 'tap':
        return <TapGame uid={uid} onDone={handleDone} label={currentOption.label} onSwitchGame={cycleGame} />;
      case 'fishing':
      default:
        return <FishingGame uid={uid} onDone={handleDone} label={currentOption.label} onSwitchGame={cycleGame} />;
    }
  };

  return (
    <span className={`minigame-host ${active ? 'is-active' : ''} ${result ? 'has-result' : ''}`}>
      <button
        className={`minigame-teaser ${isStreaming ? 'is-ready' : ''} ${active ? 'is-mounted' : ''}`}
        onClick={() => setActive((prev) => !prev)}
        aria-label={active ? '收起小游戏' : '打开小游戏'}
        aria-expanded={active}
        aria-controls="header-minigame-dock"
      >
        <span className="minigame-teaser-text">{currentOption.teaser}</span>
      </button>

      {active && (
        <span className="minigame-dock-host">
          <span className="minigame-dock-connector" aria-hidden="true">
            <svg viewBox="0 0 132 28" preserveAspectRatio="none">
              <path d="M4 22 C26 22, 32 8, 58 8 S102 10, 128 10" />
              <circle cx="4" cy="22" r="2.2" />
              <circle cx="128" cy="10" r="2.2" />
            </svg>
          </span>
          <span className="minigame-dock-shell" id="header-minigame-dock">
            <span className="minigame-dock-lane">
              {renderGame()}
            </span>
          </span>
        </span>
      )}

      {!active && result && (
        <span className="minigame-result-pill" aria-live="polite">
          <span className="minigame-result-chip">
            {GAME_OPTIONS.find((option) => option.id === result.game)?.resultLabel ?? result.game}
          </span>
          <span className="minigame-result-log">{result.bubble}</span>
        </span>
      )}
    </span>
  );
}
