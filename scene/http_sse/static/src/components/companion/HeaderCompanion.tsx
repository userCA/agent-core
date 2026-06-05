import React from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useCompanionStore } from '../../stores/companion-store';
import CompanionSprite from './CompanionSprite';
import type { CompanionMood } from './CompanionSprite';

export default function HeaderCompanion() {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const storeMood = useCompanionStore((s) => s.mood);
  const setMood = useCompanionStore((s) => s.setMood);

  const targetMood: CompanionMood = isStreaming ? 'working' : 'awake';

  React.useEffect(() => {
    setMood(targetMood);
  }, [targetMood, setMood]);

  return (
    <CompanionSprite mood={storeMood} className="header-companion-art" />
  );
}
