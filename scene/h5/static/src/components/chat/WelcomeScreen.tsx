import React, { useState } from 'react';
import { motion } from 'motion/react';
import Icon from '../shared/Icon';
import { getWelcomeScenes, type SceneCategory } from '../../config/welcome';
import './WelcomeScreen.css';

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' as const } },
};

const stagger = {
  visible: { transition: { staggerChildren: 0.05, delayChildren: 0.1 } },
};

interface Props {
  onSelect?: (text: string) => void;
}

export default function WelcomeScreen({ onSelect }: Props) {
  const [scenes] = useState<SceneCategory[]>(() => getWelcomeScenes());
  const [activeScene, setActiveScene] = useState<string>(scenes[0]?.id || 'code');
  const scene = scenes.find((s) => s.id === activeScene) ?? scenes[0];

  return (
    <motion.div
      className="welcome"
      variants={stagger}
      initial="hidden"
      animate="visible"
    >
      <div className="welcome-ambient" aria-hidden="true" />
      <motion.div variants={fadeUp}>
        <pre className="welcome-logo welcome-logo--float" aria-hidden="true">{`
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
      </motion.div>
      <motion.h1 className="welcome-title" variants={fadeUp}>咪兔</motion.h1>
      <motion.p className="welcome-subtitle" variants={fadeUp}>你的 AI 伙伴 — 随时为你提供帮助</motion.p>

      <motion.div className="scene-tabs" variants={stagger}>
        {scenes.map((s) => (
          <motion.button
            key={s.id}
            className={`scene-tab${activeScene === s.id ? ' active' : ''}`}
            onClick={() => setActiveScene(s.id)}
            aria-pressed={activeScene === s.id}
            variants={fadeUp}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.95 }}
          >
            <Icon name={s.icon} size={14} />
            {s.label}
          </motion.button>
        ))}
      </motion.div>

      <motion.div className="prompt-grid" variants={stagger}>
        {scene.prompts.map((p) => (
          <motion.button
            key={`${scene.id}-${p.label}`}
            className="prompt-card"
            onClick={() => onSelect?.(p.text)}
            variants={fadeUp}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.97 }}
          >
            <span className="prompt-icon">
              <Icon name={p.icon} size={16} />
            </span>
            <span className="prompt-label">{p.label}</span>
          </motion.button>
        ))}
      </motion.div>

    </motion.div>
  );
}
