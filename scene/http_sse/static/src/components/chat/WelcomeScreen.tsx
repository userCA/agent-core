import React, { useState, useEffect } from 'react';
import Icon from '../shared/Icon';
import { getWelcomeScenes, type SceneCategory } from '../../config/welcome';
import './WelcomeScreen.css';

interface Props {
  onSelect?: (text: string) => void;
}

export default function WelcomeScreen({ onSelect }: Props) {
  const [scenes] = useState<SceneCategory[]>(() => getWelcomeScenes());
  const [activeScene, setActiveScene] = useState<string>(scenes[0]?.id || 'code');
  const [mounted, setMounted] = useState(false);
  const scene = scenes.find((s) => s.id === activeScene) ?? scenes[0];

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="welcome">
      <div className="welcome-ambient" aria-hidden="true" />
      <pre className="welcome-logo" aria-hidden="true">{`
              ██            ██
             ████          ████
            ██████        ██████
           ██████████████████████
          ████    ████████    ████
          ████                ████
          ████  ██  ██  ██  ████
          ████    ██████    ████
           ██████████████████████
             ████          ████
              ████████████████
                ████    ████
                 ██      ██
      `}</pre>
      <h1 className="welcome-title">咪兔</h1>
      <p className="welcome-subtitle">你的 AI 伙伴 — 随时为你提供帮助</p>

      {/* Scene tabs */}
      <div className="scene-tabs">
        {scenes.map((s) => (
          <button
            key={s.id}
            className={`scene-tab${activeScene === s.id ? ' active' : ''}`}
            onClick={() => setActiveScene(s.id)}
            aria-pressed={activeScene === s.id}
          >
            <Icon name={s.icon} size={14} />
            {s.label}
          </button>
        ))}
      </div>

      {/* Prompt grid for active scene */}
      <div className="prompt-grid">
        {scene.prompts.map((p, idx) => (
          <button
            key={`${scene.id}-${p.label}`}
            className={`prompt-card${mounted ? ' animated' : ''}`}
            onClick={() => onSelect?.(p.text)}
            style={{ animationDelay: `${idx * 0.08}s` }}
          >
            <span className="prompt-icon">
              <Icon name={p.icon} size={16} />
            </span>
            <span className="prompt-label">{p.label}</span>
          </button>
        ))}
      </div>

    </div>
  );
}
