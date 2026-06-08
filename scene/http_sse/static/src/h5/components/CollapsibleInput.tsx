import React, { useState, useCallback } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import ChatInput from '../../components/input/ChatInput';
import './CollapsibleInput.css';

interface Props {
  onSend: (text: string) => void;
}

const MOODS = ['awake', 'happy', 'sleeping', 'working', 'concerned'] as const;

export default function CollapsibleInput({ onSend }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [moodIdx, setMoodIdx] = useState(0);

  const mood = MOODS[moodIdx];

  const handleSend = useCallback((text: string) => {
    onSend(text);
    setExpanded(false);
    setMoodIdx((i) => (i + 1) % MOODS.length);
  }, [onSend]);

  return (
    <div className="h5-input-dock">
      <AnimatePresence>
        {!expanded && (
          <motion.button
            className="h5-input-fab"
            onClick={() => setExpanded(true)}
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0 }}
            transition={{ type: 'spring', stiffness: 400, damping: 22 }}
          >
            <span className={`h5-fab-avatar h5-fab-avatar--${mood}`}>
              <span className="h5-fab-ear h5-fab-ear--l" />
              <span className="h5-fab-ear h5-fab-ear--r" />
              <span className="h5-fab-eye h5-fab-eye--l" />
              <span className="h5-fab-eye h5-fab-eye--r" />
              <span className="h5-fab-nose" />
            </span>
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {expanded && (
          <>
            <motion.div
              className="h5-input-backdrop"
              onClick={() => setExpanded(false)}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
            />
            <motion.div
              className="h5-input-expanded"
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', stiffness: 300, damping: 30, mass: 0.9 }}
            >
              <div className="h5-input-expanded-header">
                <span className={`h5-fab-avatar h5-fab-avatar--sm h5-fab-avatar--${mood}`}>
                  <span className="h5-fab-ear h5-fab-ear--l" />
                  <span className="h5-fab-ear h5-fab-ear--r" />
                  <span className="h5-fab-eye h5-fab-eye--l" />
                  <span className="h5-fab-eye h5-fab-eye--r" />
                  <span className="h5-fab-nose" />
                </span>
                <span className="h5-input-expanded-title">和咪兔聊聊</span>
                <button className="h5-input-dismiss" onClick={() => setExpanded(false)}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
              <ChatInput onSend={handleSend} compact />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
